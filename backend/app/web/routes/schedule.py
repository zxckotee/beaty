"""Day dashboard (the "bar" of cells) shared by manager and specialist views."""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.services.cell_service import (
    get_default_branch,
    list_cells,
    local_day_bounds,
    work_day_hours,
)
from app.web.deps import WebContext, require_manager, require_staff
from app.web.serializers import booking_dict, cell_dict, local_date

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
    start, end = local_day_bounds(day, branch.timezone)
    staff_filter = ctx.staff.id if own_only and ctx.staff else None
    views = await list_cells(
        session, tenant_id=tenant.id, range_start=start, range_end=end, staff_member_id=staff_filter
    )
    own_id = ctx.staff.id if ctx.staff else None
    cells = [
        cell_dict(v, tz, tenant.public_id, reveal_clients=ctx.is_manager or v.staff.id == own_id) for v in views
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
            "bookings": sum(len(v.bookings) for v in views),
            "free_minutes": sum(v.free_minutes for v in views),
        },
    }


async def counts_payload(
    session: AsyncSession, ctx: WebContext, start_day: date, days: int, *, own_only: bool
) -> dict[str, int]:
    branch = await get_default_branch(session, ctx.tenant)
    tz = ZoneInfo(branch.timezone)
    range_start, _ = local_day_bounds(start_day, branch.timezone)
    _, range_end = local_day_bounds(start_day + timedelta(days=days - 1), branch.timezone)
    staff_filter = ctx.staff.id if own_only and ctx.staff else None
    views = await list_cells(
        session,
        tenant_id=ctx.tenant.id,
        range_start=range_start,
        range_end=range_end,
        staff_member_id=staff_filter,
        with_bookings=False,
    )
    counts: dict[str, int] = {}
    for v in views:
        key = local_date(v.cell.starts_at, tz).isoformat()
        counts[key] = counts.get(key, 0) + 1
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
    start, end = local_day_bounds(day, branch.timezone)
    views = await list_cells(
        session, tenant_id=ctx.tenant.id, range_start=start, range_end=end, staff_member_id=ctx.staff.id
    )
    rows = [booking_dict(b, tz, reveal=True) for v in views for b in v.bookings]
    rows.sort(key=lambda r: str(r["start"]))
    return rows
