import asyncio
import logging

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from app.bot.dispatcher_setup import dispatcher
from app.bot.registry import get_bot_for_tenant
from app.core.db import SessionLocal
from app.core.redis_client import get_redis
from app.domain.models import Tenant
from app.platform_bot.dispatcher_setup import platform_dispatcher
from app.webhook.security import verify_platform_webhook_secret, verify_tenant_webhook_secret

logger = logging.getLogger(__name__)
webhook_router = APIRouter()


async def _dedupe_update(tenant_key: str, update_id: int) -> bool:
    redis = await get_redis()
    key = f"tg:dedupe:{tenant_key}:{update_id}"
    inserted = await redis.set(key, "1", nx=True, ex=86400)
    return inserted is True


@webhook_router.post("/tg/platform")
async def platform_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    from app.core.settings import get_settings

    settings = get_settings()
    verify_platform_webhook_secret(x_telegram_bot_api_secret_token)
    data = await request.json()
    update = Update.model_validate(data)
    if update.update_id and not await _dedupe_update("platform", update.update_id):
        return {"ok": "duplicate"}
    from app.bot.factory import create_bot

    bot = create_bot(settings.platform_bot_token)
    asyncio.create_task(platform_dispatcher.feed_update(bot, update))
    return {"ok": "accepted"}


@webhook_router.post("/tg/{tenant_public_id}")
async def tenant_webhook(
    tenant_public_id: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        verify_tenant_webhook_secret(x_telegram_bot_api_secret_token, tenant.webhook_secret)
        bot = get_bot_for_tenant(tenant)
    data = await request.json()
    update = Update.model_validate(data)
    if update.update_id and not await _dedupe_update(tenant_public_id, update.update_id):
        return {"ok": "duplicate"}

    async def _process() -> None:
        try:
            await dispatcher.feed_update(bot, update)
        except Exception:
            logger.exception("failed to process update tenant=%s", tenant_public_id)

    asyncio.create_task(_process())
    return {"ok": "accepted"}


@webhook_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
