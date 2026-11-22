from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from app.bot.active_role import UI_ROLE_CLIENT, UI_ROLE_MANAGER, UI_ROLE_SPECIALIST
from app.bot.chat_readonly import reply_use_miniapp
from app.bot.filters.roles import HasActiveClientRole, is_manager, is_staff
from app.bot.miniapp import bot_chat_write_enabled, miniapp_open_hint
from app.domain.models import Tenant  # noqa: TC001 — aiogram DI

common_router = Router(name="common")


@common_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@common_router.message(Command("help"))
@common_router.message(F.text == "Помощь")
async def cmd_help(message: Message, tenant: Tenant, roles: set[str], active_ui_role: str) -> None:
    bot_user = message.bot
    username = getattr(bot_user, "username", None) or "bot"
    lines = [
        f"Салон: {tenant.name}",
        f"Бот: @{username}",
        "",
    ]
    if not bot_chat_write_enabled():
        lines.extend(
            [
                "В чате можно только смотреть информацию. Запись и управление — в мини-приложении.",
                "",
                "/my — мои записи",
            ]
        )
        if is_manager(roles):
            lines.extend(
                [
                    "/today — записи салона на сегодня",
                    "/staff — команда",
                    "/services — услуги",
                    "/find_client имя — поиск клиента",
                    "/pending — нерешённые переносы",
                ]
            )
        if is_staff(roles):
            lines.append("/day — мой рабочий день")
        lines.extend(["/help — эта справка", "", miniapp_open_hint()])
        await message.answer("\n".join(lines))
        return
    lines.extend(
        [
            "Команды:",
            "/cancel — отменить текущий шаг",
        ]
    )
    if active_ui_role == UI_ROLE_MANAGER and is_manager(roles):
        lines.extend(
            [
                "/today — записи на сегодня",
                "Команда, Услуги — управление салоном",
            ]
        )
    if active_ui_role == UI_ROLE_SPECIALIST and is_staff(roles):
        lines.extend(["/day — мой рабочий день", "/sick — форс-мажор"])
    if active_ui_role == UI_ROLE_CLIENT:
        lines.extend(["/book — запись", "/my — мои записи"])
    await message.answer("\n".join(lines))


@common_router.message(F.text == "Запись", HasActiveClientRole())
async def text_book(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session,
) -> None:
    if not bot_chat_write_enabled():
        await reply_use_miniapp(message, tenant)
        return
    from app.bot.client.book import start_book_flow

    await start_book_flow(message, state, entry="service", tenant=tenant, db_session=db_session)


@common_router.message(F.text == "Повторить прошлую", HasActiveClientRole())
async def text_repeat(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session,
    client_profile,
) -> None:
    from sqlalchemy import text

    from app.bot.client.book import start_book_flow

    if not bot_chat_write_enabled():
        await reply_use_miniapp(message, tenant)
        return
    if not client_profile:
        await message.answer("Сначала /start и телефон для записи.")
        return
    row = await db_session.execute(
        text(
            """
            SELECT bi.service_id, bi.staff_member_id
            FROM booking b
            JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            WHERE b.tenant_id = :tenant_id AND b.client_profile_id = :cid
              AND b.status = 'completed'
            ORDER BY lower(bi.during) DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"tenant_id": str(tenant.id), "cid": str(client_profile.id)},
    )
    last = row.first()
    if not last:
        await message.answer("Пока нет завершённых визитов для повтора.")
        return
    await state.update_data(
        book_entry="service",
        pre_service_id=str(last.service_id),
        pre_staff_id=str(last.staff_member_id),
        service_id=str(last.service_id),
        staff_id=str(last.staff_member_id),
    )
    await start_book_flow(message, state, entry="service", tenant=tenant, db_session=db_session)


@common_router.message(F.text == "Мои записи", HasActiveClientRole())
async def text_my(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session,
    client_profile,
) -> None:
    from app.bot.client.my_bookings import send_my_bookings

    await send_my_bookings(message, state, tenant, db_session, client_profile)
