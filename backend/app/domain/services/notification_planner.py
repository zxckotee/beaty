from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, Notification, NotificationStatus, NotificationType


async def plan_booking_notifications(
    session: AsyncSession,
    booking: Booking,
    *,
    start_at: datetime,
    tenant_rules: dict[str, Any],
) -> None:
    default_offsets: list[dict[str, Any]] = [
        {"type": NotificationType.REMINDER_24H.value, "hours_before": 24},
        {"type": NotificationType.REMINDER_2H.value, "hours_before": 2},
    ]
    raw_offsets = tenant_rules.get("reminder_offsets", default_offsets)
    offsets = raw_offsets if isinstance(raw_offsets, list) else default_offsets
    for off in offsets:
        hours = int(off["hours_before"])
        send_at = start_at - timedelta(hours=hours)
        ntype = off["type"]
        key = f"{booking.id}:{ntype}:{int(send_at.timestamp())}"
        session.add(
            Notification(
                tenant_id=booking.tenant_id,
                booking_id=booking.id,
                recipient_type="client",
                recipient_id=booking.client_profile_id,
                notification_type=ntype,
                send_at=send_at,
                idempotency_key=key,
                payload={"booking_id": str(booking.id)},
            )
        )
    confirm_key = f"{booking.id}:booking_confirmed:{int(datetime.now(UTC).timestamp())}"
    session.add(
        Notification(
            tenant_id=booking.tenant_id,
            booking_id=booking.id,
            recipient_type="client",
            recipient_id=booking.client_profile_id,
            notification_type=NotificationType.BOOKING_CONFIRMED.value,
            send_at=datetime.now(UTC),
            idempotency_key=confirm_key,
            payload={"booking_id": str(booking.id)},
        )
    )


async def cancel_booking_notifications(session: AsyncSession, booking_id: UUID) -> None:
    from sqlalchemy import update

    await session.execute(
        update(Notification)
        .where(Notification.booking_id == booking_id, Notification.status == NotificationStatus.PENDING.value)
        .values(status=NotificationStatus.CANCELLED.value)
    )
