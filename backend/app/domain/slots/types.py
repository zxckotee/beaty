from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeInterval:
    start: datetime
    end: datetime

    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class SlotRules:
    grid_step_minutes: int
    min_lead_time_minutes: int
    horizon_days: int


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime
    staff_member_id: str | None = None
