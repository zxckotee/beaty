from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_by_public_id, require_role
from app.api.subscription_gate import assert_tenant_can_write
from app.core.context import UserContext
from app.core.db import get_session
from app.domain.exceptions import DomainError, SlotTakenError
from app.domain.models import (
    Booking,
    Branch,
    ClientProfile,
    Service,
    StaffMember,
)
from app.domain.services.booking_service import confirm_hold, hold_slot
from app.domain.services.catalog_service import apply_catalog_template
from app.domain.services.schedule_service import ensure_default_schedule, replace_weekly_template

manager_router = APIRouter(prefix="/manager", tags=["manager"])


class CalendarItemOut(BaseModel):
    booking_id: UUID
    client_name: str
    service_name: str
    staff_member_id: UUID
    staff_name: str
    start_at: datetime
    end_at: datetime
    status: str
    reschedule_pending: bool


class ServiceCreate(BaseModel):
    name: str
    price_cents: int
    duration_minutes: int = 30
    category_id: UUID | None = None


class StaffCreate(BaseModel):
    display_name: str
    roles: list[str] = Field(default_factory=lambda: ["specialist"])


class ManualBookingCreate(BaseModel):
    staff_member_id: UUID
    service_id: UUID
    start_at: datetime
    client_name: str
    client_phone: str | None = None
    client_profile_id: UUID | None = None


class ScheduleRow(BaseModel):
    weekday: int
    start_time: str
    end_time: str
    break_start: str | None = None
    break_end: str | None = None


class BrandUpdate(BaseModel):
    brand: dict | None = None
    rules: dict | None = None


@manager_router.get("/calendar", response_model=list[CalendarItemOut])
async def manager_calendar(
    tenant_public_id: str = Query(...),
    day: str | None = Query(default=None, description="YYYY-MM-DD in branch TZ"),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("manager", "owner", "reception")),
) -> list[CalendarItemOut]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    branch_id = UUID(str((tenant.rules or {}).get("default_branch_id")))
    branch = await session.get(Branch, branch_id)
    tz_name = branch.timezone if branch else "Europe/Moscow"
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    if day:
        local_day = datetime.fromisoformat(day).date()
    else:
        local_day = datetime.now(tz).date()
    day_start = datetime.combine(local_day, datetime.min.time(), tzinfo=tz).astimezone(UTC)
    day_end = day_start + timedelta(days=1)

    rows = await session.execute(
        text(
            """
            SELECT b.id, b.status, b.reschedule_pending,
                   cp.name AS client_name,
                   s.name AS service_name,
                   sm.id AS staff_id, sm.display_name AS staff_name,
                   lower(bi.during) AS start_at, upper(bi.during) AS end_at
            FROM booking b
            JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            JOIN client_profile cp ON cp.id = b.client_profile_id
            JOIN service s ON s.id = bi.service_id
            JOIN staff_member sm ON sm.id = bi.staff_member_id
            WHERE b.tenant_id = :tenant_id
              AND bi.during && tstzrange(:start, :end, '[)')
              AND b.status NOT IN ('cancelled')
            ORDER BY start_at
            """
        ),
        {"tenant_id": str(tenant.id), "start": day_start, "end": day_end},
    )
    return [
        CalendarItemOut(
            booking_id=r.id,
            client_name=r.client_name,
            service_name=r.service_name,
            staff_member_id=r.staff_id,
            staff_name=r.staff_name,
            start_at=r.start_at,
            end_at=r.end_at,
            status=r.status,
            reschedule_pending=bool(r.reschedule_pending),
        )
        for r in rows.all()
    ]


