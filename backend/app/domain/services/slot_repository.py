from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.domain.models import (
    Booking,
    BookingItem,
    BookingStatus,
    Branch,
    ScheduleException,
    ScheduleTemplate,
    Service,
    SpecialistService,
    StaffMember,
)
from app.domain.slots import Slot, SlotRules, TimeInterval, compute_slots

ACTIVE_STATUSES = {
    BookingStatus.HELD.value,
    BookingStatus.BOOKED.value,
    BookingStatus.CONFIRMED.value,
    BookingStatus.ARRIVED.value,
}

DEFAULT_WEEKDAY_HOURS = (time(9, 0), time(18, 0))


def _slot_rules_from_tenant(rules: dict) -> SlotRules:
    return SlotRules(
        grid_step_minutes=int(rules.get("grid_step_minutes", 30)),
        min_lead_time_minutes=int(rules.get("min_lead_time_hours", 2)) * 60,
        horizon_days=int(rules.get("booking_horizon_days", 30)),
    )


def _combine_local(day: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, t, tzinfo=tz).astimezone(UTC)


async def _invalidate_slot_cache(tenant_id: UUID, staff_member_id: UUID) -> None:
    redis = await get_redis()
    pattern = f"slots:{tenant_id}:{staff_member_id}:*"
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        if keys:
            await redis.delete(*keys)
        if cursor == 0:
            break


async def invalidate_slots_for_staff(tenant_id: UUID, staff_member_id: UUID) -> None:
    await _invalidate_slot_cache(tenant_id, staff_member_id)


def _templates_for_weekday(
    templates: list[ScheduleTemplate], weekday: int
) -> list[tuple[time, time, time | None, time | None]]:
    rows: list[tuple[time, time, time | None, time | None]] = []
    for tpl in templates:
        if tpl.weekday != weekday:
            continue
        start = time.fromisoformat(tpl.start_time)
        end = time.fromisoformat(tpl.end_time)
        br_s = time.fromisoformat(tpl.break_start) if tpl.break_start else None
        br_e = time.fromisoformat(tpl.break_end) if tpl.break_end else None
        rows.append((start, end, br_s, br_e))
    return rows


def _work_intervals_for_day(
    day: date,
    tz: ZoneInfo,
    templates: list[ScheduleTemplate],
    holidays: list,
) -> list[TimeInterval]:
    day_iso = day.isoformat()
    if any(h.get("date") == day_iso for h in holidays if isinstance(h, dict)):
        return []

    weekday = day.weekday()
    tpl_rows = _templates_for_weekday(templates, weekday)
    if not tpl_rows:
        start_t, end_t = DEFAULT_WEEKDAY_HOURS
        tpl_rows = [(start_t, end_t, None, None)]

    intervals: list[TimeInterval] = []
    for start_t, end_t, br_s, br_e in tpl_rows:
        w_start = _combine_local(day, start_t, tz)
        w_end = _combine_local(day, end_t, tz)
        if w_end <= w_start:
            continue
        if br_s and br_e:
            intervals.append(TimeInterval(w_start, _combine_local(day, br_s, tz)))
            intervals.append(TimeInterval(_combine_local(day, br_e, tz), w_end))
        else:
            intervals.append(TimeInterval(w_start, w_end))
    return intervals


async def _busy_intervals(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    range_start: datetime,
    range_end: datetime,
) -> list[TimeInterval]:
    rows = await session.execute(
        text(
            """
            SELECT lower(bi.blocked_during) AS s, upper(bi.blocked_during) AS e
            FROM booking_item bi
            JOIN booking b ON b.id = bi.booking_id
            WHERE bi.tenant_id = :tenant_id
              AND bi.staff_member_id = :staff_id
              AND bi.is_active = true
              AND b.status = ANY(:statuses)
              AND bi.blocked_during && tstzrange(:start, :end, '[)')
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "staff_id": str(staff_member_id),
            "statuses": list(ACTIVE_STATUSES),
            "start": range_start,
            "end": range_end,
        },
    )
    busy: list[TimeInterval] = []
    for s, e in rows.all():
        if s and e:
            busy.append(TimeInterval(s, e))
    return busy


async def _exception_busy(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    range_start: datetime,
    range_end: datetime,
) -> list[TimeInterval]:
    rows = (
        await session.scalars(
            select(ScheduleException).where(
                ScheduleException.tenant_id == tenant_id,
                ScheduleException.staff_member_id == staff_member_id,
            )
        )
    ).all()
    busy: list[TimeInterval] = []
    for exc in rows:
        if exc.kind not in ("block", "vacation", "sick", "force_majeure"):
            continue
        row = await session.execute(
            text(
                "SELECT lower(during), upper(during) FROM schedule_exception WHERE id = :id"
            ),
            {"id": str(exc.id)},
        )
        s, e = row.one()
        if s and e and s < range_end and e > range_start:
            busy.append(TimeInterval(max(s, range_start), min(e, range_end)))
    return busy


async def list_available_slots(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    branch: Branch,
    service: Service,
    staff_member_id: UUID | None,
    rules: dict,
    limit: int = 50,
) -> list[Slot]:
    slot_rules = _slot_rules_from_tenant(rules)
    tz = ZoneInfo(branch.timezone or "Europe/Moscow")
    now = datetime.now(UTC)
    range_end = now + timedelta(days=slot_rules.horizon_days)

    staff_ids: list[UUID]
    if staff_member_id is not None:
        staff_ids = [staff_member_id]
    else:
        links = (
            await session.scalars(
                select(SpecialistService.staff_member_id).where(
                    SpecialistService.tenant_id == tenant_id,
                    SpecialistService.service_id == service.id,
                )
            )
        ).all()
        if links:
            staff_ids = list(links)
        else:
            staff_ids = [
                r.id
                for r in (
                    await session.scalars(
                        select(StaffMember).where(
                            StaffMember.tenant_id == tenant_id,
                            StaffMember.is_active.is_(True),
                        )
                    )
                ).all()
            ]

    duration = service.duration_minutes
    all_slots: list[Slot] = []

    for sid in staff_ids:
        link = await session.scalar(
            select(SpecialistService).where(
                SpecialistService.staff_member_id == sid,
                SpecialistService.service_id == service.id,
            )
        )
        if link and link.duration_minutes:
            duration = link.duration_minutes

        templates = (
            await session.scalars(
                select(ScheduleTemplate).where(
                    ScheduleTemplate.tenant_id == tenant_id,
                    ScheduleTemplate.staff_member_id == sid,
                )
            )
        ).all()

        work: list[TimeInterval] = []
        day = now.astimezone(tz).date()
        last_day = range_end.astimezone(tz).date()
        while day <= last_day:
            work.extend(
                _work_intervals_for_day(day, tz, list(templates), branch.holidays or [])
            )
            day += timedelta(days=1)

        busy = await _busy_intervals(
            session,
            tenant_id=tenant_id,
            staff_member_id=sid,
            range_start=now,
            range_end=range_end,
        )
        busy.extend(
            await _exception_busy(
                session,
                tenant_id=tenant_id,
                staff_member_id=sid,
                range_start=now,
                range_end=range_end,
            )
        )

        for slot in compute_slots(work, busy, duration, slot_rules, now=now):
            all_slots.append(
                Slot(start=slot.start, end=slot.end, staff_member_id=sid)
            )

    all_slots.sort(key=lambda s: s.start)
    return all_slots[:limit]
