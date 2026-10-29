"""Notify business owner when tenant bot token is rejected by Telegram."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.bot.factory import create_bot
from app.core.db import SessionLocal
from app.core.settings import get_settings
from app.domain.models import StaffMember, StaffRole, Tenant, UserAccount

logger = logging.getLogger(__name__)


async def find_owner_telegram_id(session, tenant_id) -> int | None:
    rows = (
        await session.scalars(select(StaffMember).where(StaffMember.tenant_id == tenant_id))
    ).all()
    for staff in rows:
        if StaffRole.OWNER.value not in (staff.roles or []):
            continue
        if staff.user_account_id is None:
            continue
        user = await session.get(UserAccount, staff.user_account_id)
        if user is not None:
            return user.telegram_user_id
    return None


async def notify_owner_bot_token_revoked(public_id: str) -> None:
    settings = get_settings()
    if not settings.platform_bot_token:
        return
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.public_id == public_id))
        if tenant is None:
            return
        owner_id = await find_owner_telegram_id(session, tenant.id)
        if owner_id is None:
            return
        uname = tenant.bot_username or public_id
    bot = create_bot(settings.platform_bot_token)
    try:
        await bot.send_message(
            owner_id,
            "Telegram отклонил токен бота салона "
            f"(@{uname}).\n\n"
            "Если вы нажали Revoke в @BotFather — скопируйте новый токен и "
            "пришлите его этому платформенному боту (команда /start).",
            parse_mode=None,
        )
    except Exception:
        logger.exception("failed to notify owner about revoked token tenant=%s", public_id)
    finally:
        await bot.session.close()
