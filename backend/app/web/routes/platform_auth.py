"""Telegram Login Widget auth for the public platform landing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.user_guide import PLATFORM_BOT_USERNAME, tg_platform_url
from app.core.db import get_session
from app.core.settings import get_settings
from app.core.telegram_auth import verify_telegram_login_widget
from app.domain.services.client_service import get_or_create_user_account
from app.domain.services.provisioning import find_owned_tenant_for_telegram_user
from app.web.ratelimit import limit_by_ip
from app.web.routes.auth import _set_session_cookie

router = APIRouter(tags=["platform-auth"])


class TelegramLoginWidgetBody(BaseModel):
    id: int
    first_name: str = Field(min_length=1, max_length=255)
    auth_date: int
    hash: str = Field(min_length=1, max_length=128)
    last_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=64)
    photo_url: str | None = Field(default=None, max_length=512)


@router.post("/api/platform/auth/telegram-login")
async def platform_telegram_login(
    body: TelegramLoginWidgetBody,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    await limit_by_ip(request, "platform_tg_login", limit=30)
    settings = get_settings()
    token = (settings.platform_bot_token or "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="telegram login is not configured")
    payload = body.model_dump(mode="json", exclude_none=True)
    try:
        verify_telegram_login_widget(payload, token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    account = await get_or_create_user_account(session, body.id)
    tenant = await find_owned_tenant_for_telegram_user(session, body.id)
    if tenant is None:
        await session.commit()
        return {
            "state": "no_tenant",
            "redirect": tg_platform_url(),
            "message": "Подключите салон в @beaty_welcome_agent",
        }

    display = body.first_name
    if body.last_name:
        display = f"{body.first_name} {body.last_name}".strip()
    _set_session_cookie(response, tenant, account.id, display)
    await session.commit()
    return {
        "state": "authenticated",
        "redirect": f"/t/{tenant.public_id}/#/dashboard",
        "tenant_public_id": tenant.public_id,
    }


@router.get("/api/platform/telegram-login-config")
async def platform_telegram_login_config() -> dict[str, object]:
    settings = get_settings()
    enabled = bool((settings.platform_bot_token or "").strip())
    return {
        "bot_username": PLATFORM_BOT_USERNAME,
        "enabled": enabled,
    }