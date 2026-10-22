from datetime import UTC, datetime, timedelta

from app.domain.slots.types import Slot, SlotRules, TimeInterval


def subtract_busy(work: list[TimeInterval], busy: list[TimeInterval]) -> list[TimeInterval]:
    free = list(work)
    for b in sorted(busy, key=lambda x: x.start):
        next_free: list[TimeInterval] = []
        for w in free:
            if b.end <= w.start or b.start >= w.end:
                next_free.append(w)
                continue
            if w.start < b.start:
                next_free.append(TimeInterval(w.start, b.start))
            if b.end < w.end:
                next_free.append(TimeInterval(b.end, w.end))
        free = next_free
    return free


def align_to_grid(dt: datetime, step_minutes: int) -> datetime:
    minute = (dt.minute // step_minutes) * step_minutes
    return dt.replace(minute=minute, second=0, microsecond=0)


def compute_slots(
    work_intervals: list[TimeInterval],
    busy_intervals: list[TimeInterval],
    total_duration_minutes: int,
    rules: SlotRules,
    now: datetime | None = None,
) -> list[Slot]:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    earliest = now + timedelta(minutes=rules.min_lead_time_minutes)
    latest = now + timedelta(days=rules.horizon_days)
    free = subtract_busy(work_intervals, busy_intervals)
    slots: list[Slot] = []

    for interval in free:
        cursor = align_to_grid(interval.start, rules.grid_step_minutes)
        if cursor < interval.start:
            cursor += timedelta(minutes=rules.grid_step_minutes)
        while cursor + timedelta(minutes=total_duration_minutes) <= interval.end:
            end = cursor + timedelta(minutes=total_duration_minutes)
            if cursor >= earliest and cursor <= latest:
                slots.append(Slot(start=cursor, end=end))
            cursor += timedelta(minutes=rules.grid_step_minutes)
    return slots
