from aiogram import Router

from app.bot.manager.bookings import bookings_router
from app.bot.manager.catalog import catalog_router
from app.bot.manager.clients import clients_router
from app.bot.manager.pending import pending_router
from app.bot.manager.settings import settings_router
from app.bot.manager.team import team_router
from app.bot.manager.today import today_router

manager_router = Router(name="manager")
manager_router.include_router(today_router)
manager_router.include_router(team_router)
manager_router.include_router(catalog_router)
manager_router.include_router(bookings_router)
manager_router.include_router(clients_router)
manager_router.include_router(settings_router)
manager_router.include_router(pending_router)

__all__ = ["manager_router"]
