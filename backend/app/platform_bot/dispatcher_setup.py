from aiogram import Dispatcher

from app.platform_bot.handlers import platform_router
from app.platform_bot.help_handlers import platform_help_router

platform_dispatcher = Dispatcher()
platform_dispatcher.include_router(platform_router)
platform_dispatcher.include_router(platform_help_router)
