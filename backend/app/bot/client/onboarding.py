from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.active_role import UI_ROLE_LABELS, available_ui_roles, read_stored_ui_role, resolve_active_ui_role
from app.bot.client.states import ClientOnboarding
from app.bot.filters.roles import is_manager
from app.bot.keyboards.builders import contact_request_keyboard, main_menu_reply
from app.domain.exceptions import DomainError
from app.domain.models import ClientProfile, StaffMember, Tenant, UserAccount
from app.domain.services.client_onboarding_service import (
    client_has_phone,
    complete_client_onboarding,
    ensure_user_account,
)
from app.domain.services.team_invite_service import accept_invite, parse_invite_token

client_onboarding_router = Router(name="client_onboarding")


def _parse_start_param(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else None


def _reply_menu(
    roles: set[str],
    staff_member: StaffMember | None,
    *,
    active_ui_role: str | None = None,
    can_switch_ui_role: bool | None = None,
):
    avail = available_ui_roles(
        granted_roles=roles,
        has_staff_profile=staff_member is not None,
    )
    active = active_ui_role or resolve_active_ui_role(read_stored_ui_role(staff_member), avail)
    can_switch = can_switch_ui_role if can_switch_ui_role is not None else len(avail) > 1
    return main_menu_reply(active_ui_role=active, can_switch_ui_role=can_switch)  # type: ignore[arg-type]


@client_onboarding_router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
    user_account: UserAccount | None,
    staff_member: StaffMember | None,
    roles: set[str],
    active_ui_role: str,
    can_switch_ui_role: bool,
) -> None:
    start_param = _parse_start_param(message.text)
    invite_token = parse_invite_token(start_param)
    if invite_token and message.from_user:
        try:
            staff = await accept_invite(
                db_session,
                tenant_id=tenant.id,
                telegram_user_id=message.from_user.id,
                raw_token=invite_token,
            )
            await db_session.commit()
            roles.update(staff.roles or [])
            roles.add("specialist")
            staff_member = staff
            await state.clear()
            avail = available_ui_roles(granted_roles=roles, has_staff_profile=True)
            active = resolve_active_ui_role(read_stored_ui_role(staff), avail)
            await message.answer(
                f"Вы присоединились к {tenant.name} как {staff.display_name}.",
                reply_markup=main_menu_reply(
                    active_ui_role=active,
                    can_switch_ui_role=len(avail) > 1,
                ),
            )
            return
        except DomainError as exc:
            await db_session.rollback()
            await message.answer(f"Не удалось принять приглашение: {exc}")
            return

    await state.update_data(start_param=start_param, book_entry=None)

    if start_param:
        if start_param.startswith("service_"):
            await state.update_data(book_entry="service", pre_service_id=start_param[8:])
        elif start_param.startswith("master_"):
            await state.update_data(book_entry="master", pre_staff_id=start_param[7:])
        elif start_param.startswith("promo_"):
            await state.update_data(promo_code=start_param[6:])

    if client_profile and client_has_phone(client_profile):
        await message.answer(
            f"Снова здравствуйте! {tenant.name}",
            reply_markup=_reply_menu(
                roles,
                staff_member,
                active_ui_role=active_ui_role,
                can_switch_ui_role=can_switch_ui_role,
            ),
        )
        if start_param and not invite_token and active_ui_role == "client":
            from app.bot.client.book import start_book_flow

            entry = (await state.get_data()).get("book_entry") or "service"
            await start_book_flow(message, state, entry=entry, tenant=tenant, db_session=db_session)
        return

    if staff_member is not None and client_profile is None:
        lines = [f"Здравствуйте, {staff_member.display_name}!"]
        if is_manager(roles):
            lines.append(
                "Вы управляете салоном: добавьте услуги в «Услуги», "
                "мастеров в «Команда», записи — в «Сегодня»."
            )
            if can_switch_ui_role:
                lines.append(
                    f"Сейчас режим «{UI_ROLE_LABELS.get(active_ui_role, active_ui_role)}». "
                    "Другие роли — кнопка «Сменить режим»."
                )
        else:
            lines.append("Ваш рабочий день — кнопка «Мой день».")
        await message.answer(
            "\n".join(lines),
            reply_markup=_reply_menu(
                roles,
                staff_member,
                active_ui_role=active_ui_role,
                can_switch_ui_role=can_switch_ui_role,
            ),
        )
        return

    policy = (tenant.rules or {}).get("privacy_url", "")
    intro = f"Добро пожаловать в {tenant.name}!"
    if policy:
        intro += f"\nПолитика: {policy}"
    intro += "\n\nДля записи нужен номер телефона (кнопка ниже)."
    await state.set_state(ClientOnboarding.waiting_contact)
    await message.answer(intro, reply_markup=contact_request_keyboard())


