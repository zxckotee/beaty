"""Periodic webhook health checks for tenant bots."""

import logging

import httpx
from sqlalchemy import select

from app.bot.factory import create_bot
from app.bot.telegram_ui_sync import sync_tenant_bot_telegram_ui
from app.core.crypto import decrypt_bot_token
from app.core.db import SessionLocal
from app.core.settings import get_settings
from app.domain.models import Tenant
from app.max.client import MaxClient

logger = logging.getLogger(__name__)


async def check_tenant_webhooks() -> None:
    async with SessionLocal() as session:
        tenants = (
            await session.scalars(
                select(Tenant).where(
                    Tenant.bot_token_encrypted.isnot(None),
                    Tenant.bot_status == "active",
                )
            )
        ).all()
        for tenant in tenants:
            try:
                token = decrypt_bot_token(tenant.bot_token_encrypted or "")
            except Exception:
                logger.warning("webhook check: decrypt failed tenant=%s", tenant.public_id)
                continue
            url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url)
                    data = resp.json()
            except Exception:
                logger.exception("webhook check failed tenant=%s", tenant.public_id)
                continue
            if not data.get("ok"):
                continue
            info = data.get("result") or {}
            last_error = info.get("last_error_message")
            if last_error:
                logger.error(
                    "webhook error tenant=%s: %s",
                    tenant.public_id,
                    last_error,
                )
            bot = create_bot(token)
            try:
                await sync_tenant_bot_telegram_ui(bot, tenant)
            except Exception:
                logger.exception("telegram ui sync tenant=%s", tenant.public_id)
            finally:
                await bot.session.close()

        max_tenants = (
            await session.scalars(
                select(Tenant).where(
                    Tenant.max_bot_token_encrypted.isnot(None),
                    Tenant.max_bot_status == "active",
                )
            )
        ).all()
        for tenant in max_tenants:
            try:
                token = decrypt_bot_token(tenant.max_bot_token_encrypted or "")
                client = MaxClient(token)
                subs = await client.list_subscriptions()
                if not subs:
                    logger.warning("MAX webhook: no subscriptions tenant=%s", tenant.public_id)
            except Exception:
                logger.exception("MAX webhook check failed tenant=%s", tenant.public_id)

        settings = get_settings()
        if settings.platform_max_bot_token:
            try:
                client = MaxClient(settings.platform_max_bot_token)
                subs = await client.list_subscriptions()
                if not subs:
                    logger.warning("MAX platform webhook: no subscriptions")
            except Exception:
                logger.exception("MAX platform webhook check failed")
