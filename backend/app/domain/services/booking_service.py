from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.audit import log_audit
from app.domain.cells import chain_items, first_fit_start, free_segments, price_total, total_block_minutes
from app.domain.exceptions import DoesNotFitError, ForbiddenError, NotFoundError, SlotTakenError
from app.domain.models import Booking, BookingEvent, BookingItem, BookingStatus, Service, Tenant
from app.domain.services.cell_service import (
    cell_allows,
    eligible_staff_needs,
    get_cell,
    lead_time_earliest,
    load_services,
    staff_busy,
)
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
        during=Range(start_at, end_at, bounds="[)"),
        blocked_during=Range(start_at, blocked_end, bounds="[)"),
        is_active=True,
    )
    session.add(item)

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


def _cancel_deadline_passed(tenant: Tenant, start_at: datetime) -> bool:
    rules = tenant.rules or {}
    hours = int(rules.get("cancel_deadline_hours", 12))
    return datetime.now(UTC) > start_at - timedelta(hours=hours)


async def reschedule_booking(
    session: AsyncSession,
    *,
    tenant: Tenant,
    booking_id: UUID,
    new_start_at: datetime,
    actor_user_id: UUID | None = None,
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant.id:
        raise NotFoundError("booking not found")
    if booking.status in (BookingStatus.CANCELLED.value, BookingStatus.COMPLETED.value):
        raise ForbiddenError("cannot reschedule")

    items = (
        await session.scalars(select(BookingItem).where(BookingItem.booking_id == booking.id))
    ).all()
    if not items:
        raise NotFoundError("booking items missing")
    item = items[0]
    row = await session.execute(
        text("SELECT lower(during) FROM booking_item WHERE id = :id"),
        {"id": str(item.id)},
    )
    old_start = row.scalar_one()
    if old_start and _cancel_deadline_passed(tenant, old_start):
        raise ForbiddenError("cancel/reschedule deadline passed")

    service = await session.get(Service, item.service_id)
    if service is None:
        raise NotFoundError("service not found")
    duration = item.duration_minutes or service.duration_minutes
    buffer = service.buffer_minutes
    end_at = new_start_at + timedelta(minutes=duration)
    blocked_end = end_at + timedelta(minutes=buffer)

    await _expire_overlapping_holds(session, item.staff_member_id, new_start_at, blocked_end)
    item.is_active = False
    await session.flush()

    new_item = BookingItem(
        tenant_id=tenant.id,
        booking_id=booking.id,
        staff_member_id=item.staff_member_id,
        service_id=item.service_id,
        price_cents=item.price_cents,
        duration_minutes=duration,
        during=Range(new_start_at, end_at, bounds="[)"),
        blocked_during=Range(new_start_at, blocked_end, bounds="[)"),
        is_active=True,
    )
    session.add(new_item)
    try:
        await session.flush()
    except Exception as exc:
        if "exclusion" in str(exc).lower() or "overlap" in str(exc).lower():
            raise SlotTakenError("slot already taken") from exc
        raise

    booking.reschedule_pending = False
    await cancel_booking_notifications(session, booking.id)
    await plan_booking_notifications(
        session, booking, start_at=new_start_at, tenant_rules=tenant.rules
    )
    session.add(
        BookingEvent(
            tenant_id=tenant.id,
            booking_id=booking.id,
            event_type="rescheduled",
            payload={"old_start": old_start.isoformat() if old_start else None, "new_start": new_start_at.isoformat()},
            actor_user_id=actor_user_id,
        )
    )
    return booking


async def confirm_visit(
    session: AsyncSession,
    *,
    tenant: Tenant,
    booking_id: UUID,
    actor_user_id: UUID | None = None,
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant.id:
        raise NotFoundError("booking not found")
    if booking.status not in (BookingStatus.BOOKED.value, BookingStatus.CONFIRMED.value):
        raise ForbiddenError("invalid status")
    booking.status = BookingStatus.CONFIRMED.value
    session.add(
        BookingEvent(
            tenant_id=tenant.id,
            booking_id=booking.id,
            event_type="visit_confirmed",
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
    skip_deadline_check: bool = False,
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant.id:
        raise NotFoundError("booking not found")

    if not skip_deadline_check:
        items = (
            await session.scalars(select(BookingItem).where(BookingItem.booking_id == booking.id))
        ).all()
        if items:
            row = await session.execute(
                text("SELECT lower(during) FROM booking_item WHERE id = :id"),
                {"id": str(items[0].id)},
            )
            start_at = row.scalar_one()
            if start_at and _cancel_deadline_passed(tenant, start_at):
                raise ForbiddenError("cancel deadline passed")

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
    items = (
        await session.scalars(select(BookingItem).where(BookingItem.booking_id == booking.id))
    ).all()
    if items:
        from app.domain.services.waitlist_service import pop_matching_waitlist

        await pop_matching_waitlist(
            session,
            tenant_id=tenant.id,
            service_id=items[0].service_id,
            staff_member_id=items[0].staff_member_id,
        )
    return booking


async def book_services_in_cell(
    session: AsyncSession,
    *,
    tenant: Tenant,
    cell_id: UUID,
    client_profile_id: UUID,
    service_ids: list[UUID],
    comment: str | None = None,
    actor_user_id: UUID | None = None,
    source: str = "web",
    enforce_lead_time: bool = True,
) -> Booking:
    """Book several services back to back inside one manager-defined cell.

    The cell row is locked so concurrent bookings of the same window are serialized; the
    database exclusion constraint on booking_item remains the last line of defence.
    """
    cell = await get_cell(session, tenant.id, cell_id, for_update=True)
    services = await load_services(session, tenant.id, service_ids)
    ids = [s.id for s in services]
    if not cell_allows(cell, ids):
        raise DoesNotFitError("cell does not offer these services")
    needs_by_staff = await eligible_staff_needs(
        session, tenant_id=tenant.id, services=services, staff_member_id=cell.staff_member_id
    )
    needs = needs_by_staff.get(cell.staff_member_id)
    if needs is None:
        raise DoesNotFitError("specialist does not perform all selected services")

    await _expire_overlapping_holds(session, cell.staff_member_id, cell.starts_at, cell.ends_at)
    busy = (
        await staff_busy(
            session,
            tenant_id=tenant.id,
            staff_ids=[cell.staff_member_id],
            range_start=cell.starts_at,
            range_end=cell.ends_at + timedelta(days=1),
        )
    )[cell.staff_member_id]
    segments = free_segments(cell.starts_at, cell.ends_at, busy)
    now = datetime.now(UTC)
    earliest = lead_time_earliest(tenant, now) if enforce_lead_time else now
    start = first_fit_start(segments, total_block_minutes(needs), earliest)
    if start is None:
        raise DoesNotFitError("selected services do not fit into the free time of this cell")

    planned = chain_items(start, needs)
    booking = Booking(
        tenant_id=tenant.id,
        branch_id=cell.branch_id,
        client_profile_id=client_profile_id,
        status=BookingStatus.BOOKED.value,
        source=source,
        comment=(comment or "").strip() or None,
        total_price_cents=price_total(needs, cell.price_cents),
    )
    session.add(booking)
    await session.flush()
    for item in planned:
        session.add(
            BookingItem(
                tenant_id=tenant.id,
                booking_id=booking.id,
                staff_member_id=cell.staff_member_id,
                service_id=item.service_id,
                cell_id=cell.id,
                price_cents=item.price_cents,
                duration_minutes=item.duration_minutes,
                during=Range(item.start, item.end, bounds="[)"),
                blocked_during=Range(item.start, item.blocked_end, bounds="[)"),
                is_active=True,
            )
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        if "no_specialist_overlap" in str(exc):
            raise SlotTakenError("slot already taken") from exc
        raise

    await plan_booking_notifications(session, booking, start_at=planned[0].start, tenant_rules=tenant.rules)
    session.add(
        BookingEvent(
            tenant_id=tenant.id,
            booking_id=booking.id,
            event_type="booked_in_cell",
            payload={"cell_id": str(cell.id), "start": planned[0].start.isoformat(), "source": source},
            actor_user_id=actor_user_id,
        )
    )
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="booking.created_in_cell",
        entity_type="booking",
        entity_id=booking.id,
        actor_user_id=actor_user_id,
    )
    return booking
