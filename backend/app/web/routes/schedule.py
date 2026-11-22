"""Day dashboard (the "bar" of cells) shared by manager and specialist views."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.exceptions import ForbiddenError, NotFoundError
from app.domain.models import Booking, BookingItem
from app.domain.services.availability_service import list_schedule_day_windows
from app.domain.services.booking_service import cancel_booking, mark_booking_completed
from app.domain.services.cell_service import get_default_branch, work_day_hours
from app.web.deps import WebContext, require_manager, require_staff, writable
from app.web.serializers import booking_dict, schedule_window_dict

router = APIRouter(prefix="/api/t/{tenant_public_id}", tags=["schedule"])


async def day_payload(
    session: AsyncSession,
    ctx: WebContext,
    day: date,
    *,
    own_only: bool,
) -> dict[str, object]:
    tenant = ctx.tenant
    branch = await get_default_branch(session, tenant)
    tz = ZoneInfo(branch.timezone)
    staff_filter = ctx.staff.id if own_only and ctx.staff else None
    windows = await list_schedule_day_windows(
        session, tenant=tenant, branch=branch, day=day, staff_member_id=staff_filter
    )
    own_id = ctx.staff.id if ctx.staff else None
    cells = [
        schedule_window_dict(w, tz, tenant.public_id, reveal_clients=ctx.is_manager or w.staff.id == own_id)
        for w in windows
    ]
    work_start, work_end = work_day_hours(tenant)
    today_local = datetime.now(tz).date()
    is_past = day < today_local
    active_on_day = sum(
        1 for w in windows for b in w.bookings if b.status in {"held", "booked", "confirmed", "arrived"}
    )
    return {
        "date": day.isoformat(),
        "timezone": branch.timezone,
        "work_start": work_start,
        "work_end": work_end,
        "cells": cells,
        "meta": {
            "is_past": is_past,
            "read_only_booking": is_past,
            "active_bookings": active_on_day,
        },
        "stats": {
            "cells": len(cells),
            "shifts": len(cells),
            "bookings": sum(len(w.bookings) for w in windows),
            "free_minutes": sum(w.free_minutes for w in windows),
        },
    }


async def counts_payload(
    session: AsyncSession, ctx: WebContext, start_day: date, days: int, *, own_only: bool
) -> dict[str, int]:
    branch = await get_default_branch(session, ctx.tenant)
    staff_filter = ctx.staff.id if own_only and ctx.staff else None
    counts: dict[str, int] = {}
    for offset in range(days):
        d = start_day + timedelta(days=offset)
        windows = await list_schedule_day_windows(
            session, tenant=ctx.tenant, branch=branch, day=d, staff_member_id=staff_filter
        )
        if windows:
            key = d.isoformat()
            counts[key] = len(windows)
    return counts


@router.get("/manager/day")
async def manager_day(
    day: date = Query(alias="date"),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return await day_payload(session, ctx, day, own_only=False)


@router.get("/manager/cells/counts")
async def manager_counts(
    start: date = Query(alias="from"),
    days: int = Query(default=21, ge=1, le=62),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    return await counts_payload(session, ctx, start, days, own_only=False)


@router.get("/specialist/day")
async def specialist_day(
    day: date = Query(alias="date"),
    scope: str = Query(default="own", pattern="^(own|all)$"),
    ctx: WebContext = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return await day_payload(session, ctx, day, own_only=scope == "own")


@router.get("/specialist/cells/counts")
async def specialist_counts(
    start: date = Query(alias="from"),
    days: int = Query(default=21, ge=1, le=62),
    scope: str = Query(default="own", pattern="^(own|all)$"),
    ctx: WebContext = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    return await counts_payload(session, ctx, start, days, own_only=scope == "own")


@router.get("/specialist/bookings")
async def specialist_bookings(
    day: date = Query(alias="date"),
    ctx: WebContext = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Flat list of the specialist's own bookings for a day (read-only)."""
    assert ctx.staff is not None
    branch = await get_default_branch(session, ctx.tenant)
    tz = ZoneInfo(branch.timezone)
    windows = await list_schedule_day_windows(
        session, tenant=ctx.tenant, branch=branch, day=day, staff_member_id=ctx.staff.id
    )
    rows = [booking_dict(b, tz, reveal=True) for w in windows for b in w.bookings]
    rows.sort(key=lambda r: str(r["start"]))
    return rows


class SpecialistBookingCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


async def _assert_specialist_owns_booking(
    session: AsyncSession, ctx: WebContext, booking_id: UUID
) -> Booking:
    assert ctx.staff is not None
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != ctx.tenant.id:
        raise HTTPException(status_code=404, detail="booking not found")
    owned = await session.scalar(
        select(BookingItem.id)
        .where(
            BookingItem.booking_id == booking_id,
            BookingItem.staff_member_id == ctx.staff.id,
        )
        .limit(1)
    )
    if owned is None:
        raise HTTPException(status_code=403, detail="not your booking")
    return booking


@router.post("/specialist/bookings/{booking_id}/complete")
async def specialist_complete_booking(
    booking_id: UUID,
    ctx: WebContext = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    assert ctx.user is not None
    await _assert_specialist_owns_booking(session, ctx, booking_id)
    try:
        booking = await mark_booking_completed(
            session, tenant=tenant, booking_id=booking_id, actor_user_id=ctx.user.id
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="booking not found") from None
    except ForbiddenError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    await session.commit()
    return {"status": booking.status}


@router.post("/specialist/bookings/{booking_id}/cancel")
async def specialist_cancel_booking(
    booking_id: UUID,
    body: SpecialistBookingCancelIn,
    ctx: WebContext = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    assert ctx.user is not None
    await _assert_specialist_owns_booking(session, ctx, booking_id)
    try:
        booking = await cancel_booking(
            session,
            tenant=tenant,
            booking_id=booking_id,
            reason="manager_cancel",
            message=body.reason,
            actor_user_id=ctx.user.id,
            skip_deadline_check=True,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="booking not found") from None
    except ForbiddenError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    await session.commit()
    return {"status": booking.status}
