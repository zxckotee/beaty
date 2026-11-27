from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.help_delivery import send_help_parts
from app.content.user_guide import (
    HELP_BUTTON,
    LEGACY_HELP_BUTTON,
    build_platform_owner_help,
    platform_docs_url,
)
from app.platform_bot.keyboards import platform_reply_keyboard

platform_help_router = Router(name="platform_help")


@platform_help_router.message(Command("help"))
@platform_help_router.message(F.text.in_({HELP_BUTTON, LEGACY_HELP_BUTTON}))
async def platform_cmd_help(message: Message) -> None:
    text = build_platform_owner_help(web_docs_url=platform_docs_url())
    await send_help_parts(
        message,
        text,
        docs_url=platform_docs_url(),
        reply_markup=platform_reply_keyboard(),
    )