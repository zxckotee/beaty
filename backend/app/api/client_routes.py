from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_by_public_id, resolve_staff_and_client
from app.api.schemas import BookingOut, HoldBookingRequest, RescheduleRequest, SlotOut
from app.api.subscription_gate import assert_tenant_can_write
from app.core.context import UserContext
from app.core.db import get_session
from app.domain.exceptions import DomainError, ForbiddenError, SlotTakenError
from app.domain.models import Booking, BookingItem, Branch, Service, StaffMember
from app.domain.services.booking_service import (
    cancel_booking,
    confirm_hold,
    hold_slot,
    reschedule_booking,
)
from app.domain.services.slot_repository import list_available_slots

client_router = APIRouter(prefix="/client", tags=["client"])


class ForceMajeureChoice(BaseModel):
    choice: dict


@client_router.get("/slots", response_model=list[SlotOut])
async def client_slots(
    tenant_public_id: str = Query(...),
    service_id: UUID = Query(...),
    staff_member_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[SlotOut]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    service = await session.get(Service, service_id)
    if service is None or service.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="service not found")
    branch_id = UUID(str((tenant.rules or {}).get("default_branch_id")))
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=500, detail="branch not configured")
    slots = await list_available_slots(
        session,
        tenant_id=tenant.id,
        branch=branch,
        service=service,
        staff_member_id=staff_member_id,
        rules=tenant.rules or {},
    )
    return [
        SlotOut(start=s.start, end=s.end, staff_member_id=s.staff_member_id) for s in slots
    ]


@client_router.post("/bookings/hold", response_model=BookingOut)
async def client_hold(
    body: HoldBookingRequest,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> BookingOut:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        raise HTTPException(status_code=400, detail="client profile required")
    branch_id = UUID(str((tenant.rules or {}).get("default_branch_id")))
    staff_id = body.staff_member_id
    if staff_id is None:
        raise HTTPException(status_code=400, detail="staff_member_id required")
    try:
        booking = await hold_slot(
            session,
            tenant=tenant,
            branch_id=branch_id,
            client_profile_id=user.client_profile_id,
            staff_member_id=staff_id,
            service_id=body.service_id,
            start_at=body.start_at,
            actor_user_id=user.user_account_id,
        )
        await session.commit()
    except SlotTakenError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BookingOut(
        id=booking.id,
        status=booking.status,
        total_price_cents=booking.total_price_cents,
        hold_expires_at=booking.hold_expires_at,
    )


@client_router.post("/bookings/{booking_id}/reschedule", response_model=BookingOut)
async def client_reschedule(
    booking_id: UUID,
    body: RescheduleRequest,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> BookingOut:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    try:
        booking = await reschedule_booking(
            session,
            tenant=tenant,
            booking_id=booking_id,
            new_start_at=body.start_at,
            actor_user_id=user.user_account_id,
        )
        await session.commit()
    except (SlotTakenError, DomainError, ForbiddenError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BookingOut(
        id=booking.id,
        status=booking.status,
        total_price_cents=booking.total_price_cents,
        hold_expires_at=booking.hold_expires_at,
    )


@client_router.post("/bookings/{booking_id}/force-majeure")
async def client_force_majeure_choice(
    booking_id: UUID,
    body: ForceMajeureChoice,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    from app.domain.services.force_majeure import apply_force_majeure_choice

    await apply_force_majeure_choice(
        session,
        tenant_id=tenant.id,
        booking_id=booking_id,
        choice=body.choice,
        actor_user_id=user.user_account_id,
    )
    await session.commit()
    return {"status": "ok"}


@client_router.get("/bookings/mine/detailed")
async def client_bookings_detailed(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> list[dict]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        return []
    rows = await session.execute(
        text(
            """
            SELECT b.id, b.status, b.total_price_cents, b.hold_expires_at,
                   s.name AS service_name, sm.display_name AS staff_name,
                   lower(bi.during) AS start_at, upper(bi.during) AS end_at
            FROM booking b
            JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            JOIN service s ON s.id = bi.service_id
            JOIN staff_member sm ON sm.id = bi.staff_member_id
            WHERE b.tenant_id = :tenant_id AND b.client_profile_id = :client_id
            ORDER BY start_at DESC NULLS LAST
            """
        ),
        {"tenant_id": str(tenant.id), "client_id": str(user.client_profile_id)},
    )
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "total_price_cents": r.total_price_cents,
            "hold_expires_at": r.hold_expires_at.isoformat() if r.hold_expires_at else None,
            "service_name": r.service_name,
            "staff_name": r.staff_name,
            "start_at": r.start_at.isoformat() if r.start_at else None,
            "end_at": r.end_at.isoformat() if r.end_at else None,
        }
        for r in rows.all()
    ]
