"""Whether the tenant chat bot may mutate bookings / salon data."""

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.bot.miniapp import bot_chat_write_enabled


class ChatWritesDisabled(BaseFilter):
    async def __call__(self, _event: TelegramObject) -> bool:
        return not bot_chat_write_enabled()


class ChatWritesEnabled(BaseFilter):
    async def __call__(self, _event: TelegramObject) -> bool:
        return bot_chat_write_enabled()
