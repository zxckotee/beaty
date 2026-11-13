from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.cells import (
    ServiceNeed,
    chain_items,
    first_fit_start,
    free_segments,
    price_total,
    total_block_minutes,
    total_duration_minutes,
)

T0 = datetime(2030, 1, 10, 10, 0, tzinfo=UTC)


def need(duration: int, buffer: int = 0, price: int = 1000) -> ServiceNeed:
    return ServiceNeed(uuid4(), "svc", duration, buffer, price)


def test_totals_include_buffers() -> None:
    needs = [need(30, 10, 500), need(45, 0, 700)]
    assert total_duration_minutes(needs) == 75
    assert total_block_minutes(needs) == 85
    assert price_total(needs) == 1200
    assert price_total(needs, 300) == 1500
    assert price_total(needs, -5000) == 0


def test_free_segments_empty_cell() -> None:
    segs = free_segments(T0, T0 + timedelta(hours=3), [])
    assert [(s.start, s.end) for s in segs] == [(T0, T0 + timedelta(hours=3))]


def test_free_segments_with_busy_in_the_middle() -> None:
    end = T0 + timedelta(hours=4)
    busy = [(T0 + timedelta(hours=1), T0 + timedelta(hours=2))]
    segs = free_segments(T0, end, busy)
    assert [(s.start, s.end) for s in segs] == [
        (T0, T0 + timedelta(hours=1)),
        (T0 + timedelta(hours=2), end),
    ]


def test_free_segments_fully_busy() -> None:
    assert free_segments(T0, T0 + timedelta(hours=1), [(T0 - timedelta(hours=1), T0 + timedelta(hours=2))]) == []


def test_first_fit_exact_boundary_fits() -> None:
    segs = free_segments(T0, T0 + timedelta(minutes=90), [])
    assert first_fit_start(segs, 90) == T0
    assert first_fit_start(segs, 91) is None


def test_first_fit_skips_too_small_segment() -> None:
    busy = [(T0 + timedelta(minutes=30), T0 + timedelta(minutes=60))]
    segs = free_segments(T0, T0 + timedelta(hours=3), busy)
    assert first_fit_start(segs, 45) == T0 + timedelta(minutes=60)


def test_first_fit_respects_earliest_and_rounds_up() -> None:
    segs = free_segments(T0, T0 + timedelta(hours=2), [])
    earliest = T0 + timedelta(minutes=12, seconds=30)
    assert first_fit_start(segs, 60) == T0
    assert first_fit_start(segs, 60, earliest) == T0 + timedelta(minutes=15)
    late = T0 + timedelta(minutes=70)
    assert first_fit_start(segs, 60, late) is None


def test_first_fit_zero_need() -> None:
    assert first_fit_start(free_segments(T0, T0 + timedelta(hours=1), []), 0) is None


def test_chain_items_places_services_back_to_back() -> None:
    needs = [need(30, 10), need(20, 0)]
    items = chain_items(T0, needs)
    assert items[0].start == T0
    assert items[0].end == T0 + timedelta(minutes=30)
    assert items[0].blocked_end == T0 + timedelta(minutes=40)
    assert items[1].start == items[0].blocked_end
    assert items[1].blocked_end == T0 + timedelta(minutes=60)
