from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.subscription_gate import assert_tenant_can_write
from app.core.db import get_session
from app.core.jwt_auth import decode_web_session_token
from app.domain.active_role import (
    UiRole,
    available_ui_roles,
    read_stored_ui_role,
    resolve_active_ui_role,
)
from app.domain.models import ClientProfile, StaffMember, Tenant, UserAccount

MANAGER_ROLES = frozenset({"owner", "manager"})


def cookie_name(tenant_public_id: str) -> str:
    return f"bs_{tenant_public_id}"


@dataclass
class WebContext:
    tenant: Tenant
    user: UserAccount | None = None
    display_name: str = ""
    staff: StaffMember | None = None
    client: ClientProfile | None = None
    granted_roles: set[str] = field(default_factory=set)
    available_roles: list[UiRole] = field(default_factory=list)
    active_role: UiRole = "client"

    @property
    def authenticated(self) -> bool:
        return self.user is not None

    @property
    def is_manager(self) -> bool:
        return bool(self.granted_roles & MANAGER_ROLES)

    @property
    def is_staff(self) -> bool:
        return self.staff is not None


async def get_tenant(tenant_public_id: str, session: AsyncSession = Depends(get_session)) -> Tenant:
    tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return tenant


async def get_context(
    request: Request,
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> WebContext:
    ctx = WebContext(tenant=tenant)
    token = request.cookies.get(cookie_name(tenant.public_id))
    if not token:
        return ctx
    try:
        payload = decode_web_session_token(token)
        if payload.get("tenant") != tenant.public_id:
            return ctx
        user_id = UUID(str(payload["sub"]))
    except Exception:
        return ctx
    user = await session.get(UserAccount, user_id)
    if user is None:
        return ctx

    ctx.user = user
    ctx.display_name = str(payload.get("name") or "")
    ctx.staff = await session.scalar(
        select(StaffMember).where(
            StaffMember.tenant_id == tenant.id,
            StaffMember.user_account_id == user.id,
            StaffMember.is_active.is_(True),
        )
    )
    ctx.client = await session.scalar(
        select(ClientProfile).where(
            ClientProfile.tenant_id == tenant.id,
            ClientProfile.user_account_id == user.id,
        )
    )
    ctx.granted_roles = {"client"}
    if ctx.staff:
        ctx.granted_roles.update(ctx.staff.roles or [])
        ctx.granted_roles.add("specialist")
        ctx.display_name = ctx.staff.display_name
    elif ctx.client:
        ctx.display_name = ctx.client.name or ctx.display_name
    ctx.available_roles = available_ui_roles(granted_roles=ctx.granted_roles, has_staff_profile=ctx.staff is not None)
    ctx.active_role = resolve_active_ui_role(read_stored_ui_role(ctx.staff), ctx.available_roles)
    return ctx


async def require_auth(ctx: WebContext = Depends(get_context)) -> WebContext:
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    return ctx


async def require_staff(ctx: WebContext = Depends(require_auth)) -> WebContext:
    if not ctx.is_staff:
        raise HTTPException(status_code=403, detail="forbidden")
    return ctx


async def require_manager(ctx: WebContext = Depends(require_auth)) -> WebContext:
    if not ctx.is_manager or ctx.staff is None:
        raise HTTPException(status_code=403, detail="forbidden")
    return ctx


def writable(ctx: WebContext) -> Tenant:
    """Tenant to mutate; blocks writes when the subscription is inactive."""
    assert_tenant_can_write(ctx.tenant)
    return ctx.tenant
