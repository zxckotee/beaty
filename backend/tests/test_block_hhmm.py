"""Block interval wall-clock labels on multi-day ranges."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.web.serializers import hhmm_block_end, hhmm_block_start


def test_block_end_past_midnight_shows_24_00() -> None:
    tz = ZoneInfo("Europe/Moscow")
    view = date(2026, 11, 23)
    end = datetime.combine(view + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    assert hhmm_block_end(end, view, tz) == "24:00"


def test_block_start_continues_from_previous_day() -> None:
    tz = ZoneInfo("Europe/Moscow")
    view = date(2026, 11, 24)
    start = datetime.combine(view - timedelta(days=1), time(10), tzinfo=tz).astimezone(UTC)
    assert hhmm_block_start(start, view, tz) == "00:00"


def test_same_day_block_times_unchanged() -> None:
    tz = ZoneInfo("Europe/Moscow")
    view = date(2026, 11, 23)
    start = datetime.combine(view, time(10), tzinfo=tz).astimezone(UTC)
    end = datetime.combine(view, time(18), tzinfo=tz).astimezone(UTC)
    assert hhmm_block_start(start, view, tz) == "10:00"
    assert hhmm_block_end(end, view, tz) == "18:00"