from aiogram import Dispatcher

from app.bot.client.book import client_book_router
from app.bot.client.my_bookings import client_my_router
from app.bot.client.onboarding import client_onboarding_router
from app.bot.common.help_cancel import common_router
from app.bot.manager.handlers import manager_router
from app.bot.middleware.context import BotContextMiddleware
from app.bot.phase2.handlers import phase2_router
from app.bot.staff.handlers import staff_router
from app.bot.tenant_handlers import legacy_router


def build_dispatcher() -> Dispatcher:
    """Build the process-wide tenant dispatcher (call once; routers are singletons)."""
    dp = Dispatcher()
    dp.update.middleware(BotContextMiddleware())
    dp.include_router(legacy_router)
    dp.include_router(client_onboarding_router)
    dp.include_router(client_book_router)
    dp.include_router(client_my_router)
    dp.include_router(staff_router)
    dp.include_router(manager_router)
    dp.include_router(phase2_router)
    dp.include_router(common_router)
    return dp


dispatcher = build_dispatcher()
