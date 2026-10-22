from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.audit import log_audit
from app.domain.exceptions import ForbiddenError, NotFoundError, SlotTakenError
from app.domain.models import Booking, BookingEvent, BookingItem, BookingStatus, Service, Tenant
from app.domain.services.notification_planner import (
    cancel_booking_notifications,
    plan_booking_notifications,
)


async def _expire_overlapping_holds(
    session: AsyncSession,
    staff_member_id: UUID,
    blocked_start: datetime,
    blocked_end: datetime,
) -> None:
    await session.execute(
        text(
            """
            UPDATE booking_item bi
            SET is_active = false
            FROM booking b
            WHERE bi.booking_id = b.id
              AND b.status = 'held'
              AND (b.hold_expires_at IS NULL OR b.hold_expires_at < now())
              AND bi.staff_member_id = :staff_id
              AND bi.blocked_during && tstzrange(:start, :end, '[)')
            """
        ),
        {"staff_id": str(staff_member_id), "start": blocked_start, "end": blocked_end},
    )


async def hold_slot(
    session: AsyncSession,
    *,
    tenant: Tenant,
    branch_id: UUID,
    client_profile_id: UUID,
    staff_member_id: UUID,
    service_id: UUID,
    start_at: datetime,
    actor_user_id: UUID | None = None,
) -> Booking:
    service = await session.get(Service, service_id)
    if service is None or service.tenant_id != tenant.id:
        raise NotFoundError("service not found")

    duration = service.duration_minutes
    buffer = service.buffer_minutes
    end_at = start_at + timedelta(minutes=duration)
    blocked_end = end_at + timedelta(minutes=buffer)
    hold_ttl = int(tenant.rules.get("hold_ttl_seconds", get_settings().hold_ttl_seconds))

    await _expire_overlapping_holds(session, staff_member_id, start_at, blocked_end)

    booking = Booking(
        tenant_id=tenant.id,
        branch_id=branch_id,
        client_profile_id=client_profile_id,
        status=BookingStatus.HELD.value,
        total_price_cents=service.price_cents,
        hold_expires_at=datetime.now(UTC) + timedelta(seconds=hold_ttl),
    )
    session.add(booking)
    await session.flush()

    item = BookingItem(
        tenant_id=tenant.id,
        booking_id=booking.id,
        staff_member_id=staff_member_id,
        service_id=service_id,
        price_cents=service.price_cents,
        duration_minutes=duration,
        is_active=True,
    )
    session.add(item)
    await session.flush()

    await session.execute(
        text(
            """
            UPDATE booking_item
            SET during = tstzrange(:during_start, :during_end, '[)'),
                blocked_during = tstzrange(:blocked_start, :blocked_end, '[)')
            WHERE id = :item_id
            """
        ),
        {
            "item_id": str(item.id),
            "during_start": start_at,
            "during_end": end_at,
            "blocked_start": start_at,
            "blocked_end": blocked_end,
        },
    )

    try:
        await session.flush()
    except Exception as exc:
        if "exclusion" in str(exc).lower() or "overlap" in str(exc).lower():
            raise SlotTakenError("slot already taken") from exc
        raise

    session.add(
        BookingEvent(
            tenant_id=tenant.id,
            booking_id=booking.id,
            event_type="held",
            payload={"start": start_at.isoformat()},
            actor_user_id=actor_user_id,
        )
    )
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="booking.held",
        entity_type="booking",
        entity_id=booking.id,
        actor_user_id=actor_user_id,
    )
    return booking


async def confirm_hold(
    session: AsyncSession,
    *,
    tenant: Tenant,
    booking_id: UUID,
    actor_user_id: UUID | None = None,
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant.id:
        raise NotFoundError("booking not found")
    if booking.status != BookingStatus.HELD.value:
        raise ForbiddenError("booking is not on hold")

    booking.status = BookingStatus.BOOKED.value
    booking.hold_expires_at = None
    items = (
        await session.scalars(select(BookingItem).where(BookingItem.booking_id == booking.id))
    ).all()
    start_at = None
    if items:
        row = await session.execute(
            text("SELECT lower(during) FROM booking_item WHERE id = :id"),
            {"id": str(items[0].id)},
        )
        start_at = row.scalar_one()

    if start_at is not None:
        await plan_booking_notifications(session, booking, start_at=start_at, tenant_rules=tenant.rules)

    session.add(
        BookingEvent(
            tenant_id=tenant.id,
            booking_id=booking.id,
            event_type="confirmed",
            actor_user_id=actor_user_id,
        )
    )
    return booking


async def cancel_booking(
    session: AsyncSession,
    *,
    tenant: Tenant,
    booking_id: UUID,
    reason: str,
    actor_user_id: UUID | None = None,
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant.id:
        raise NotFoundError("booking not found")

    booking.status = BookingStatus.CANCELLED.value
    await session.execute(
        update(BookingItem).where(BookingItem.booking_id == booking.id).values(is_active=False)
    )
    await cancel_booking_notifications(session, booking.id)
    session.add(
        BookingEvent(
            tenant_id=tenant.id,
            booking_id=booking.id,
            event_type="cancelled",
            payload={"reason": reason},
            actor_user_id=actor_user_id,
        )
    )
    return booking
