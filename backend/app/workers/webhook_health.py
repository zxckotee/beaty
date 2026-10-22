"""Periodic webhook health checks for tenant bots."""

import logging

import httpx
from sqlalchemy import select

from app.core.crypto import decrypt_bot_token
from app.core.db import SessionLocal
from app.domain.models import Tenant

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
