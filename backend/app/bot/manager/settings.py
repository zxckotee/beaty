from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.subscription_gate import assert_tenant_can_write
from app.bot.filters.roles import HasManagerRole
from app.bot.manager.pending import cmd_pending
from app.bot.manager.states import ManagerSettingsStates
from app.bot.shared import assert_can_write
from app.domain.models import Tenant

settings_router = Router(name="manager_settings")
settings_router.message.filter(HasManagerRole())
settings_router.callback_query.filter(HasManagerRole())


@settings_router.message(F.text == "Ещё")
async def more_menu(message: Message) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="Нерешённое", callback_data="m:more:pending")
    kb.button(text="Настройки салона", callback_data="m:more:settings")
    kb.button(text="Записать клиента", callback_data="m:more:book")
    kb.adjust(1)
    await message.answer("Дополнительно:", reply_markup=kb.as_markup())


@settings_router.callback_query(F.data == "m:more:pending")
async def more_pending(callback: CallbackQuery, tenant: Tenant, db_session: AsyncSession) -> None:
    if callback.message:
        await cmd_pending(callback.message, tenant, db_session)
    await callback.answer()


@settings_router.callback_query(F.data == "m:more:book")
async def more_book(callback: CallbackQuery, state: FSMContext, tenant: Tenant, db_session: AsyncSession) -> None:
    from app.bot.manager.bookings import manual_book_start

    if callback.message:
        await manual_book_start(callback.message, state, tenant, db_session)
    await callback.answer()


@settings_router.callback_query(F.data == "m:more:settings")
async def more_settings(callback: CallbackQuery) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="Название салона", callback_data="m:set:name")
    kb.button(text="Ссылка политики", callback_data="m:set:privacy")
    kb.adjust(1)
    if callback.message:
        await callback.message.answer("Что изменить?", reply_markup=kb.as_markup())
    await callback.answer()


@settings_router.callback_query(F.data == "m:set:name")
async def set_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManagerSettingsStates.waiting_salon_name)
    if callback.message:
        await callback.message.answer("Новое название салона:")
    await callback.answer()


@settings_router.message(ManagerSettingsStates.waiting_salon_name)
async def set_name_save(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    name = (message.text or "").strip()[:255]
    if not name:
        await message.answer("Введите название.")
        return
    try:
        assert_tenant_can_write(tenant)
        assert_can_write(tenant, subscription_read_only)
        tenant.name = name
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Ошибка: {exc}")
        return
    await state.clear()
    await message.answer(f"Название: {tenant.name}")


@settings_router.callback_query(F.data == "m:set:privacy")
async def set_privacy_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManagerSettingsStates.waiting_privacy_url)
    if callback.message:
        await callback.message.answer("URL политики конфиденциальности:")
    await callback.answer()


@settings_router.message(ManagerSettingsStates.waiting_privacy_url)
async def set_privacy_save(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    url = (message.text or "").strip()[:512]
    try:
        assert_tenant_can_write(tenant)
        assert_can_write(tenant, subscription_read_only)
        tenant.rules = {**(tenant.rules or {}), "privacy_url": url}
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Ошибка: {exc}")
        return
    await state.clear()
    await message.answer("Политика обновлена.")
