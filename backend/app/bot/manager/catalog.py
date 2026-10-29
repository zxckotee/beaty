from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.subscription_gate import assert_tenant_can_write
from app.bot.filters.roles import HasManagerRole
from app.bot.manager.states import ManagerServiceEditStates, ManagerServiceStates
from app.bot.shared import assert_can_write
from app.domain.models import Service, Tenant
from app.domain.services.catalog_service import apply_catalog_template

catalog_router = Router(name="manager_catalog")
catalog_router.message.filter(HasManagerRole())
catalog_router.callback_query.filter(HasManagerRole())


@catalog_router.message(F.text == "Услуги")
async def cmd_services(message: Message, tenant: Tenant, db_session: AsyncSession) -> None:
    await _list_services(message, tenant, db_session)


async def _list_services(message: Message, tenant: Tenant, db_session: AsyncSession) -> None:
    rows = (
        await db_session.scalars(select(Service).where(Service.tenant_id == tenant.id))
    ).all()
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить услугу", callback_data="m:svc:add")
    kb.button(text="📦 Шаблон barber", callback_data="m:svc:tpl:barber")
    if not rows:
        await message.answer("Услуг пока нет.", reply_markup=kb.as_markup())
        return
    for svc in rows:
        mark = "✓" if svc.is_active else "✗"
        kb.button(
            text=f"{mark} {svc.name} — {svc.price_cents // 100}₽",
            callback_data=f"m:svc:view:{svc.id}",
        )
    kb.adjust(1)
    await message.answer("Услуги:", reply_markup=kb.as_markup())


@catalog_router.callback_query(F.data == "m:svc:add")
async def svc_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManagerServiceStates.waiting_name)
    if callback.message:
        await callback.message.answer("Название услуги:")
    await callback.answer()


@catalog_router.message(ManagerServiceStates.waiting_name)
async def svc_name(message: Message, state: FSMContext) -> None:
    await state.update_data(svc_name=(message.text or "").strip()[:120])
    await state.set_state(ManagerServiceStates.waiting_price)
    await message.answer("Цена в рублях (число):")


@catalog_router.message(ManagerServiceStates.waiting_price)
async def svc_price(message: Message, state: FSMContext) -> None:
    try:
        rub = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(svc_price_rub=rub)
    await state.set_state(ManagerServiceStates.waiting_duration)
    await message.answer("Длительность в минутах:")


@catalog_router.message(ManagerServiceStates.waiting_duration)
async def svc_duration(message: Message, state: FSMContext) -> None:
    try:
        mins = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(svc_duration=mins)
    await state.set_state(ManagerServiceStates.waiting_buffer)
    await message.answer("Буфер после услуги (минут), 0 если не нужен:")


@catalog_router.message(ManagerServiceStates.waiting_buffer)
async def svc_buffer(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    try:
        buf = int((message.text or "0").strip())
    except ValueError:
        await message.answer("Введите число.")
        return
    data = await state.get_data()
    try:
        assert_tenant_can_write(tenant)
        assert_can_write(tenant, subscription_read_only)
        svc = Service(
            tenant_id=tenant.id,
            name=data["svc_name"],
            price_cents=int(data["svc_price_rub"]) * 100,
            duration_minutes=int(data["svc_duration"]),
            buffer_minutes=buf,
            is_active=True,
        )
        db_session.add(svc)
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Ошибка: {exc}")
        return
    await state.clear()
    await message.answer(f"Услуга «{svc.name}» добавлена.")


@catalog_router.callback_query(F.data.startswith("m:svc:view:"))
async def svc_view(callback: CallbackQuery, tenant: Tenant, db_session: AsyncSession) -> None:
    sid = UUID((callback.data or "").split(":")[3])
    svc = await db_session.get(Service, sid)
    if svc is None or svc.tenant_id != tenant.id:
        await callback.answer("Не найдено", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Цена", callback_data=f"m:svc:ep:{svc.id}")
    kb.button(text="Длительность", callback_data=f"m:svc:ed:{svc.id}")
    toggle = "Выключить" if svc.is_active else "Включить"
    kb.button(text=toggle, callback_data=f"m:svc:toggle:{svc.id}")
    kb.adjust(2, 1)
    text = (
        f"{svc.name}\n"
        f"Цена: {svc.price_cents // 100}₽\n"
        f"Длительность: {svc.duration_minutes} мин\n"
        f"Буфер: {svc.buffer_minutes} мин\n"
        f"Активна: {'да' if svc.is_active else 'нет'}"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@catalog_router.callback_query(F.data.startswith("m:svc:toggle:"))
async def svc_toggle(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    sid = UUID((callback.data or "").split(":")[3])
    svc = await db_session.get(Service, sid)
    if svc is None or svc.tenant_id != tenant.id:
        await callback.answer("Не найдено", show_alert=True)
        return
    try:
        assert_can_write(tenant, subscription_read_only)
        svc.is_active = not svc.is_active
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Сохранено")
    await svc_view(callback, tenant, db_session)


@catalog_router.callback_query(F.data.startswith("m:svc:ep:"))
async def svc_edit_price(callback: CallbackQuery, state: FSMContext) -> None:
    sid = (callback.data or "").split(":")[3]
    await state.set_state(ManagerServiceEditStates.waiting_price)
    await state.update_data(edit_svc_id=sid)
    if callback.message:
        await callback.message.answer("Новая цена в рублях:")
    await callback.answer()


@catalog_router.message(ManagerServiceEditStates.waiting_price)
async def svc_save_price(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    data = await state.get_data()
    sid = UUID(data["edit_svc_id"])
    try:
        rub = int((message.text or "").strip())
        assert_can_write(tenant, subscription_read_only)
        svc = await db_session.get(Service, sid)
        if svc is None or svc.tenant_id != tenant.id:
            raise ValueError("not found")
        svc.price_cents = rub * 100
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Ошибка: {exc}")
        return
    await state.clear()
    await message.answer("Цена обновлена.")


@catalog_router.callback_query(F.data.startswith("m:svc:ed:"))
async def svc_edit_dur(callback: CallbackQuery, state: FSMContext) -> None:
    sid = (callback.data or "").split(":")[3]
    await state.set_state(ManagerServiceEditStates.waiting_duration)
    await state.update_data(edit_svc_id=sid)
    if callback.message:
        await callback.message.answer("Новая длительность (мин):")
    await callback.answer()


@catalog_router.message(ManagerServiceEditStates.waiting_duration)
async def svc_save_dur(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    data = await state.get_data()
    sid = UUID(data["edit_svc_id"])
    try:
        mins = int((message.text or "").strip())
        assert_can_write(tenant, subscription_read_only)
        svc = await db_session.get(Service, sid)
        if svc is None or svc.tenant_id != tenant.id:
            raise ValueError("not found")
        svc.duration_minutes = mins
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Ошибка: {exc}")
        return
    await state.clear()
    await message.answer("Длительность обновлена.")


@catalog_router.callback_query(F.data.startswith("m:svc:tpl:"))
async def svc_template(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    name = (callback.data or "").split(":")[3]
    try:
        assert_tenant_can_write(tenant)
        assert_can_write(tenant, subscription_read_only)
        await apply_catalog_template(db_session, tenant_id=tenant.id, template_name=name)
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Шаблон загружен")
    if callback.message:
        await _list_services(callback.message, tenant, db_session)
