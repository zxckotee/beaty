from datetime import UTC, datetime, timedelta

from app.domain.slots import SlotRules, TimeInterval, compute_slots


def test_compute_slots_respects_duration_and_grid() -> None:
    day = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    work = [TimeInterval(day, day + timedelta(hours=8))]
    busy = [TimeInterval(day + timedelta(hours=2), day + timedelta(hours=3))]
    rules = SlotRules(grid_step_minutes=30, min_lead_time_minutes=0, horizon_days=7)
    now = day - timedelta(hours=1)
    slots = compute_slots(work, busy, total_duration_minutes=60, rules=rules, now=now)
    assert all((s.end - s.start) == timedelta(minutes=60) for s in slots)
    assert not any(s.start >= day + timedelta(hours=2) and s.start < day + timedelta(hours=3) for s in slots)


def test_min_lead_time() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    work = [TimeInterval(now.replace(hour=9), now.replace(hour=18))]
    rules = SlotRules(grid_step_minutes=30, min_lead_time_minutes=120, horizon_days=7)
    slots = compute_slots(work, [], total_duration_minutes=30, rules=rules, now=now)
    assert all(s.start >= now + timedelta(minutes=120) for s in slots)
