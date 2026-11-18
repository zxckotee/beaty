"""Schedule-based availability: work interval minus bookings yields client slots."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.slots import SlotRules, TimeInterval, compute_slots, subtract_busy


def test_free_day_yields_multiple_slot_starts() -> None:
    tz = ZoneInfo("Europe/Moscow")
    day = date(2030, 6, 3)
    work = [
        TimeInterval(
            datetime.combine(day, time(9, 0), tzinfo=tz).astimezone(UTC),
            datetime.combine(day, time(17, 0), tzinfo=tz).astimezone(UTC),
        )
    ]
    busy: list[TimeInterval] = []
    free = subtract_busy(work, busy)
    rules = SlotRules(grid_step_minutes=30, min_lead_time_minutes=0, horizon_days=30)
    now = work[0].start - timedelta(hours=1)
    slots = compute_slots(free, [], 45, rules, now=now)
    assert len(slots) >= 10


def test_one_booking_splits_morning_and_afternoon() -> None:
    tz = ZoneInfo("Europe/Moscow")
    day = date(2030, 6, 3)
    t9 = datetime.combine(day, time(9, 0), tzinfo=tz).astimezone(UTC)
    t17 = datetime.combine(day, time(17, 0), tzinfo=tz).astimezone(UTC)
    work = [TimeInterval(t9, t17)]
    busy = [TimeInterval(t9 + timedelta(hours=1), t9 + timedelta(hours=2))]
    free = subtract_busy(work, busy)
    rules = SlotRules(grid_step_minutes=30, min_lead_time_minutes=0, horizon_days=30)
    slots = compute_slots(free, [], 45, rules, now=t9 - timedelta(hours=1))
    starts = {s.start for s in slots}
    assert any(s < t9 + timedelta(hours=1) for s in starts)
    assert any(s >= t9 + timedelta(hours=2) for s in starts)


def test_segment_containing() -> None:
    from app.domain.services.availability_service import _segment_containing

    segs = [
        TimeInterval(datetime(2030, 1, 1, 9, tzinfo=UTC), datetime(2030, 1, 1, 12, tzinfo=UTC)),
        TimeInterval(datetime(2030, 1, 1, 14, tzinfo=UTC), datetime(2030, 1, 1, 18, tzinfo=UTC)),
    ]
    assert _segment_containing(segs, datetime(2030, 1, 1, 10, tzinfo=UTC)) is segs[0]
    assert _segment_containing(segs, datetime(2030, 1, 1, 13, tzinfo=UTC)) is None