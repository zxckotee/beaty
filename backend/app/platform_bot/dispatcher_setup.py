from aiogram import Dispatcher

from app.platform_bot.handlers import platform_router

platform_dispatcher = Dispatcher()
platform_dispatcher.include_router(platform_router)
