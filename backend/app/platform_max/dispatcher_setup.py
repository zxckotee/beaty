from aiogram import Dispatcher

from app.platform_max.handlers import platform_max_router

platform_max_dispatcher = Dispatcher()
platform_max_dispatcher.include_router(platform_max_router)