from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_by_public_id, require_role, resolve_staff_and_client
from app.api.schemas import BookingStatusUpdate
from app.api.subscription_gate import assert_tenant_can_write
from app.core.context import UserContext
from app.core.db import get_session
from app.domain.models import Booking, BookingStatus
from app.domain.services.force_majeure import declare_unavailable

staff_router = APIRouter(prefix="/staff", tags=["staff"])


class UnavailableBody(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    reason: str = "force_majeure"


class StaffBookingOut(BaseModel):
    booking_id: UUID
    client_name: str
    service_name: str
    start_at: datetime
    end_at: datetime
    status: str
    comment: str | None


@staff_router.get("/day", response_model=list[StaffBookingOut])
async def staff_day(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("specialist", "manager", "owner")),
) -> list[StaffBookingOut]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.staff_member_id is None:
        return []
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    rows = await session.execute(
        text(
            """
            SELECT b.id, b.status, b.comment,
                   cp.name AS client_name, s.name AS service_name,
                   lower(bi.during) AS start_at, upper(bi.during) AS end_at
            FROM booking b
            JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            JOIN client_profile cp ON cp.id = b.client_profile_id
            JOIN service s ON s.id = bi.service_id
            WHERE b.tenant_id = :tenant_id
              AND bi.staff_member_id = :staff_id
              AND bi.during && tstzrange(:start, :end, '[)')
              AND b.status NOT IN ('cancelled')
            ORDER BY start_at
            """
        ),
        {
            "tenant_id": str(tenant.id),
            "staff_id": str(user.staff_member_id),
            "start": day_start,
            "end": day_end,
        },
    )
    return [
        StaffBookingOut(
            booking_id=r.id,
            client_name=r.client_name,
            service_name=r.service_name,
            start_at=r.start_at,
            end_at=r.end_at,
            status=r.status,
            comment=r.comment,
        )
        for r in rows.all()
    ]


@staff_router.post("/unavailable")
async def staff_unavailable(
    body: UnavailableBody,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("specialist", "manager", "owner")),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.staff_member_id is None:
        raise HTTPException(status_code=400, detail="staff profile required")
    start = body.start_at or datetime.now(UTC)
    end = body.end_at or (start + timedelta(hours=4))
    ids = await declare_unavailable(
        session,
        tenant_id=tenant.id,
        staff_member_id=user.staff_member_id,
        start=start,
        end=end,
        reason=body.reason,
    )
    await session.commit()
    return {"affected_bookings": [str(i) for i in ids]}


@staff_router.post("/bookings/{booking_id}/status")
async def staff_booking_status(
    booking_id: UUID,
    body: BookingStatusUpdate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("specialist", "manager", "owner")),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="booking not found")
    allowed = {
        "arrived": BookingStatus.ARRIVED.value,
        "completed": BookingStatus.COMPLETED.value,
        "no_show": BookingStatus.NO_SHOW.value,
    }
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail="invalid status")
    booking.status = allowed[body.status]
    if booking.status == BookingStatus.COMPLETED.value:
        from app.domain.services.revisit_service import schedule_revisit_for_completed_booking

        await schedule_revisit_for_completed_booking(
            session, tenant_id=tenant.id, booking_id=booking.id
        )
    await session.commit()
    return {"status": booking.status}
