from aiogram import Dispatcher

from app.bot.tenant_handlers import tenant_router

dispatcher = Dispatcher()
dispatcher.include_router(tenant_router)
