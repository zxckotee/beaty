from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import Range

from app.domain.models import ScheduleException, ScheduleTemplate
from app.domain.services.slot_repository import (
    WORK_OVERRIDE_KIND,
    _work_intervals_for_day,
)
from app.domain.slots import TimeInterval


def test_weekday_without_template_row_is_day_off_when_templates_exist() -> None:
    tz = ZoneInfo("Europe/Moscow")
    templates = [
        ScheduleTemplate(
            tenant_id=None,  # type: ignore[arg-type]
            staff_member_id=None,  # type: ignore[arg-type]
            weekday=0,
            start_time="09:00",
            end_time="18:00",
        ),
    ]
    monday = date(2026, 6, 1)  # Monday
    tuesday = date(2026, 6, 2)
    assert _work_intervals_for_day(monday, tz, templates, []) != []
    assert _work_intervals_for_day(tuesday, tz, templates, []) == []


def test_empty_templates_use_default_hours() -> None:
    tz = ZoneInfo("Europe/Moscow")
    day = date(2026, 6, 3)
    work = _work_intervals_for_day(day, tz, [], [])
    assert len(work) == 1
    assert int((work[0].end - work[0].start).total_seconds()) == 9 * 3600


def test_work_override_replaces_weekly_template() -> None:
    tz = ZoneInfo("Europe/Moscow")
    day = date(2026, 6, 1)
    templates = [
        ScheduleTemplate(
            tenant_id=None,  # type: ignore[arg-type]
            staff_member_id=None,  # type: ignore[arg-type]
            weekday=0,
            start_time="09:00",
            end_time="18:00",
        ),
    ]
    start = datetime.combine(day, time(12, 0), tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day, time(16, 0), tzinfo=tz).astimezone(UTC)
    override = ScheduleException(
        tenant_id=None,  # type: ignore[arg-type]
        staff_member_id=None,  # type: ignore[arg-type]
        kind=WORK_OVERRIDE_KIND,
        during=Range(start, end, bounds="[)"),
    )
    work = _work_intervals_for_day(day, tz, templates, [], [override])
    assert len(work) == 1
    assert work[0] == TimeInterval(start, end)