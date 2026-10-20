from typing import Any

DEFAULT_TENANT_RULES: dict[str, Any] = {
    "grid_step_minutes": 30,
    "booking_horizon_days": 30,
    "min_lead_time_hours": 2,
    "cancel_deadline_hours": 12,
    "hold_ttl_seconds": 600,
    "quiet_hours": {"start": "22:00", "end": "08:00"},
    "reminder_offsets": [
        {"type": "reminder_24h", "hours_before": 24, "require_confirm": True},
        {"type": "reminder_2h", "hours_before": 2, "require_confirm": False},
    ],
}
