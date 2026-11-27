from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.active_role import UI_ROLE_CLIENT, UI_ROLE_MANAGER, UI_ROLE_SPECIALIST
from app.bot.chat_readonly import reply_use_miniapp
from app.bot.filters.roles import HasActiveClientRole, is_manager, is_staff
from app.bot.help_delivery import send_help_parts
from app.bot.keyboards.builders import tenant_reply_keyboard
from app.bot.miniapp import bot_chat_write_enabled, miniapp_open_hint
from app.content.user_guide import (
    HELP_BUTTON,
    LEGACY_HELP_BUTTON,
    build_tenant_client_help,
    build_tenant_manager_help,
    tenant_docs_url,
)
from app.domain.models import StaffMember, Tenant  # noqa: TC001 — aiogram DI

common_router = Router(name="common")


def _menu(
    *,
    active_ui_role: str,
    can_switch_ui_role: bool,
    roles: set[str],
    staff_member: StaffMember | None,
):
    return tenant_reply_keyboard(
        active_ui_role=active_ui_role,  # type: ignore[arg-type]
        can_switch_ui_role=can_switch_ui_role,
        granted_roles=roles,
        has_staff_profile=staff_member is not None,
    )


@common_router.message(Command("cancel"))
async def cmd_cancel(
    message: Message,
    state: FSMContext,
    roles: set[str],
    staff_member: StaffMember | None,
    active_ui_role: str,
    can_switch_ui_role: bool,
) -> None:
    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=_menu(
            active_ui_role=active_ui_role,
            can_switch_ui_role=can_switch_ui_role,
            roles=roles,
            staff_member=staff_member,
        ),
    )


@common_router.message(Command("help"))
@common_router.message(F.text.in_({HELP_BUTTON, LEGACY_HELP_BUTTON}))
async def cmd_help(
    message: Message,
    tenant: Tenant,
    roles: set[str],
    staff_member: StaffMember | None,
    active_ui_role: str,
    can_switch_ui_role: bool,
) -> None:
    menu = _menu(
        active_ui_role=active_ui_role,
        can_switch_ui_role=can_switch_ui_role,
        roles=roles,
        staff_member=staff_member,
    )
    miniapp = not bot_chat_write_enabled()
    docs_url = tenant_docs_url(tenant.public_id)
    if miniapp:
        hint = miniapp_open_hint()
        await send_help_parts(
            message,
            f"📖 {tenant.name}\n\n{hint}",
            docs_url=docs_url,
            reply_markup=menu,
        )
        return
    if active_ui_role == UI_ROLE_CLIENT or (
        active_ui_role == UI_ROLE_SPECIALIST and not is_manager(roles)
    ):
        text = build_tenant_client_help(tenant, miniapp=False)
        await send_help_parts(message, text, docs_url=docs_url, reply_markup=menu)
        return
    if active_ui_role in {UI_ROLE_MANAGER, UI_ROLE_SPECIALIST} and (
        is_manager(roles) or active_ui_role == UI_ROLE_MANAGER
    ):
        part1, part2 = build_tenant_manager_help(tenant, miniapp=False, web_docs_url=docs_url)
        await send_help_parts(message, part1, part2=part2, docs_url=docs_url, reply_markup=menu)
        return
    text = build_tenant_client_help(tenant, miniapp=False)
    await send_help_parts(message, text, docs_url=docs_url, reply_markup=menu)


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
