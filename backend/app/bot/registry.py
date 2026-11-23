from aiogram import Bot

from app.bot.factory import create_bot
from app.core.crypto import decrypt_bot_token
from app.domain.models import Tenant

_bot_cache: dict[str, Bot] = {}


def get_bot_for_tenant(tenant: Tenant) -> Bot:
    if tenant.public_id not in _bot_cache:
        if not tenant.bot_token_encrypted:
            raise ValueError("bot token missing")
        token = decrypt_bot_token(tenant.bot_token_encrypted)
        bot = create_bot(token)
        setattr(bot, "tenant_public_id", tenant.public_id)
        _bot_cache[tenant.public_id] = bot
    return _bot_cache[tenant.public_id]
