"""Pure helpers: does a set of services fit into a manager-defined time cell.

No database and no Telegram here, so the bot and the web cabinet share the exact same rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.domain.slots.engine import subtract_busy
from app.domain.slots.types import TimeInterval

START_ROUNDING_MINUTES = 5


@dataclass(frozen=True)
class ServiceNeed:
    """One service as performed by a concrete specialist (overrides already applied)."""

    service_id: UUID
    name: str
    duration_minutes: int
    buffer_minutes: int
    price_cents: int

    @property
    def block_minutes(self) -> int:
        return self.duration_minutes + self.buffer_minutes


@dataclass(frozen=True)
class PlannedItem:
    service_id: UUID
    start: datetime
    end: datetime
    blocked_end: datetime
    price_cents: int
    duration_minutes: int


def total_duration_minutes(needs: Sequence[ServiceNeed]) -> int:
    return sum(n.duration_minutes for n in needs)


def total_block_minutes(needs: Sequence[ServiceNeed]) -> int:
    """Time the specialist is occupied: every service plus the buffer after it."""
    return sum(n.block_minutes for n in needs)


def price_total(needs: Sequence[ServiceNeed], adjustment_cents: int | None = None) -> int:
    return max(0, sum(n.price_cents for n in needs) + (adjustment_cents or 0))


def free_segments(
    cell_start: datetime,
    cell_end: datetime,
    busy: Sequence[tuple[datetime, datetime]],
) -> list[TimeInterval]:
    """Parts of the cell not covered by busy intervals, in chronological order."""
    if cell_end <= cell_start:
        return []
    free = subtract_busy(
        [TimeInterval(cell_start, cell_end)],
        [TimeInterval(s, e) for s, e in busy if e > s],
    )
    return sorted(free, key=lambda seg: seg.start)


def _round_up(dt: datetime, step_minutes: int) -> datetime:
    base = dt.replace(second=0, microsecond=0)
    if base < dt:
        base += timedelta(minutes=1)
    extra = (-base.minute) % step_minutes
    return base + timedelta(minutes=extra)


def first_fit_start(
    segments: Sequence[TimeInterval],
    need_minutes: int,
    earliest: datetime | None = None,
) -> datetime | None:
    """Earliest start so that ``need_minutes`` fit into one free segment, or None."""
    if need_minutes <= 0:
        return None
    need = timedelta(minutes=need_minutes)
    for seg in segments:
        start = seg.start
        if earliest is not None and earliest > start:
            start = _round_up(earliest, START_ROUNDING_MINUTES)
        if start + need <= seg.end:
            return start
    return None


def chain_items(start: datetime, needs: Sequence[ServiceNeed]) -> list[PlannedItem]:
    """Lay services one after another; each next one starts when the previous block ends."""
    items: list[PlannedItem] = []
    cursor = start
    for need in needs:
        end = cursor + timedelta(minutes=need.duration_minutes)
        blocked_end = end + timedelta(minutes=need.buffer_minutes)
        items.append(
            PlannedItem(
                service_id=need.service_id,
                start=cursor,
                end=end,
                blocked_end=blocked_end,
                price_cents=need.price_cents,
                duration_minutes=need.duration_minutes,
            )
        )
        cursor = blocked_end
    return items
