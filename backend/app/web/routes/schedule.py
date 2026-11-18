"""Day dashboard (the "bar" of cells) shared by manager and specialist views."""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.services.availability_service import list_schedule_day_windows
from app.domain.services.cell_service import get_default_branch, work_day_hours
from app.web.deps import WebContext, require_manager, require_staff
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
    return {
        "date": day.isoformat(),
        "timezone": branch.timezone,
        "work_start": work_start,
        "work_end": work_end,
        "cells": cells,
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
