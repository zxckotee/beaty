"""Manager dashboard aggregates (bookings, revenue, free time)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, BookingItem, BookingStatus, Branch, Service, StaffMember, Tenant
from app.domain.services.availability_service import list_schedule_day_windows
from app.domain.services.cell_service import ACTIVE_STATUSES, get_default_branch

ACTIVE = tuple(ACTIVE_STATUSES)
MAX_RANGE_DAYS = 366


@dataclass
class AnalyticsSummary:
    completed: int
    cancelled: int
    upcoming: int
    no_show: int
    held: int
    free_minutes: int
    work_minutes: int
    revenue_cents: int
    avg_ticket_cents: int
    bookings_total: int


def _clamp_range(start: date, end: date) -> tuple[date, date]:
    if end < start:
        start, end = end, start
    if (end - start).days > MAX_RANGE_DAYS:
        end = start + timedelta(days=MAX_RANGE_DAYS)
    return start, end


def _range_bounds(start: date, end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    rs = datetime.combine(start, time.min, tzinfo=tz).astimezone(UTC)
    re = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return rs, re


async def analytics_summary(
    session: AsyncSession,
    *,
    tenant: Tenant,
    branch: Branch,
    start_day: date,
    end_day: date,
    now: datetime | None = None,
) -> AnalyticsSummary:
    now = now or datetime.now(UTC)
    tz = ZoneInfo(branch.timezone or "Europe/Moscow")
    start_day, end_day = _clamp_range(start_day, end_day)
    range_start, range_end = _range_bounds(start_day, end_day, tz)

    status_rows = (
        await session.execute(
            select(Booking.status, func.count(func.distinct(Booking.id)))
            .select_from(Booking)
            .join(BookingItem, BookingItem.booking_id == Booking.id)
            .where(
                Booking.tenant_id == tenant.id,
                BookingItem.during.overlaps(Range(range_start, range_end, bounds="[)")),
            )
            .group_by(Booking.status)
        )
    ).all()
    by_status = {str(s): int(c) for s, c in status_rows}

    upcoming = (
        await session.scalar(
            select(func.count(func.distinct(Booking.id)))
            .select_from(Booking)
            .join(BookingItem, BookingItem.booking_id == Booking.id)
            .where(
                Booking.tenant_id == tenant.id,
                Booking.status.in_(ACTIVE),
                BookingItem.is_active.is_(True),
                func.lower(BookingItem.during) > now,
                func.lower(BookingItem.during) < range_end,
                func.lower(BookingItem.during) >= range_start,
            )
        )
        or 0
    )

    revenue = (
        await session.scalar(
            select(func.coalesce(func.sum(Booking.total_price_cents), 0))
            .select_from(Booking)
            .join(BookingItem, BookingItem.booking_id == Booking.id)
            .where(
                Booking.tenant_id == tenant.id,
                Booking.status == BookingStatus.COMPLETED.value,
                BookingItem.during.overlaps(Range(range_start, range_end, bounds="[)")),
            )
        )
        or 0
    )

    completed = int(by_status.get(BookingStatus.COMPLETED.value, 0))
    cancelled = int(by_status.get(BookingStatus.CANCELLED.value, 0))
    avg_ticket = int(revenue // completed) if completed else 0

    free_minutes = 0
    work_minutes = 0
    day = start_day
    while day <= end_day:
        windows = await list_schedule_day_windows(
            session, tenant=tenant, branch=branch, day=day, staff_member_id=None
        )
        for w in windows:
            free_minutes += w.free_minutes
            work_minutes += w.total_minutes
        day += timedelta(days=1)

    bookings_total = sum(by_status.values())
    return AnalyticsSummary(
        completed=completed,
        cancelled=cancelled,
        upcoming=int(upcoming),
        no_show=int(by_status.get(BookingStatus.NO_SHOW.value, 0)),
        held=int(by_status.get(BookingStatus.HELD.value, 0)),
        free_minutes=free_minutes,
        work_minutes=work_minutes,
        revenue_cents=int(revenue),
        avg_ticket_cents=avg_ticket,
        bookings_total=bookings_total,
    )


def _bucket_key(dt: datetime, tz: ZoneInfo, granularity: str) -> str:
    local = dt.astimezone(tz)
    if granularity == "month":
        return f"{local.year}-{local.month:02d}"
    if granularity == "week":
        year, week, _ = local.isocalendar()
        return f"{year}-W{week:02d}"
    return local.date().isoformat()


async def analytics_series(
    session: AsyncSession,
    *,
    tenant: Tenant,
    branch: Branch,
    start_day: date,
    end_day: date,
    granularity: str,
    metric: str,
) -> list[dict[str, object]]:
    tz = ZoneInfo(branch.timezone or "Europe/Moscow")
    start_day, end_day = _clamp_range(start_day, end_day)
    range_start, range_end = _range_bounds(start_day, end_day, tz)

    rows = (
        await session.execute(
            select(
                Booking.id,
                Booking.status,
                Booking.total_price_cents,
                func.lower(BookingItem.during).label("start_at"),
            )
            .join(BookingItem, BookingItem.booking_id == Booking.id)
            .where(
                Booking.tenant_id == tenant.id,
                BookingItem.during.overlaps(Range(range_start, range_end, bounds="[)")),
            )
        )
    ).all()

    counts: dict[str, set[UUID]] = defaultdict(set)
    revenue: dict[str, int] = defaultdict(int)
    for bid, status, price, start_at in rows:
        if start_at is None:
            continue
        key = _bucket_key(start_at, tz, granularity)
        if metric == "bookings":
            counts[key].add(bid)
        elif metric == "revenue" and status == BookingStatus.COMPLETED.value:
            revenue[key] += int(price)

    if metric == "bookings":
        keys = sorted(counts.keys())
        return [{"period": k, "value": len(counts[k])} for k in keys]
    keys = sorted(revenue.keys())
    return [{"period": k, "value": revenue[k]} for k in keys]


async def top_services(
    session: AsyncSession, *, tenant_id: UUID, start_day: date, end_day: date, tz_name: str, limit: int = 5
) -> list[dict[str, object]]:
    tz = ZoneInfo(tz_name or "Europe/Moscow")
    start_day, end_day = _clamp_range(start_day, end_day)
    range_start, range_end = _range_bounds(start_day, end_day, tz)
    rows = (
        await session.execute(
            select(Service.name, func.count(BookingItem.id))
            .join(Service, Service.id == BookingItem.service_id)
            .join(Booking, Booking.id == BookingItem.booking_id)
            .where(
                Booking.tenant_id == tenant_id,
                Booking.status == BookingStatus.COMPLETED.value,
                BookingItem.during.overlaps(Range(range_start, range_end, bounds="[)")),
            )
            .group_by(Service.name)
            .order_by(func.count(BookingItem.id).desc())
            .limit(limit)
        )
    ).all()
    return [{"name": name, "count": int(cnt)} for name, cnt in rows]


async def staff_booking_counts(
    session: AsyncSession, *, tenant_id: UUID, start_day: date, end_day: date, tz_name: str
) -> list[dict[str, object]]:
    tz = ZoneInfo(tz_name or "Europe/Moscow")
    start_day, end_day = _clamp_range(start_day, end_day)
    range_start, range_end = _range_bounds(start_day, end_day, tz)
    rows = (
        await session.execute(
            select(StaffMember.display_name, func.count(func.distinct(Booking.id)))
            .select_from(BookingItem)
            .join(Booking, Booking.id == BookingItem.booking_id)
            .join(StaffMember, StaffMember.id == BookingItem.staff_member_id)
            .where(
                Booking.tenant_id == tenant_id,
                Booking.status == BookingStatus.COMPLETED.value,
                BookingItem.during.overlaps(Range(range_start, range_end, bounds="[)")),
            )
            .group_by(StaffMember.display_name)
            .order_by(func.count(func.distinct(Booking.id)).desc())
        )
    ).all()
    return [{"name": name, "count": int(cnt)} for name, cnt in rows]