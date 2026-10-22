"""Phase 3: one-way Google Calendar export for specialists."""

from uuid import UUID


async def export_staff_day_to_gcal(*, staff_member_id: UUID, ical_body: str) -> dict:
    return {"status": "not_implemented", "staff_member_id": str(staff_member_id), "bytes": len(ical_body)}
