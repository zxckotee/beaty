from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.client_routes import client_router
from app.api.deps import (
    get_current_user,
    get_tenant_by_public_id,
    resolve_staff_and_client,
)
from app.api.manager_routes import manager_router
from app.api.schemas import (
    AuthResponse,
    AuthTelegramRequest,
    BookingOut,
    HoldBookingRequest,
    MeResponse,
    ProfileUpdate,
    RescheduleRequest,
    ServiceOut,
    SlotOut,
    SpecialistOut,
)
from app.api.staff_routes import staff_router
from app.api.subscription_gate import assert_tenant_can_write
from app.core.context import UserContext
from app.core.crypto import decrypt_bot_token
from app.core.db import get_session
from app.core.jwt_auth import create_access_token, create_refresh_token, decode_refresh_token
from app.core.telegram_auth import verify_webapp_init_data
from app.domain.exceptions import DomainError, ForbiddenError, SlotTakenError
from app.domain.models import Branch, ClientProfile, Service, StaffMember
from app.domain.services.booking_service import cancel_booking, confirm_hold, hold_slot, reschedule_booking
from app.domain.services.client_service import get_or_create_user_account, register_client
from app.domain.services.slot_repository import list_available_slots

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(client_router)
api_router.include_router(manager_router)
api_router.include_router(staff_router)


class RefreshRequest(BaseModel):
    refresh_token: str
    tenant_public_id: str


class TenantBrandOut(BaseModel):
    name: str
    brand: dict
    rules: dict


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
        source="telegram",
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
    refresh = create_refresh_token(tenant_public_id=tenant.public_id, user_account_id=user.id)
    return AuthResponse(access_token=access, refresh_token=refresh)


@api_router.post("/auth/refresh", response_model=AuthResponse)
async def auth_refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> AuthResponse:
    tenant = await get_tenant_by_public_id(body.tenant_public_id, session)
    try:
        payload = decode_refresh_token(body.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    if payload.get("tenant") != tenant.public_id:
        raise HTTPException(status_code=401, detail="tenant mismatch")
    user_id = UUID(str(payload["sub"]))
    staff = await session.scalar(
        select(StaffMember).where(
            StaffMember.tenant_id == tenant.id,
            StaffMember.user_account_id == user_id,
        )
    )
    roles: list[str] = ["client"]
    if staff and staff.roles:
        roles = list(set(staff.roles) | {"client"})
    access = create_access_token(
        tenant_public_id=tenant.public_id,
        user_account_id=user_id,
        roles=roles,
    )
    refresh = create_refresh_token(tenant_public_id=tenant.public_id, user_account_id=user_id)
    return AuthResponse(access_token=access, refresh_token=refresh)


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
        subscription_status=tenant.subscription_status,
    )


@api_router.get("/tenant/brand", response_model=TenantBrandOut)
async def tenant_brand(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> TenantBrandOut:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    return TenantBrandOut(name=tenant.name, brand=tenant.brand or {}, rules=tenant.rules or {})


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
    service_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[SpecialistOut]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    if service_id:
        from app.domain.models import SpecialistService

        ids = (
            await session.scalars(
                select(SpecialistService.staff_member_id).where(
                    SpecialistService.tenant_id == tenant.id,
                    SpecialistService.service_id == service_id,
                )
            )
        ).all()
        if ids:
            rows = (
                await session.scalars(
                    select(StaffMember).where(StaffMember.id.in_(ids), StaffMember.is_active.is_(True))
                )
            ).all()
        else:
            rows = (
                await session.scalars(
                    select(StaffMember).where(
                        StaffMember.tenant_id == tenant.id,
                        StaffMember.is_active.is_(True),
                    )
                )
            ).all()
    else:
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
    branch_id = UUID(str((tenant.rules or {}).get("default_branch_id")))
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=500, detail="branch not configured")
    slots = await list_available_slots(
        session,
        tenant_id=tenant.id,
        branch=branch,
        service=service,
        staff_member_id=staff_member_id,
        rules=tenant.rules or {},
    )
    return [
        SlotOut(start=s.start, end=s.end, staff_member_id=s.staff_member_id) for s in slots
    ]


@api_router.post("/bookings/hold", response_model=BookingOut)
async def api_hold_booking(
    body: HoldBookingRequest,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> BookingOut:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        raise HTTPException(status_code=400, detail="client profile required")
    branch_id = UUID(str((tenant.rules or {}).get("default_branch_id")))
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=500, detail="branch not configured")
    staff_id = body.staff_member_id
    start_at = body.start_at
    if staff_id is None:
        service = await session.get(Service, body.service_id)
        if service is None:
            raise HTTPException(status_code=404, detail="service not found")
        slots = await list_available_slots(
            session,
            tenant_id=tenant.id,
            branch=branch,
            service=service,
            staff_member_id=None,
            rules=tenant.rules or {},
            limit=1,
        )
        if not slots or slots[0].staff_member_id is None:
            raise HTTPException(status_code=409, detail="no slots available")
        staff_id = slots[0].staff_member_id
        start_at = slots[0].start
    try:
        booking = await hold_slot(
            session,
            tenant=tenant,
            branch_id=branch_id,
            client_profile_id=user.client_profile_id,
            staff_member_id=staff_id,
            service_id=body.service_id,
            start_at=start_at,
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
    assert_tenant_can_write(tenant)
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
    assert_tenant_can_write(tenant)
    try:
        await cancel_booking(
            session,
            tenant=tenant,
            booking_id=booking_id,
            reason="client_cancel",
            actor_user_id=user.user_account_id,
        )
        await session.commit()
    except (DomainError, ForbiddenError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "cancelled"}


@api_router.post("/bookings/{booking_id}/reschedule", response_model=BookingOut)
async def api_reschedule_booking(
    booking_id: UUID,
    body: RescheduleRequest,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> BookingOut:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    try:
        booking = await reschedule_booking(
            session,
            tenant=tenant,
            booking_id=booking_id,
            new_start_at=body.start_at,
            actor_user_id=user.user_account_id,
        )
        await session.commit()
    except (SlotTakenError, DomainError, ForbiddenError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BookingOut(
        id=booking.id,
        status=booking.status,
        total_price_cents=booking.total_price_cents,
        hold_expires_at=booking.hold_expires_at,
    )


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
    rows = await session.execute(
        text(
            """
            SELECT b.id, b.status, b.total_price_cents, b.hold_expires_at,
                   lower(bi.during) AS start_at, upper(bi.during) AS end_at,
                   s.id AS service_id, s.name AS service_name, sm.display_name AS staff_name
            FROM booking b
            LEFT JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            LEFT JOIN service s ON s.id = bi.service_id
            LEFT JOIN staff_member sm ON sm.id = bi.staff_member_id
            WHERE b.tenant_id = :tenant_id AND b.client_profile_id = :client_id
            ORDER BY start_at DESC NULLS LAST
            """
        ),
        {"tenant_id": str(tenant.id), "client_id": str(user.client_profile_id)},
    )
    return [
        BookingOut(
            id=r.id,
            status=r.status,
            total_price_cents=r.total_price_cents,
            hold_expires_at=r.hold_expires_at,
            start_at=r.start_at,
            end_at=r.end_at,
            service_id=r.service_id,
            service_name=r.service_name,
            staff_name=r.staff_name,
        )
        for r in rows.all()
    ]


@api_router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
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
