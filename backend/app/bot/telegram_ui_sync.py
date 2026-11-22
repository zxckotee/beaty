"""Sync Telegram-side bot chrome: main «Open» Mini App button, command menu."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import MenuButtonCommands, MenuButtonDefault, MenuButtonWebApp, WebAppInfo

from app.bot.miniapp import bot_reply_keyboard_enabled, miniapp_url_for_tenant
from app.domain.models import Tenant

logger = logging.getLogger(__name__)

MENU_OPEN_LABEL = "Открыть"


async def sync_tenant_bot_telegram_ui(bot: Bot, tenant: Tenant) -> None:
    """Apply platform UI mode to this bot in Telegram (menu button + commands list)."""
    url = miniapp_url_for_tenant(tenant)
    try:
        if url:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text=MENU_OPEN_LABEL,
                    web_app=WebAppInfo(url=url),
                )
            )
            await bot.delete_my_commands()
        elif bot_reply_keyboard_enabled():
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            await bot.delete_my_commands()
    except TelegramAPIError as exc:
        logger.warning("telegram ui sync failed tenant=%s: %s", tenant.public_id, exc)