@manager_router.post("/bookings/manual")
async def manual_booking(
    body: ManualBookingCreate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("manager", "owner", "reception")),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    branch_id = UUID(str((tenant.rules or {}).get("default_branch_id")))
    if body.client_profile_id:
        profile = await session.get(ClientProfile, body.client_profile_id)
        if profile is None or profile.tenant_id != tenant.id:
            raise HTTPException(status_code=404, detail="client not found")
        client_id = profile.id
    else:
        profile = ClientProfile(
            tenant_id=tenant.id,
            name=body.client_name,
            phone=body.client_phone,
            source="manual",
        )
        session.add(profile)
        await session.flush()
        client_id = profile.id

    try:
        booking = await hold_slot(
            session,
            tenant=tenant,
            branch_id=branch_id,
            client_profile_id=client_id,
            staff_member_id=body.staff_member_id,
            service_id=body.service_id,
            start_at=body.start_at,
            actor_user_id=user.user_account_id,
        )
        booking = await confirm_hold(
            session,
            tenant=tenant,
            booking_id=booking.id,
            actor_user_id=user.user_account_id,
        )
        await session.commit()
    except (SlotTakenError, DomainError) as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"booking_id": str(booking.id), "status": booking.status}


@manager_router.get("/services")
async def manager_list_services(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("manager", "owner")),
) -> list[dict]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    rows = (
        await session.scalars(select(Service).where(Service.tenant_id == tenant.id))
    ).all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "price_cents": s.price_cents,
            "duration_minutes": s.duration_minutes,
            "is_active": s.is_active,
        }
        for s in rows
    ]


@manager_router.post("/services")
async def manager_create_service(
    body: ServiceCreate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("manager", "owner")),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    svc = Service(
        tenant_id=tenant.id,
        category_id=body.category_id,
        name=body.name,
        price_cents=body.price_cents,
        duration_minutes=body.duration_minutes,
    )
    session.add(svc)
    await session.commit()
    return {"id": str(svc.id)}


@manager_router.get("/staff")
async def manager_list_staff(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("manager", "owner")),
) -> list[dict]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    rows = (
        await session.scalars(select(StaffMember).where(StaffMember.tenant_id == tenant.id))
    ).all()
    return [
        {
            "id": str(s.id),
            "display_name": s.display_name,
            "roles": s.roles,
            "is_active": s.is_active,
        }
        for s in rows
    ]


@manager_router.post("/staff")
async def manager_create_staff(
    body: StaffCreate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("manager", "owner")),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    staff = StaffMember(
        tenant_id=tenant.id,
        display_name=body.display_name,
        roles=body.roles,
    )
    session.add(staff)
    await session.flush()
    await ensure_default_schedule(session, tenant_id=tenant.id, staff_member_id=staff.id)
    await session.commit()
    return {"id": str(staff.id)}


@manager_router.put("/staff/{staff_member_id}/schedule")
async def manager_set_schedule(
    staff_member_id: UUID,
    rows: list[ScheduleRow],
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("manager", "owner")),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    await replace_weekly_template(
        session,
        tenant_id=tenant.id,
        staff_member_id=staff_member_id,
        rows=[r.model_dump() for r in rows],
        actor_user_id=user.user_account_id,
    )
    await session.commit()
    return {"status": "ok"}


@manager_router.patch("/settings")
async def manager_settings(
    body: BrandUpdate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("manager", "owner")),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    if body.brand is not None:
        tenant.brand = {**(tenant.brand or {}), **body.brand}
    if body.rules is not None:
        tenant.rules = {**(tenant.rules or {}), **body.rules}
    await session.commit()
    return {"status": "ok"}


@manager_router.post("/catalog/apply-template")
async def manager_apply_template(
    template_name: str = Query(...),
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("manager", "owner")),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    await apply_catalog_template(session, tenant_id=tenant.id, template_name=template_name)
    await session.commit()
    return {"status": "ok"}


@manager_router.get("/reschedule-pending")
async def reschedule_pending(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("manager", "owner")),
) -> list[dict]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    rows = (
        await session.scalars(
            select(Booking).where(
                Booking.tenant_id == tenant.id,
                Booking.reschedule_pending.is_(True),
            )
        )
    ).all()
    return [{"id": str(b.id), "status": b.status} for b in rows]
