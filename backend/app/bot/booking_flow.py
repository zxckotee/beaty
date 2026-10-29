"""Client booking wizard via inline keyboards (bot-only UI)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.bot.keyboards import BTN_BOOK, BTN_MY, BTN_PROFILE, BTN_REPEAT, client_main_menu
from app.core.db import SessionLocal
from app.domain.models import Branch, ClientProfile, Service, SpecialistService, StaffMember, Tenant
from app.domain.services.booking_service import confirm_hold, hold_slot
from app.domain.services.client_service import get_or_create_user_account
from app.domain.services.slot_repository import list_available_slots

booking_router = Router(name="booking")

PAGE_SIZE = 8


class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_master = State()
    choosing_slot = State()
    confirming = State()


async def _load_tenant(session, public_id: str | None) -> Tenant | None:
    if not public_id:
        return None
    return await session.scalar(select(Tenant).where(Tenant.public_id == public_id))


def _services_keyboard(services: list[Service], page: int = 0) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    chunk = services[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for s in chunk:
        price = f"{s.price_cents // 100}₽" if s.price_cents else ""
        label = f"{s.name} · {s.duration_minutes} мин"
        if price:
            label = f"{label} · {price}"
        kb.button(text=label[:64], callback_data=f"bk:svc:{s.id}")
    kb.adjust(1)
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="« Назад", callback_data=f"bk:svcpage:{page - 1}")
    if (page + 1) * PAGE_SIZE < len(services):
        nav.button(text="Ещё »", callback_data=f"bk:svcpage:{page + 1}")
    nav.adjust(2)
    kb.attach(nav)
    kb.button(text="Отмена", callback_data="bk:cancel")
    return kb


def _masters_keyboard(masters: list[StaffMember]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="Любой мастер", callback_data="bk:mst:any")
    for m in masters:
        kb.button(text=(m.display_name or "Мастер")[:64], callback_data=f"bk:mst:{m.id}")
    kb.adjust(1)
    kb.button(text="Отмена", callback_data="bk:cancel")
    return kb


def _slots_keyboard(slots: list, page: int = 0) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    chunk = slots[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for i, slot in enumerate(chunk):
        idx = page * PAGE_SIZE + i
        local = slot.start.astimezone()
        label = local.strftime("%d.%m %H:%M")
        kb.button(text=label, callback_data=f"bk:slot:{idx}")
    kb.adjust(2)
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="« Назад", callback_data=f"bk:slotpage:{page - 1}")
    if (page + 1) * PAGE_SIZE < len(slots):
        nav.button(text="Ещё »", callback_data=f"bk:slotpage:{page + 1}")
    nav.adjust(2)
    kb.attach(nav)
    kb.button(text="Отмена", callback_data="bk:cancel")
    return kb


async def start_booking(message: Message, state: FSMContext, *, start_param: str | None = None) -> None:
    tenant_public_id = getattr(message.bot, "tenant_public_id", None)
    async with SessionLocal() as session:
        tenant = await _load_tenant(session, tenant_public_id)
        if tenant is None:
            await message.answer("Салон не найден.")
            return
        services = list(
            await session.scalars(
                select(Service)
                .where(Service.tenant_id == tenant.id, Service.is_active.is_(True))
                .order_by(Service.name)
            )
        )
        if not services:
            await message.answer("Пока нет услуг для записи. Загляните позже.")
            return

    await state.set_state(BookingStates.choosing_service)
    data: dict = {"services": [str(s.id) for s in services]}
    if start_param and start_param.startswith("service_"):
        data["preferred_service"] = start_param.removeprefix("service_")
    if start_param and start_param.startswith("master_"):
        data["preferred_master"] = start_param.removeprefix("master_")
    await state.update_data(**data)

    preferred = data.get("preferred_service")
    if preferred and preferred in data["services"]:
        await state.update_data(service_id=preferred)
        await _prompt_masters(message, state)
        return

    await message.answer("Выберите услугу:", reply_markup=_services_keyboard(services).as_markup())


async def _prompt_masters(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    service_id = UUID(data["service_id"])
    tenant_public_id = getattr(target.bot, "tenant_public_id", None)  # type: ignore[union-attr]
    async with SessionLocal() as session:
        tenant = await _load_tenant(session, tenant_public_id)
        if tenant is None:
            return
        link_ids = list(
            await session.scalars(
                select(SpecialistService.staff_member_id).where(
                    SpecialistService.tenant_id == tenant.id,
                    SpecialistService.service_id == service_id,
                )
            )
        )
        q = select(StaffMember).where(StaffMember.tenant_id == tenant.id, StaffMember.is_active.is_(True))
        if link_ids:
            q = q.where(StaffMember.id.in_(link_ids))
        masters = list(await session.scalars(q.order_by(StaffMember.display_name)))

    preferred = data.get("preferred_master")
    if preferred and any(str(m.id) == preferred for m in masters):
        await state.update_data(staff_member_id=preferred)
        await state.set_state(BookingStates.choosing_slot)
        msg = target.message if isinstance(target, CallbackQuery) else target
        assert msg is not None
        await _prompt_slots(msg, state)
        return

    await state.set_state(BookingStates.choosing_master)
    text = "Выберите мастера:"
    markup = _masters_keyboard(masters).as_markup()
    if isinstance(target, CallbackQuery) and target.message:
        await target.message.edit_text(text, reply_markup=markup)
    else:
        msg = target if isinstance(target, Message) else target.message
        if msg:
            await msg.answer(text, reply_markup=markup)


async def _prompt_slots(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    tenant_public_id = getattr(message.bot, "tenant_public_id", None)
    async with SessionLocal() as session:
        tenant = await _load_tenant(session, tenant_public_id)
        if tenant is None:
            await message.answer("Салон не найден.")
            return
        service = await session.get(Service, UUID(data["service_id"]))
        branch_id = tenant.rules.get("default_branch_id")
        branch = await session.get(Branch, UUID(branch_id)) if branch_id else None
        if branch is None:
            branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
        if service is None or branch is None:
            await message.answer("Не удалось загрузить слоты.")
            return
        staff_id = None if data.get("staff_member_id") in (None, "any") else UUID(data["staff_member_id"])
        slots = await list_available_slots(
            session,
            tenant_id=tenant.id,
            branch=branch,
            service=service,
            staff_member_id=staff_id,
            rules=tenant.rules or {},
            limit=40,
        )
        serialized = [
            {"start": s.start.isoformat(), "end": s.end.isoformat(), "staff_member_id": str(s.staff_member_id)}
            for s in slots
        ]

    if not serialized:
        await message.answer(
            "Свободных слотов нет. Попробуйте другую услугу или мастера.",
            reply_markup=client_main_menu(),
        )
        await state.clear()
        return

    await state.update_data(slots=serialized, slot_page=0)
    await state.set_state(BookingStates.choosing_slot)
    await message.answer("Выберите время:", reply_markup=_slots_keyboard(slots).as_markup())


@booking_router.message(F.text == BTN_BOOK)
async def menu_book(message: Message, state: FSMContext) -> None:
    await start_booking(message, state)


@booking_router.message(F.text == BTN_MY)
async def menu_my(message: Message) -> None:
    await message.answer(
        "Раздел «Мои записи» скоро будет доступен командами в этом чате.\n"
        "Перенос и отмена также приходят кнопками в напоминаниях.",
        reply_markup=client_main_menu(),
    )


@booking_router.message(F.text == BTN_REPEAT)
async def menu_repeat(message: Message) -> None:
    await message.answer(
        "«Повторить прошлую» — быстрый сценарий следующего шага. Пока запишитесь через «Записаться».",
        reply_markup=client_main_menu(),
    )


@booking_router.message(F.text == BTN_PROFILE)
async def menu_profile(message: Message) -> None:
    await message.answer(
        "Профиль: имя и телефон из Telegram. Изменение данных и удаление — через поддержку салона (пока).",
        reply_markup=client_main_menu(),
    )


@booking_router.callback_query(F.data == "bk:cancel")
async def booking_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message:
        await callback.message.edit_text("Запись отменена.")
        await callback.message.answer("Меню:", reply_markup=client_main_menu())


@booking_router.callback_query(F.data.startswith("bk:svcpage:"))
async def service_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int((callback.data or "").split(":")[-1])
    data = await state.get_data()
    tenant_public_id = getattr(callback.bot, "tenant_public_id", None)
    async with SessionLocal() as session:
        tenant = await _load_tenant(session, tenant_public_id)
        if tenant is None:
            await callback.answer("Ошибка", show_alert=True)
            return
        services = list(
            await session.scalars(
                select(Service)
                .where(Service.tenant_id == tenant.id, Service.is_active.is_(True))
                .order_by(Service.name)
            )
        )
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_services_keyboard(services, page).as_markup())
    await callback.answer()
    await state.update_data(**data)


@booking_router.callback_query(F.data.startswith("bk:svc:"))
async def pick_service(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = (callback.data or "").split(":")[-1]
    await state.update_data(service_id=service_id)
    await callback.answer()
    await _prompt_masters(callback, state)


@booking_router.callback_query(F.data.startswith("bk:mst:"))
async def pick_master(callback: CallbackQuery, state: FSMContext) -> None:
    raw = (callback.data or "").split(":")[-1]
    await state.update_data(staff_member_id=raw)
    await callback.answer()
    if callback.message:
        await _prompt_slots(callback.message, state)


@booking_router.callback_query(F.data.startswith("bk:slotpage:"))
async def slot_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int((callback.data or "").split(":")[-1])
    data = await state.get_data()
    slots_raw = data.get("slots") or []

    class _S:
        def __init__(self, d: dict) -> None:
            self.start = datetime.fromisoformat(d["start"])
            self.end = datetime.fromisoformat(d["end"])
            self.staff_member_id = d["staff_member_id"]

    slots = [_S(s) for s in slots_raw]
    await state.update_data(slot_page=page)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_slots_keyboard(slots, page).as_markup())
    await callback.answer()


@booking_router.callback_query(F.data.startswith("bk:slot:"))
async def pick_slot(callback: CallbackQuery, state: FSMContext) -> None:
    idx = int((callback.data or "").split(":")[-1])
    data = await state.get_data()
    slots = data.get("slots") or []
    if idx < 0 or idx >= len(slots):
        await callback.answer("Слот устарел", show_alert=True)
        return
    slot = slots[idx]
    await state.update_data(chosen_slot=slot)
    await state.set_state(BookingStates.confirming)
    start = datetime.fromisoformat(slot["start"]).astimezone()
    kb = InlineKeyboardBuilder()
    kb.button(text="Подтвердить", callback_data="bk:confirm")
    kb.button(text="Отмена", callback_data="bk:cancel")
    kb.adjust(2)
    text = f"Сводка:\nВремя: {start.strftime('%d.%m.%Y %H:%M')}\nПодтвердить запись?"
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.as_markup())


@booking_router.callback_query(F.data == "bk:confirm")
async def confirm_booking(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer("Ошибка", show_alert=True)
        return
    data = await state.get_data()
    slot = data.get("chosen_slot")
    if not slot:
        await callback.answer("Нет выбранного слота", show_alert=True)
        return
    tenant_public_id = getattr(callback.bot, "tenant_public_id", None)
    async with SessionLocal() as session:
        tenant = await _load_tenant(session, tenant_public_id)
        if tenant is None:
            await callback.answer("Ошибка", show_alert=True)
            return
        user = await get_or_create_user_account(session, callback.from_user.id)
        profile = await session.scalar(
            select(ClientProfile).where(
                ClientProfile.tenant_id == tenant.id,
                ClientProfile.user_account_id == user.id,
            )
        )
        if profile is None:
            profile = ClientProfile(
                tenant_id=tenant.id,
                user_account_id=user.id,
                name=callback.from_user.full_name or "Клиент",
                phone=None,
                consents={"pd_consent": True},
                source="bot",
            )
            session.add(profile)
            await session.flush()
        branch_id = tenant.rules.get("default_branch_id")
        branch = await session.get(Branch, UUID(branch_id)) if branch_id else None
        if branch is None:
            branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
        if branch is None:
            await callback.answer("Филиал не настроен", show_alert=True)
            return
        try:
            booking = await hold_slot(
                session,
                tenant=tenant,
                branch_id=branch.id,
                client_profile_id=profile.id,
                staff_member_id=UUID(slot["staff_member_id"]),
                service_id=UUID(data["service_id"]),
                start_at=datetime.fromisoformat(slot["start"]).astimezone(UTC),
                actor_user_id=user.id,
            )
            await confirm_hold(session, tenant=tenant, booking_id=booking.id, actor_user_id=user.id)
            await session.commit()
        except Exception:
            await session.rollback()
            await callback.answer("Слот занят или недоступен. Выберите другое время.", show_alert=True)
            await state.clear()
            return

    await state.clear()
    await callback.answer("Записаны!")
    if callback.message:
        await callback.message.edit_text("Готово! Вы записаны. Напоминание придёт в этот чат.")
        await callback.message.answer("Меню:", reply_markup=client_main_menu())
