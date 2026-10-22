from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.db import get_session
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
    roles = payload.get("roles") or []
    return UserContext(
        user_account_id=UUID(payload["sub"]),
        telegram_user_id=None,
        roles=set(roles),
    )


def require_role(*allowed: str):
    async def _dep(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.has_role(*allowed):
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return _dep


async def resolve_staff_and_client(
    session: AsyncSession,
    tenant: Tenant,
    user: UserContext,
) -> UserContext:
    if user.user_account_id:
        staff = await session.scalar(
            select(StaffMember).where(
                StaffMember.tenant_id == tenant.id,
                StaffMember.user_account_id == user.user_account_id,
            )
        )
        if staff:
            user.staff_member_id = staff.id
            user.roles.update(staff.roles or [])
        client = await session.scalar(
            select(ClientProfile).where(
                ClientProfile.tenant_id == tenant.id,
                ClientProfile.user_account_id == user.user_account_id,
            )
        )
        if client:
            user.client_profile_id = client.id
    return user
