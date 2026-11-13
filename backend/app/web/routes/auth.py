from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.jwt_auth import create_web_session_token
from app.core.settings import get_settings
from app.domain.active_role import UI_ROLE_LABELS, write_stored_ui_role
from app.domain.models import Branch, Tenant
from app.domain.services.cell_service import get_default_branch, work_day_hours
from app.domain.services.client_service import get_or_create_user_account, upsert_client_profile
from app.domain.services.web_auth_service import create_login_request, poll_login, start_param_for
from app.web.deps import WebContext, cookie_name, get_context, get_tenant, require_auth, writable
from app.web.ratelimit import limit_by_ip

router = APIRouter(prefix="/api/t/{tenant_public_id}", tags=["auth"])


def dev_login_enabled() -> bool:
    settings = get_settings()
    return settings.environment != "production" or settings.web_dev_login


def _set_session_cookie(response: Response, tenant: Tenant, user_id: UUID, name: str | None) -> None:
    settings = get_settings()
    token = create_web_session_token(
        tenant_public_id=tenant.public_id,
        user_account_id=user_id,
        name=name,
        days=settings.web_session_days,
    )
    response.set_cookie(
        cookie_name(tenant.public_id),
        token,
        max_age=settings.web_session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.web_cookie_secure,
        path="/",
    )


async def _tenant_info(session: AsyncSession, tenant: Tenant) -> dict[str, object]:
    branch: Branch = await get_default_branch(session, tenant)
    work_start, work_end = work_day_hours(tenant)
    return {
        "public_id": tenant.public_id,
        "name": tenant.name,
        "brand": tenant.brand or {},
        "bot_username": tenant.bot_username,
        "timezone": branch.timezone,
        "work_start": work_start,
        "work_end": work_end,
        "grid_step_minutes": int((tenant.rules or {}).get("grid_step_minutes", 30)),
        "dev_login": dev_login_enabled(),
        "read_only": tenant.subscription_status in {"expired", "suspended", "cancelled"},
    }


def _me_payload(ctx: WebContext) -> dict[str, object]:
    if not ctx.authenticated:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "name": ctx.display_name,
        "roles": [{"id": r, "label": UI_ROLE_LABELS[r]} for r in ctx.available_roles],
        "active_role": ctx.active_role,
        "is_staff": ctx.is_staff,
        "staff_member_id": str(ctx.staff.id) if ctx.staff else None,
        "client": {"name": ctx.client.name, "phone": ctx.client.phone} if ctx.client else None,
    }


@router.get("/info")
async def info(
    tenant: Tenant = Depends(get_tenant), session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    return await _tenant_info(session, tenant)


@router.post("/auth/start")
async def auth_start(request: Request, tenant: Tenant = Depends(get_tenant)) -> dict[str, object]:
    await limit_by_ip(request, "auth_start", limit=20)
    code = await create_login_request(tenant.public_id)
    bot_url = f"https://t.me/{tenant.bot_username}?start={start_param_for(code)}" if tenant.bot_username else None
    return {"code": code, "bot_url": bot_url, "expires_in": 300}


@router.get("/auth/poll")
async def auth_poll(
    response: Response,
    code: str = Query(min_length=8, max_length=64),
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    result = await poll_login(code, tenant_public_id=tenant.public_id)
    if result.state == "confirmed" and result.telegram_user_id is not None:
        user = await get_or_create_user_account(session, result.telegram_user_id)
        await session.commit()
        _set_session_cookie(response, tenant, user.id, result.display_name)
    return {"state": result.state}


class DevLogin(BaseModel):
    telegram_user_id: int
    name: str | None = None


@router.post("/auth/dev")
async def auth_dev(
    body: DevLogin,
    response: Response,
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if not dev_login_enabled():
        raise HTTPException(status_code=404, detail="not found")
    user = await get_or_create_user_account(session, body.telegram_user_id)
    await session.commit()
    _set_session_cookie(response, tenant, user.id, body.name)
    return {"state": "confirmed"}


@router.post("/auth/logout")
async def auth_logout(response: Response, tenant: Tenant = Depends(get_tenant)) -> dict[str, str]:
    response.delete_cookie(cookie_name(tenant.public_id), path="/")
    return {"state": "logged_out"}


@router.get("/me")
async def me(ctx: WebContext = Depends(get_context)) -> dict[str, object]:
    return _me_payload(ctx)


class RoleBody(BaseModel):
    role: str


@router.post("/me/role")
async def set_role(
    body: RoleBody,
    ctx: WebContext = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    if body.role not in ctx.available_roles:
        raise HTTPException(status_code=400, detail="role not available")
    if ctx.staff is not None:
        write_stored_ui_role(ctx.staff, body.role)  # type: ignore[arg-type]
        await session.commit()
        ctx.active_role = body.role  # type: ignore[assignment]
    return _me_payload(ctx)


class ProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)


@router.patch("/me/profile")
async def update_profile(
    body: ProfileBody,
    ctx: WebContext = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    assert ctx.user is not None
    profile = await upsert_client_profile(
        session,
        tenant_id=tenant.id,
        user_account_id=ctx.user.id,
        name=body.name.strip(),
        phone=body.phone,
        source="web",
    )
    await session.commit()
    ctx.client = profile
    return _me_payload(ctx)
