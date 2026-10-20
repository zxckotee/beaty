from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_tenant_by_public_id,
    require_role,
    resolve_staff_and_client,
)
from app.api.schemas import (
    AuthResponse,
    AuthTelegramRequest,
    BookingOut,
    BookingStatusUpdate,
    HoldBookingRequest,
    MeResponse,
    ProfileUpdate,
    ServiceOut,
    SlotOut,
    SpecialistOut,
)
from app.core.context import UserContext
from app.core.crypto import decrypt_bot_token
from app.core.db import get_session
from app.core.jwt_auth import create_access_token
from app.core.telegram_auth import verify_webapp_init_data
from app.domain.exceptions import DomainError, SlotTakenError
from app.domain.models import Booking, ClientProfile, Service, StaffMember
from app.domain.services.booking_service import cancel_booking, confirm_hold, hold_slot
from app.domain.services.client_service import get_or_create_user_account, register_client
from app.domain.slots import SlotRules, TimeInterval, compute_slots

api_router = APIRouter(prefix="/api/v1")


@api_router.post("/auth/telegram", response_model=AuthResponse)
async def auth_telegram(body: AuthTelegramRequest, session: AsyncSession = Depends(get_session)) -> AuthResponse:
    tenant = await get_tenant_by_public_id(body.tenant_public_id, session)
    if not tenant.bot_token_encrypted:
        raise HTTPException(status_code=400, detail="tenant bot not configured")
    token = decrypt_bot_token(tenant.bot_token_encrypted)
    try:
        parsed = verify_webapp_init_data(body.init_data, token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user_data = parsed.get("user")
    if not isinstance(user_data, dict):
        raise HTTPException(status_code=400, detail="user missing in init data")
    tg_id = int(user_data["id"])
    user = await get_or_create_user_account(session, tg_id)
    await register_client(
        session,
        tenant_id=tenant.id,
        user_account_id=user.id,
        name=user_data.get("first_name", "Client"),
        phone=str(tg_id),
        source="miniapp",
    )
    staff = await session.scalar(
        select(StaffMember).where(
            StaffMember.tenant_id == tenant.id,
            StaffMember.user_account_id == user.id,
        )
    )
    roles: list[str] = ["client"]
    if staff and staff.roles:
        roles = list(set(staff.roles) | {"client"})
    await session.commit()
    access = create_access_token(
        tenant_public_id=tenant.public_id,
        user_account_id=user.id,
        roles=roles,
    )
    return AuthResponse(access_token=access)


@api_router.get("/me", response_model=MeResponse)
async def me(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> MeResponse:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await resolve_staff_and_client(session, tenant, user)
    return MeResponse(
        user_account_id=user.user_account_id,  # type: ignore[arg-type]
        roles=sorted(user.roles),
        client_profile_id=user.client_profile_id,
        staff_member_id=user.staff_member_id,
        tenant_public_id=tenant.public_id,
        tenant_name=tenant.name,
        brand=tenant.brand or {},
    )


@api_router.get("/services", response_model=list[ServiceOut])
async def list_services(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[ServiceOut]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    rows = (
        await session.scalars(
            select(Service).where(Service.tenant_id == tenant.id, Service.is_active.is_(True))
        )
    ).all()
    return [
        ServiceOut(
            id=r.id,
            name=r.name,
            price_cents=r.price_cents,
            duration_minutes=r.duration_minutes,
            category_id=r.category_id,
        )
        for r in rows
    ]


@api_router.get("/specialists", response_model=list[SpecialistOut])
async def list_specialists(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[SpecialistOut]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    rows = (
        await session.scalars(
            select(StaffMember).where(
                StaffMember.tenant_id == tenant.id,
                StaffMember.is_active.is_(True),
            )
        )
    ).all()
    return [
        SpecialistOut(id=r.id, display_name=r.display_name, photo_url=r.photo_url) for r in rows
    ]


@api_router.get("/slots", response_model=list[SlotOut])
async def list_slots(
    tenant_public_id: str = Query(...),
    service_id: UUID = Query(...),
    staff_member_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[SlotOut]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    service = await session.get(Service, service_id)
    if service is None or service.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="service not found")
    rules = tenant.rules or {}
    slot_rules = SlotRules(
        grid_step_minutes=int(rules.get("grid_step_minutes", 30)),
        min_lead_time_minutes=int(rules.get("min_lead_time_hours", 2)) * 60,
        horizon_days=int(rules.get("booking_horizon_days", 30)),
    )
    now = datetime.now(UTC)
    work = [TimeInterval(now.replace(hour=9, minute=0), now.replace(hour=18, minute=0))]
    slots = compute_slots(work, [], service.duration_minutes, slot_rules, now=now)
    return [
        SlotOut(start=s.start, end=s.end, staff_member_id=staff_member_id) for s in slots[:20]
    ]


@api_router.post("/bookings/hold", response_model=BookingOut)
async def api_hold_booking(
    body: HoldBookingRequest,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> BookingOut:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        raise HTTPException(status_code=400, detail="client profile required")
    branch_id = UUID(str((tenant.rules or {}).get("default_branch_id")))
    try:
        booking = await hold_slot(
            session,
            tenant=tenant,
            branch_id=branch_id,
            client_profile_id=user.client_profile_id,
            staff_member_id=body.staff_member_id,
            service_id=body.service_id,
            start_at=body.start_at,
            actor_user_id=user.user_account_id,
        )
        await session.commit()
    except SlotTakenError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BookingOut(
        id=booking.id,
        status=booking.status,
        total_price_cents=booking.total_price_cents,
        hold_expires_at=booking.hold_expires_at,
    )


@api_router.post("/bookings/{booking_id}/confirm", response_model=BookingOut)
async def api_confirm_booking(
    booking_id: UUID,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> BookingOut:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    try:
        booking = await confirm_hold(
            session,
            tenant=tenant,
            booking_id=booking_id,
            actor_user_id=user.user_account_id,
        )
        await session.commit()
    except DomainError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BookingOut(
        id=booking.id,
        status=booking.status,
        total_price_cents=booking.total_price_cents,
        hold_expires_at=booking.hold_expires_at,
    )


@api_router.delete("/bookings/{booking_id}")
async def api_cancel_booking(
    booking_id: UUID,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    try:
        await cancel_booking(
            session,
            tenant=tenant,
            booking_id=booking_id,
            reason="client_cancel",
            actor_user_id=user.user_account_id,
        )
        await session.commit()
    except DomainError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "cancelled"}


@api_router.get("/bookings/mine", response_model=list[BookingOut])
async def my_bookings(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> list[BookingOut]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        return []
    rows = (
        await session.scalars(
            select(Booking).where(
                Booking.tenant_id == tenant.id,
                Booking.client_profile_id == user.client_profile_id,
            )
        )
    ).all()
    return [
        BookingOut(
            id=b.id,
            status=b.status,
            total_price_cents=b.total_price_cents,
            hold_expires_at=b.hold_expires_at,
        )
        for b in rows
    ]


@api_router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        raise HTTPException(status_code=404, detail="profile not found")
    profile = await session.get(ClientProfile, user.client_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if body.name:
        profile.name = body.name
    if body.phone:
        profile.phone = body.phone
    await session.commit()
    return {"status": "ok"}


manager_router = APIRouter(prefix="/manager", tags=["manager"])


@manager_router.get("/calendar")
async def manager_calendar(
    tenant_public_id: str = Query(...),
    _: UserContext = Depends(require_role("manager", "owner")),
) -> dict:
    return {"items": []}


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


staff_router = APIRouter(prefix="/staff", tags=["staff"])


@staff_router.get("/day")
async def staff_day(
    tenant_public_id: str = Query(...),
    user: UserContext = Depends(require_role("specialist", "manager", "owner")),
) -> dict:
    return {"bookings": [], "staff_member_id": str(user.staff_member_id) if user.staff_member_id else None}


@staff_router.post("/unavailable")
async def staff_unavailable(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_role("specialist", "manager", "owner")),
) -> dict:
    from datetime import UTC, datetime, timedelta

    from app.domain.services.force_majeure import declare_unavailable

    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    if user.staff_member_id is None:
        raise HTTPException(status_code=400, detail="staff profile required")
    start = datetime.now(UTC)
    end = start + timedelta(hours=4)
    ids = await declare_unavailable(
        session,
        tenant_id=tenant.id,
        staff_member_id=user.staff_member_id,
        start=start,
        end=end,
        reason="force_majeure",
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
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="booking not found")
    booking.status = body.status
    await session.commit()
    return {"status": booking.status}
