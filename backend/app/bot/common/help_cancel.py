from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from app.domain.models import Tenant  # noqa: TC001 — aiogram DI

common_router = Router(name="common")


@common_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@common_router.message(Command("help"))
@common_router.message(F.text == "Помощь")
async def cmd_help(message: Message, tenant: Tenant, roles: set[str]) -> None:
    bot_user = message.bot
    username = getattr(bot_user, "username", None) or "bot"
    lines = [
        f"Салон: {tenant.name}",
        f"Бот: @{username}",
        "",
        "Команды:",
        "/book — запись",
        "/my — мои записи",
        "/cancel — отменить текущий шаг",
    ]
    if roles.intersection({"owner", "manager", "reception"}):
        lines.extend(["/today — записи на сегодня", "/book_client — записать клиента"])
    if roles.intersection({"specialist", "owner", "manager"}):
        lines.extend(["/day — мой рабочий день", "/sick — форс-мажор"])
    await message.answer("\n".join(lines))


@common_router.message(F.text == "Запись")
async def text_book(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session,
) -> None:
    from app.bot.client.book import start_book_flow

    await start_book_flow(message, state, entry="service", tenant=tenant, db_session=db_session)


@common_router.message(F.text == "Мои записи")
async def text_my(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session,
    client_profile,
) -> None:
    from app.bot.client.my_bookings import send_my_bookings

    await send_my_bookings(message, state, tenant, db_session, client_profile)
