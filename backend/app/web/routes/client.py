from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.exceptions import ForbiddenError, ValidationError
from app.domain.models import (
    Booking,
    BookingItem,
    BookingStatus,
    Service,
    ServiceCategory,
    SpecialistService,
    StaffMember,
    Tenant,
)
from app.domain.services.availability_service import find_schedule_offers
from app.domain.services.booking_service import book_services_at_start, book_services_in_cell, cancel_booking
from app.domain.services.cell_service import get_default_branch, load_services
from app.domain.services.client_service import normalize_phone, upsert_client_profile
from app.web.deps import WebContext, get_tenant, require_auth, writable
from app.web.serializers import hhmm, local_date, schedule_offer_dict, service_card, staff_card

router = APIRouter(prefix="/api/t/{tenant_public_id}/client", tags=["client"])


@router.get("/catalog")
async def catalog(
    tenant: Tenant = Depends(get_tenant), session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    categories = {
        c.id: c.name
        for c in (await session.scalars(select(ServiceCategory).where(ServiceCategory.tenant_id == tenant.id))).all()
    }
    services = (
        await session.scalars(
            select(Service).where(Service.tenant_id == tenant.id, Service.is_active.is_(True)).order_by(Service.name)
        )
    ).all()
    staff = (
        await session.scalars(
            select(StaffMember)
            .where(StaffMember.tenant_id == tenant.id, StaffMember.is_active.is_(True))
            .order_by(StaffMember.display_name)
        )
    ).all()
    links = (await session.scalars(select(SpecialistService).where(SpecialistService.tenant_id == tenant.id))).all()
    linked: dict[UUID, set[UUID]] = defaultdict(set)
    for lk in links:
        linked[lk.service_id].add(lk.staff_member_id)
    all_staff_ids = [s.id for s in staff]

    service_payload = []
    for svc in services:
        card = service_card(svc, categories.get(svc.category_id) if svc.category_id else None)
        ids = [i for i in all_staff_ids if i in linked[svc.id]] if svc.id in linked else all_staff_ids
        card["staff_ids"] = [str(i) for i in ids]
        service_payload.append(card)
    return {
        "services": service_payload,
        "specialists": [staff_card(s, tenant.public_id) for s in staff],
    }


class AvailabilityBody(BaseModel):
    service_ids: list[UUID] = Field(min_length=1, max_length=10)
    staff_member_id: UUID | None = None


@router.post("/availability")
async def availability(
    body: AvailabilityBody,
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    branch = await get_default_branch(session, tenant)
    tz = ZoneInfo(branch.timezone)
    services = await load_services(session, tenant.id, body.service_ids)
    now = datetime.now(UTC)
    branch = await get_default_branch(session, tenant)
    offers = await find_schedule_offers(
        session,
        tenant=tenant,
        branch=branch,
        service_ids=body.service_ids,
        range_start=now,
        range_end=now + timedelta(days=366),
        staff_member_id=body.staff_member_id,
        now=now,
    )
    by_day: dict[str, list[dict[str, object]]] = defaultdict(list)
    from app.web.serializers import schedule_offer_dict

    for offer in offers:
        by_day[local_date(offer.start_at, tz).isoformat()].append(
            schedule_offer_dict(offer, tz, tenant.public_id)
        )
    return {
        "summary": {
            "total_minutes": sum(s.duration_minutes for s in services),
            "base_price_cents": sum(s.price_cents for s in services),
            "services": [{"id": str(s.id), "name": s.name} for s in services],
        },
        "days": [{"date": d, "offers": by_day[d]} for d in sorted(by_day)],
    }


class BookingBody(BaseModel):
    cell_id: UUID | None = None
    staff_member_id: UUID | None = None
    start_at: datetime | None = None
    service_ids: list[UUID] = Field(min_length=1, max_length=10)
    comment: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)


@router.post("/bookings", status_code=201)
async def create_booking(
    body: BookingBody,
    ctx: WebContext = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    assert ctx.user is not None
    needs_profile = ctx.client is None or len(normalize_phone(ctx.client.phone or "")) < 10
    if needs_profile or body.name or body.phone:
        phone = body.phone or (ctx.client.phone if ctx.client else None)
        if not phone or len(normalize_phone(phone)) < 10:
            raise ValidationError("phone is required")
        profile = await upsert_client_profile(
            session,
            tenant_id=tenant.id,
            user_account_id=ctx.user.id,
            name=(body.name or ctx.display_name or "Клиент").strip(),
            phone=phone,
            source="web",
        )
    else:
        assert ctx.client is not None
        profile = ctx.client
    ctx.client = profile
    if body.cell_id is not None:
        booking = await book_services_in_cell(
            session,
            tenant=tenant,
            cell_id=body.cell_id,
            client_profile_id=profile.id,
            service_ids=body.service_ids,
            comment=body.comment,
            actor_user_id=ctx.user.id,
            source="web",
        )
    elif body.staff_member_id is not None and body.start_at is not None:
        booking = await book_services_at_start(
            session,
            tenant=tenant,
            staff_member_id=body.staff_member_id,
            start_at=body.start_at,
            client_profile_id=profile.id,
            service_ids=body.service_ids,
            comment=body.comment,
            actor_user_id=ctx.user.id,
            source="web",
        )
    else:
        raise ValidationError("cell_id or (staff_member_id and start_at) required")
    await session.commit()
    mine = await _my_bookings(session, ctx, only=booking.id)
    return mine[0]


async def _my_bookings(
    session: AsyncSession, ctx: WebContext, *, only: UUID | None = None
) -> list[dict[str, object]]:
    if ctx.client is None:
        return []
    branch = await get_default_branch(session, ctx.tenant)
    tz = ZoneInfo(branch.timezone)
    stmt = (
        select(Booking, BookingItem, Service, StaffMember)
        .join(BookingItem, BookingItem.booking_id == Booking.id)
        .join(Service, Service.id == BookingItem.service_id)
        .join(StaffMember, StaffMember.id == BookingItem.staff_member_id)
        .where(Booking.tenant_id == ctx.tenant.id, Booking.client_profile_id == ctx.client.id)
        .order_by(func.lower(BookingItem.during))
    )
    if only is not None:
        stmt = stmt.where(Booking.id == only)
    grouped: dict[UUID, dict[str, object]] = {}
    for booking, item, service, staff in (await session.execute(stmt)).all():
        rng = item.during
        entry = grouped.get(booking.id)
        if entry is None:
            entry = {
                "id": str(booking.id),
                "status": booking.status,
                "date": local_date(rng.lower, tz).isoformat(),
                "start": hhmm(rng.lower, tz),
                "end": hhmm(rng.upper, tz),
                "_start": rng.lower,
                "total_price_cents": booking.total_price_cents,
                "staff": staff_card(staff, ctx.tenant.public_id),
                "services": [],
            }
            grouped[booking.id] = entry
        entry["end"] = hhmm(rng.upper, tz)
        services_list = entry["services"]
        assert isinstance(services_list, list)
        services_list.append({"id": str(service.id), "name": service.name, "duration_minutes": item.duration_minutes})
    now = datetime.now(UTC)
    rows = sorted(grouped.values(), key=lambda e: e["_start"], reverse=True)  # type: ignore[arg-type, return-value]
    for row in rows:
        start = row.pop("_start")
        assert isinstance(start, datetime)
        row["upcoming"] = start > now and row["status"] in {
            BookingStatus.BOOKED.value,
            BookingStatus.CONFIRMED.value,
            BookingStatus.HELD.value,
        }
    return rows


@router.get("/bookings")
async def my_bookings(
    ctx: WebContext = Depends(require_auth), session: AsyncSession = Depends(get_session)
) -> list[dict[str, object]]:
    return await _my_bookings(session, ctx)


@router.delete("/bookings/{booking_id}")
async def cancel_my_booking(
    booking_id: UUID,
    ctx: WebContext = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    booking = await session.get(Booking, booking_id)
    owned = booking is not None and ctx.client is not None and booking.client_profile_id == ctx.client.id
    if booking is None or booking.tenant_id != tenant.id or not owned:
        raise HTTPException(status_code=404, detail="booking not found")
    if booking.status in {BookingStatus.CANCELLED.value, BookingStatus.COMPLETED.value, BookingStatus.NO_SHOW.value}:
        raise ForbiddenError("booking cannot be cancelled")
    assert ctx.user is not None
    await cancel_booking(
        session, tenant=tenant, booking_id=booking_id, reason="client_cancel_web", actor_user_id=ctx.user.id
    )
    await session.commit()
    return {"status": "cancelled"}
