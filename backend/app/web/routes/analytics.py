from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.services.analytics_service import (
    analytics_series,
    analytics_summary,
    staff_booking_counts,
    top_services,
)
from app.domain.services.cell_service import get_default_branch
from app.web.deps import WebContext, require_manager

router = APIRouter(prefix="/api/t/{tenant_public_id}/manager", tags=["analytics"])


def _parse_range(
    from_date: date | None,
    to_date: date | None,
    tz: ZoneInfo,
    *,
    horizon_days: int,
) -> tuple[date, date]:
    today = datetime.now(tz).date()
    end = to_date or (today + timedelta(days=max(horizon_days, 1)))
    if from_date is None:
        return date(2020, 1, 1), end
    return from_date, end


@router.get("/analytics/summary")
async def get_analytics_summary(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    branch = await get_default_branch(session, ctx.tenant)
    tz = ZoneInfo(branch.timezone or "Europe/Moscow")
    horizon = int((ctx.tenant.rules or {}).get("booking_horizon_days", 30))
    start, end = _parse_range(from_date, to_date, tz, horizon_days=horizon)
    summary = await analytics_summary(
        session, tenant=ctx.tenant, branch=branch, start_day=start, end_day=end
    )
    services = await top_services(
        session, tenant_id=ctx.tenant.id, start_day=start, end_day=end, tz_name=branch.timezone or "Europe/Moscow"
    )
    staff = await staff_booking_counts(
        session, tenant_id=ctx.tenant.id, start_day=start, end_day=end, tz_name=branch.timezone or "Europe/Moscow"
    )
    util_pct = 0
    if summary.work_minutes > 0:
        booked = summary.work_minutes - summary.free_minutes
        util_pct = round(100 * booked / summary.work_minutes)
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "counts": {
            "completed": summary.completed,
            "cancelled": summary.cancelled,
            "upcoming": summary.upcoming,
            "no_show": summary.no_show,
            "held": summary.held,
            "free_minutes": summary.free_minutes,
            "work_minutes": summary.work_minutes,
            "utilization_percent": util_pct,
        },
        "revenue_cents": summary.revenue_cents,
        "avg_ticket_cents": summary.avg_ticket_cents,
        "bookings_total": summary.bookings_total,
        "top_services": services,
        "staff_completed": staff,
    }


@router.get("/analytics/series")
async def get_analytics_series(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    metric: str = Query(default="bookings", pattern="^(bookings|revenue)$"),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    branch = await get_default_branch(session, ctx.tenant)
    tz = ZoneInfo(branch.timezone or "Europe/Moscow")
    horizon = int((ctx.tenant.rules or {}).get("booking_horizon_days", 30))
    start, end = _parse_range(from_date, to_date, tz, horizon_days=horizon)
    points = await analytics_series(
        session,
        tenant=ctx.tenant,
        branch=branch,
        start_day=start,
        end_day=end,
        granularity=granularity,
        metric=metric,
    )
    return {"granularity": granularity, "metric": metric, "points": points}