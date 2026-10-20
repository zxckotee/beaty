from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, BookingItem


async def declare_unavailable(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    start: datetime,
    end: datetime,
    reason: str,
) -> list[UUID]:
    """Mark affected bookings as reschedule_pending (MVP)."""
    rows = await session.execute(
        select(Booking.id)
        .join(BookingItem, BookingItem.booking_id == Booking.id)
        .where(
            Booking.tenant_id == tenant_id,
            BookingItem.staff_member_id == staff_member_id,
            BookingItem.is_active.is_(True),
            Booking.status.in_(["booked", "confirmed"]),
        )
    )
    booking_ids = [r[0] for r in rows.all()]
    if booking_ids:
        await session.execute(
            update(Booking)
            .where(Booking.id.in_(booking_ids))
            .values(reschedule_pending=True)
        )
    return booking_ids