@client_onboarding_router.message(ClientOnboarding.waiting_contact, F.contact)
async def got_contact(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
    staff_member: StaffMember | None,
) -> None:
    contact = message.contact
    if contact is None or contact.user_id != message.from_user.id:  # type: ignore[union-attr]
        await message.answer("Нужен ваш контакт, не чужой.")
        return
    phone = contact.phone_number or ""
    name = (message.from_user.full_name or "Клиент") if message.from_user else "Клиент"
    data = await state.get_data()
    await ensure_user_account(db_session, message.from_user.id)  # type: ignore[union-attr]
    profile = await complete_client_onboarding(
        db_session,
        tenant_id=tenant.id,
        telegram_user_id=message.from_user.id,  # type: ignore[union-attr]
        name=name,
        phone=phone,
        source=data.get("start_param"),
    )
    await db_session.commit()
    await state.update_data(pending_name=profile.name)
    await state.set_state(ClientOnboarding.waiting_name_confirm)
    kb = InlineKeyboardBuilder()
    kb.button(text="Верно", callback_data="c:onb:name:ok")
    kb.button(text="Изменить", callback_data="c:onb:name:edit")
    await message.answer(f"Имя: {profile.name} — верно?", reply_markup=kb.as_markup())


@client_onboarding_router.callback_query(F.data == "c:onb:name:ok")
async def name_ok(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ClientOnboarding.waiting_marketing)
    kb = InlineKeyboardBuilder()
    kb.button(text="Да", callback_data="c:onb:mkt:yes")
    kb.button(text="Нет", callback_data="c:onb:mkt:no")
    if callback.message:
        await callback.message.edit_text("Получать акции и напоминания?", reply_markup=kb.as_markup())
    await callback.answer()


@client_onboarding_router.callback_query(F.data == "c:onb:name:edit")
async def name_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ClientOnboarding.waiting_name_edit)
    if callback.message:
        await callback.message.edit_text("Напишите, как к вам обращаться:")
    await callback.answer()


@client_onboarding_router.message(ClientOnboarding.waiting_name_edit)
async def name_edited(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
) -> None:
    if client_profile:
        client_profile.name = (message.text or client_profile.name).strip()[:120]
        await db_session.commit()
    await state.set_state(ClientOnboarding.waiting_marketing)
    kb = InlineKeyboardBuilder()
    kb.button(text="Да", callback_data="c:onb:mkt:yes")
    kb.button(text="Нет", callback_data="c:onb:mkt:no")
    await message.answer("Получать акции и напоминания?", reply_markup=kb.as_markup())


@client_onboarding_router.callback_query(F.data.startswith("c:onb:mkt:"))
async def marketing_choice(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
    roles: set[str],
    staff_member: StaffMember | None,
    active_ui_role: str,
    can_switch_ui_role: bool,
) -> None:
    opt_in = callback.data.endswith(":yes")
    data = await state.get_data()
    if client_profile:
        client_profile.consents = {**client_profile.consents, "marketing": opt_in}
        await db_session.commit()
    book_entry = data.get("book_entry")
    await state.clear()
    if callback.message:
        await callback.message.edit_text(f"Готово! Добро пожаловать в {tenant.name}.")
    await callback.message.answer(  # type: ignore[union-attr]
        "Меню:",
        reply_markup=_reply_menu(
            roles,
            staff_member,
            active_ui_role=active_ui_role,
            can_switch_ui_role=can_switch_ui_role,
        ),
    )
    if book_entry and callback.message and active_ui_role == "client":
        from app.bot.client.book import start_book_flow

        await start_book_flow(
            callback.message,
            state,
            entry=book_entry,
            tenant=tenant,
            db_session=db_session,
        )
    await callback.answer()
