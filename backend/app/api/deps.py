from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.db import apply_tenant_rls, get_session
from app.core.jwt_auth import decode_access_token
from app.domain.models import ClientProfile, StaffMember, Tenant


async def get_tenant_by_public_id(
    tenant_public_id: str,
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return tenant


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    if payload.get("typ") == "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token type")
    roles = payload.get("roles") or []
    tenant_claim = payload.get("tenant")
    return UserContext(
        user_account_id=UUID(str(payload["sub"])),
        telegram_user_id=None,
        roles=set(roles) if isinstance(roles, (list, set)) else set(),
        token_tenant_public_id=str(tenant_claim) if tenant_claim else None,
    )


async def bind_api_tenant(
    session: AsyncSession,
    tenant: Tenant,
    user: UserContext,
) -> UserContext:
    if not user.token_tenant_public_id or user.token_tenant_public_id != tenant.public_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant mismatch")
    await apply_tenant_rls(session, tenant.id)
    return await resolve_staff_and_client(session, tenant, user)


async def prepare_api_tenant_user(
    tenant_public_id: str,
    session: AsyncSession,
    user: UserContext,
) -> tuple[Tenant, UserContext]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await bind_api_tenant(session, tenant, user)
    return tenant, user


def require_role(*allowed: str):
    async def _dep(
        tenant_public_id: str = Query(...),
        session: AsyncSession = Depends(get_session),
        user: UserContext = Depends(get_current_user),
    ) -> UserContext:
        tenant = await get_tenant_by_public_id(tenant_public_id, session)
        user = await bind_api_tenant(session, tenant, user)
        if not user.has_role(*allowed):
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return _dep


def require_tenant_staff(*allowed: str):
    """Staff-only: must belong to the tenant and have one of the allowed roles."""

    async def _dep(
        tenant_public_id: str = Query(...),
        session: AsyncSession = Depends(get_session),
        user: UserContext = Depends(get_current_user),
    ) -> UserContext:
        tenant = await get_tenant_by_public_id(tenant_public_id, session)
        user = await bind_api_tenant(session, tenant, user)
        if user.staff_member_id is None:
            raise HTTPException(status_code=403, detail="forbidden")
        if not user.has_role(*allowed):
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return _dep


async def resolve_staff_and_client(
    session: AsyncSession,
    tenant: Tenant,
    user: UserContext,
) -> UserContext:
    user.roles = set()
    if user.user_account_id:
        staff = await session.scalar(
            select(StaffMember).where(
                StaffMember.tenant_id == tenant.id,
                StaffMember.user_account_id == user.user_account_id,
                StaffMember.is_active.is_(True),
            )
        )
        if staff:
            user.staff_member_id = staff.id
            user.roles.update(staff.roles or [])
            if "specialist" not in user.roles:
                user.roles.add("specialist")
        client = await session.scalar(
            select(ClientProfile).where(
                ClientProfile.tenant_id == tenant.id,
                ClientProfile.user_account_id == user.user_account_id,
            )
        )
        if client:
            user.client_profile_id = client.id
            user.roles.add("client")
    return user