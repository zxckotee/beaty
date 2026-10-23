from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class TimeInterval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class SlotRules:
    grid_step_minutes: int = 30
    min_lead_time_minutes: int = 120
    horizon_days: int = 30


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime
    staff_member_id: UUID | None = None
