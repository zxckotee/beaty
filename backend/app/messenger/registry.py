from __future__ import annotations

from aiogram import Bot

from app.core.crypto import decrypt_bot_token
from app.domain.models import Tenant
from app.max.session import create_max_bot

_tg_bots: dict[str, Bot] = {}
_max_bots: dict[str, Bot] = {}


def get_telegram_bot_for_tenant(tenant: Tenant) -> Bot:
    from app.bot.registry import get_bot_for_tenant

    return get_bot_for_tenant(tenant)


def get_max_bot_for_tenant(tenant: Tenant) -> Bot:
    cached = _max_bots.get(tenant.public_id)
    if cached is not None:
        return cached
    if not tenant.max_bot_token_encrypted:
        raise RuntimeError("MAX bot token missing")
    token = decrypt_bot_token(tenant.max_bot_token_encrypted)
    bot = create_max_bot(token)
    bot.tenant_public_id = tenant.public_id  # type: ignore[attr-defined]
    bot.messenger_channel = "max"  # type: ignore[attr-defined]
    _max_bots[tenant.public_id] = bot
    return bot


def invalidate_max_bot(tenant_public_id: str) -> None:
    _max_bots.pop(tenant_public_id, None)