from aiogram import Dispatcher

from app.bot.booking_flow import booking_router
from app.bot.tenant_handlers import tenant_router

dispatcher = Dispatcher()
dispatcher.include_router(tenant_router)
dispatcher.include_router(booking_router)
