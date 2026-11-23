from __future__ import annotations

import json
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_bot_token
from app.core.db import get_session
from app.core.jwt_auth import create_web_session_token
from app.core.redis_client import get_redis
from app.core.settings import get_settings
from app.core.webapp_auth import verify_webapp_init_data
from app.domain.active_role import UI_ROLE_LABELS, write_stored_ui_role
from app.messenger.types import Channel
from app.domain.models import Branch, Tenant
from app.domain.services.cell_service import get_default_branch, work_day_hours
from app.domain.services.client_service import get_or_create_user_by_messenger, upsert_client_profile
from app.domain.services.landing_service import get_or_create_landing
from app.domain.services.web_auth_service import create_login_request, poll_login, start_param_for
from app.web.deps import WebContext, cookie_name, get_context, get_tenant, require_auth, writable
from app.web.dev_login import resolve_telegram_user_id
from app.web.ratelimit import limit_by_ip

router = APIRouter(prefix="/api/t/{tenant_public_id}", tags=["auth"])


def dev_login_enabled() -> bool:
    settings = get_settings()
    if settings.environment == "production":
        return False
    if settings.environment == "test":
        return True
    return settings.web_dev_login


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
    landing = await get_or_create_landing(session, tenant.id)
    return {
        "public_id": tenant.public_id,
        "name": tenant.name,
        "brand": tenant.brand or {},
        "bot_username": tenant.bot_username,
        "max_bot_username": tenant.max_bot_username,
        "telegram_linked": bool(tenant.bot_token_encrypted),
        "max_linked": bool(tenant.max_bot_token_encrypted),
        "timezone": branch.timezone,
        "work_start": work_start,
        "work_end": work_end,
        "grid_step_minutes": int((tenant.rules or {}).get("grid_step_minutes", 30)),
        "avatar_url": landing.avatar_url,
        **({"dev_login": True} if dev_login_enabled() else {}),
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


def _telegram_deep_link(tenant: Tenant, code: str) -> str | None:
    if not tenant.bot_username:
        return None
    payload = quote(start_param_for(code), safe="")
    return f"https://t.me/{tenant.bot_username}?start={payload}"


def _max_deep_link(tenant: Tenant, code: str) -> str | None:
    if not tenant.max_bot_username:
        return None
    payload = quote(start_param_for(code), safe="")
    return f"https://max.ru/{tenant.max_bot_username}?startapp={payload}"


@router.post("/auth/start")
async def auth_start(request: Request, tenant: Tenant = Depends(get_tenant)) -> dict[str, object]:
    await limit_by_ip(request, "auth_start", limit=20)
    code = await create_login_request(tenant.public_id)
    bot_url = _telegram_deep_link(tenant, code)
    max_url = _max_deep_link(tenant, code)
    return {
        "code": code,
        "bot_url": bot_url,
        "max_bot_url": max_url,
        "telegram_go": f"/api/t/{tenant.public_id}/auth/telegram-go?code={quote(code, safe='')}",
        "max_go": f"/api/t/{tenant.public_id}/auth/max-go?code={quote(code, safe='')}",
        "expires_in": 300,
    }


@router.get("/auth/telegram-go")
async def telegram_go(
    code: str = Query(min_length=8, max_length=64),
    tenant: Tenant = Depends(get_tenant),
) -> Response:
    """Redirect into Telegram with the one-time login payload (open from the site, then START BOT)."""
    if not tenant.bot_username:
        raise HTTPException(status_code=503, detail="bot not linked")
    redis = await get_redis()
    raw = await redis.get(f"weblogin:{code}")
    if raw is None:
        raise HTTPException(status_code=410, detail="login code expired; start again from the website")
    data = json.loads(raw)
    if data.get("tenant") != tenant.public_id or data.get("status") not in {"pending", "confirmed"}:
        raise HTTPException(status_code=410, detail="login code expired; start again from the website")
    url = _telegram_deep_link(tenant, code)
    assert url is not None
    return RedirectResponse(url, status_code=302)


@router.get("/auth/max-go")
async def max_go(
    code: str = Query(min_length=8, max_length=64),
    tenant: Tenant = Depends(get_tenant),
) -> Response:
    if not tenant.max_bot_username:
        raise HTTPException(status_code=503, detail="MAX bot not linked")
    redis = await get_redis()
    raw = await redis.get(f"weblogin:{code}")
    if raw is None:
        raise HTTPException(status_code=410, detail="login code expired; start again from the website")
    data = json.loads(raw)
    if data.get("tenant") != tenant.public_id or data.get("status") not in {"pending", "confirmed"}:
        raise HTTPException(status_code=410, detail="login code expired; start again from the website")
    url = _max_deep_link(tenant, code)
    assert url is not None
    return RedirectResponse(url, status_code=302)


@router.get("/auth/poll")
async def auth_poll(
    response: Response,
    code: str = Query(min_length=8, max_length=64),
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    result = await poll_login(code, tenant_public_id=tenant.public_id)
    if result.state == "confirmed" and result.messenger_user_id is not None:
        channel = result.channel or Channel.TELEGRAM
        user = await get_or_create_user_by_messenger(session, channel, result.messenger_user_id)
        await session.commit()
        _set_session_cookie(response, tenant, user.id, result.display_name)
    return {"state": result.state}


class DevLogin(BaseModel):
    telegram_user_id: int | None = None
    identifier: str | None = None
    name: str | None = None


class WebAppAuthBody(BaseModel):
    init_data: str = Field(min_length=1, max_length=4096)


class TelegramWebAppAuth(WebAppAuthBody):
    pass


@router.post("/auth/telegram")
async def auth_telegram(
    body: TelegramWebAppAuth,
    response: Response,
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Exchange Telegram WebApp initData for a session cookie (Mini App login)."""
    if not tenant.bot_token_encrypted:
        raise HTTPException(status_code=503, detail="bot not linked")
    bot_token = decrypt_bot_token(tenant.bot_token_encrypted)
    try:
        parsed = verify_webapp_init_data(body.init_data, bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = parsed.get("user")
    if not isinstance(user, dict) or "id" not in user:
        raise HTTPException(status_code=400, detail="missing user in init data")
    telegram_user_id = int(user["id"])
    display_name = user.get("first_name") or user.get("username")
    account = await get_or_create_user_by_messenger(session, Channel.TELEGRAM, telegram_user_id)
    await session.commit()
    _set_session_cookie(response, tenant, account.id, display_name)
    return {"state": "confirmed"}


@router.post("/auth/max")
async def auth_max(
    body: WebAppAuthBody,
    response: Response,
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if not tenant.max_bot_token_encrypted:
        raise HTTPException(status_code=503, detail="MAX bot not linked")
    bot_token = decrypt_bot_token(tenant.max_bot_token_encrypted)
    try:
        parsed = verify_webapp_init_data(body.init_data, bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = parsed.get("user")
    if not isinstance(user, dict) or "id" not in user:
        raise HTTPException(status_code=400, detail="missing user in init data")
    max_user_id = int(user["id"])
    display_name = user.get("first_name") or user.get("username")
    account = await get_or_create_user_by_messenger(session, Channel.MAX, max_user_id)
    await session.commit()
    _set_session_cookie(response, tenant, account.id, display_name)
    return {"state": "confirmed"}


@router.post("/auth/dev")
async def auth_dev(
    body: DevLogin,
    response: Response,
    tenant: Tenant = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if not dev_login_enabled():
        raise HTTPException(status_code=404, detail="not found")
    if body.telegram_user_id is not None and not body.identifier:
        telegram_user_id, auto_name = body.telegram_user_id, None
    elif body.identifier:
        telegram_user_id, auto_name = await resolve_telegram_user_id(tenant, body.identifier)
    elif body.telegram_user_id is not None:
        telegram_user_id, auto_name = body.telegram_user_id, None
    else:
        raise HTTPException(status_code=400, detail="telegram_user_id or identifier required")
    user = await get_or_create_user_by_messenger(session, Channel.TELEGRAM, telegram_user_id)
    await session.commit()
    _set_session_cookie(response, tenant, user.id, body.name or auto_name)
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
