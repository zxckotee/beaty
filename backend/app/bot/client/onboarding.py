from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.client.states import ClientOnboarding
from app.bot.keyboards.builders import contact_request_keyboard, main_menu_reply
from app.bot.miniapp import miniapp_book_keyboard, miniapp_enabled
from app.domain.models import ClientProfile, Tenant, UserAccount
from app.domain.services.client_onboarding_service import (
    client_has_phone,
    complete_client_onboarding,
    ensure_user_account,
)

client_onboarding_router = Router(name="client_onboarding")


def _parse_start_param(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else None


@client_onboarding_router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
    user_account: UserAccount | None,
    roles: set[str],
) -> None:
    start_param = _parse_start_param(message.text)
    await state.update_data(start_param=start_param, book_entry=None)

    if start_param:
        if start_param.startswith("service_"):
            await state.update_data(book_entry="service", pre_service_id=start_param[8:])
        elif start_param.startswith("master_"):
            await state.update_data(book_entry="master", pre_staff_id=start_param[7:])
        elif start_param.startswith("promo_"):
            await state.update_data(promo_code=start_param[6:])

    if client_profile and client_has_phone(client_profile):
        greet_markup = main_menu_reply(
            is_staff=bool(roles.intersection({"specialist", "owner", "manager"})),
            is_manager=bool(roles.intersection({"owner", "manager", "reception"})),
        )
        await message.answer(f"Снова здравствуйте! {tenant.name}", reply_markup=greet_markup)
        if miniapp_enabled():
            await message.answer(
                "Или откройте запись в мини-приложении:",
                reply_markup=miniapp_book_keyboard(tenant.public_id, start_param),
            )
        if start_param:
            from app.bot.client.book import start_book_flow

            entry = (await state.get_data()).get("book_entry") or "service"
            await start_book_flow(message, state, entry=entry, tenant=tenant, db_session=db_session)
        return

    policy = (tenant.rules or {}).get("privacy_url", "")
    intro = f"Добро пожаловать в {tenant.name}!"
    if policy:
        intro += f"\nПолитика: {policy}"
    intro += "\n\nДля записи нужен номер телефона (кнопка ниже)."
    await state.set_state(ClientOnboarding.waiting_contact)
    if miniapp_enabled():
        await message.answer(intro, reply_markup=miniapp_book_keyboard(tenant.public_id, start_param))
        intro += "\n\nЛибо поделитесь телефоном для записи в чате:"
    await message.answer(intro, reply_markup=contact_request_keyboard())


@client_onboarding_router.message(ClientOnboarding.waiting_contact, F.contact)
async def got_contact(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
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
        reply_markup=main_menu_reply(
            is_staff=bool(roles.intersection({"specialist", "owner", "manager"})),
            is_manager=bool(roles.intersection({"owner", "manager", "reception"})),
        ),
    )
    if book_entry and callback.message:
        from app.bot.client.book import start_book_flow

        await start_book_flow(
            callback.message,
            state,
            entry=book_entry,
            tenant=tenant,
            db_session=db_session,
        )
    await callback.answer()
