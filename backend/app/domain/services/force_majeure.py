from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, BookingItem, Branch, Service, SpecialistService
from app.domain.services.slot_repository import list_available_slots


async def declare_unavailable(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    start: datetime,
    end: datetime,
    reason: str,
) -> list[UUID]:
    """Mark affected bookings and store resolution options in booking_event payload."""
    from app.domain.services.schedule_service import add_exception

    await add_exception(
        session,
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        kind="force_majeure",
        start=start,
        end=end,
        note=reason,
        actor_user_id=None,
    )

    rows = await session.execute(
        text(
            """
            SELECT DISTINCT b.id
            FROM booking b
            JOIN booking_item bi ON bi.booking_id = b.id
            WHERE b.tenant_id = :tenant_id
              AND bi.staff_member_id = :staff_id
              AND bi.is_active = true
              AND b.status IN ('booked', 'confirmed')
              AND bi.during && tstzrange(:start, :end, '[)')
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "staff_id": str(staff_member_id),
            "start": start,
            "end": end,
        },
    )
    booking_ids = [UUID(str(r[0])) for r in rows.all()]
    for bid in booking_ids:
        await session.execute(
            update(Booking).where(Booking.id == bid).values(reschedule_pending=True)
        )
        options = await build_resolution_options(
            session, tenant_id=tenant_id, booking_id=bid, unavailable_staff_id=staff_member_id
        )
        from app.domain.models import BookingEvent

        session.add(
            BookingEvent(
                tenant_id=tenant_id,
                booking_id=bid,
                event_type="force_majeure_options",
                payload={"options": options},
            )
        )
    return booking_ids


async def build_resolution_options(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    booking_id: UUID,
    unavailable_staff_id: UUID,
) -> list[dict[str, Any]]:
    from app.domain.models import Tenant

    booking = await session.get(Booking, booking_id)
    if booking is None:
        return []
    tenant = await session.get(Tenant, tenant_id)
    rules = (tenant.rules or {}) if tenant else {}
    branch = await session.get(Branch, booking.branch_id)
    items = (
        await session.scalars(select(BookingItem).where(BookingItem.booking_id == booking_id))
    ).all()
    if not items or branch is None:
        return []
    item = items[0]
    service = await session.get(Service, item.service_id)
    if service is None:
        return []
    row = await session.execute(
        text("SELECT lower(during) FROM booking_item WHERE id = :id"),
        {"id": str(item.id)},
    )
    original_start = row.scalar_one()
    options: list[dict[str, Any]] = []

    alts = (
        await session.scalars(
            select(SpecialistService.staff_member_id).where(
                SpecialistService.tenant_id == tenant_id,
                SpecialistService.service_id == service.id,
                SpecialistService.staff_member_id != unavailable_staff_id,
            )
        )
    ).all()
    for alt_staff in alts[:3]:
        slots = await list_available_slots(
            session,
            tenant_id=tenant_id,
            branch=branch,
            service=service,
            staff_member_id=alt_staff,
            rules=rules,
            limit=3,
        )
        for slot in slots:
            if original_start and abs((slot.start - original_start).total_seconds()) < 7200:
                options.append(
                    {
                        "type": "other_staff",
                        "staff_member_id": str(alt_staff),
                        "start_at": slot.start.isoformat(),
                    }
                )
                break

    same_slots = await list_available_slots(
        session,
        tenant_id=tenant_id,
        branch=branch,
        service=service,
        staff_member_id=unavailable_staff_id,
        rules=rules,
        limit=5,
    )
    for slot in same_slots[:2]:
        options.append(
            {
                "type": "same_staff",
                "staff_member_id": str(unavailable_staff_id),
                "start_at": slot.start.isoformat(),
            }
        )
    options.append({"type": "cancel"})
    return options


async def apply_force_majeure_choice(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    booking_id: UUID,
    choice: dict[str, Any],
    actor_user_id: UUID | None,
) -> None:
    from app.domain.models import Tenant
    from app.domain.services.booking_service import cancel_booking, reschedule_booking

    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return
    if choice.get("type") == "cancel":
        await cancel_booking(
            session,
            tenant=tenant,
            booking_id=booking_id,
            reason="force_majeure",
            actor_user_id=actor_user_id,
            skip_deadline_check=True,
        )
    elif choice.get("start_at"):
        from datetime import UTC

        start = datetime.fromisoformat(str(choice["start_at"]))
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        await reschedule_booking(
            session,
            tenant=tenant,
            booking_id=booking_id,
            new_start_at=start,
            actor_user_id=actor_user_id,
        )
