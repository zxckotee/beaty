"""«Пора снова» — plan notifications based on service.revisit_days."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, BookingItem, BookingStatus, Notification, Service


async def schedule_revisit_for_completed_booking(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    booking_id: UUID,
) -> None:
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.status != BookingStatus.COMPLETED.value:
        return
    item = await session.scalar(
        select(BookingItem).where(BookingItem.booking_id == booking_id, BookingItem.is_active.is_(False))
    )
    if item is None:
        item = await session.scalar(select(BookingItem).where(BookingItem.booking_id == booking_id))
    if item is None:
        return
    service = await session.get(Service, item.service_id)
    if service is None or not service.revisit_days:
        return
    send_at = datetime.now(UTC) + timedelta(days=service.revisit_days)
    key = f"revisit:{booking_id}"
    session.add(
        Notification(
            tenant_id=tenant_id,
            booking_id=booking_id,
            recipient_type="client",
            recipient_id=booking.client_profile_id,
            notification_type="revisit",
            send_at=send_at,
            idempotency_key=key,
            payload={"service_id": str(service.id), "service_name": service.name},
        )
    )
