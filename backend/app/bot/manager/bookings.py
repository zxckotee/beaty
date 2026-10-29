from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.subscription_gate import assert_tenant_can_write
from app.bot.filters.roles import HasManagerRole
from app.bot.manager.states import ManagerManualBookStates
from app.bot.shared import assert_can_write, get_branch, get_branch_id
from app.domain.exceptions import DomainError, SlotTakenError
from app.domain.models import ClientProfile, Service, StaffMember, Tenant, UserAccount
from app.domain.services.booking_service import cancel_booking, confirm_hold, hold_slot
from app.domain.services.slot_repository import list_available_slots

bookings_router = Router(name="manager_bookings")
bookings_router.message.filter(HasManagerRole())
bookings_router.callback_query.filter(HasManagerRole())


@bookings_router.message(Command("book_client"))
@bookings_router.message(F.text == "Записать клиента")
async def manual_book_start(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    rows = (
        await db_session.scalars(
            select(StaffMember).where(
                StaffMember.tenant_id == tenant.id,
                StaffMember.is_active.is_(True),
            )
        )
    ).all()
    if not rows:
        await message.answer("Сначала добавьте специалиста в «Команда».")
        return
    kb = InlineKeyboardBuilder()
    for st in rows:
        kb.button(text=st.display_name[:40], callback_data=f"m:mb:st:{st.id}")
    kb.adjust(1)
    await state.set_state(ManagerManualBookStates.pick_staff)
    await message.answer("Выберите мастера:", reply_markup=kb.as_markup())


@bookings_router.callback_query(F.data.startswith("m:mb:st:"))
async def manual_pick_staff(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    sid = UUID((callback.data or "").split(":")[3])
    await state.update_data(mb_staff_id=str(sid))
    rows = (
        await db_session.scalars(
            select(Service).where(Service.tenant_id == tenant.id, Service.is_active.is_(True))
        )
    ).all()
    kb = InlineKeyboardBuilder()
    for svc in rows[:12]:
        kb.button(text=f"{svc.name}"[:40], callback_data=f"m:mb:sv:{svc.id}")
    kb.adjust(1)
    await state.set_state(ManagerManualBookStates.pick_service)
    if callback.message:
        await callback.message.edit_text("Выберите услугу:", reply_markup=kb.as_markup())
    await callback.answer()


@bookings_router.callback_query(F.data.startswith("m:mb:sv:"))
async def manual_pick_service(callback: CallbackQuery, state: FSMContext) -> None:
    svc_id = (callback.data or "").split(":")[3]
    await state.update_data(mb_service_id=svc_id)
    await state.set_state(ManagerManualBookStates.pick_day)
    kb = InlineKeyboardBuilder()
    today = date.today()
    for i in range(7):
        d = today + timedelta(days=i)
        kb.button(text=d.strftime("%d.%m"), callback_data=f"m:mb:day:{d.isoformat()}")
    kb.adjust(4)
    if callback.message:
        await callback.message.edit_text("Выберите день:", reply_markup=kb.as_markup())
    await callback.answer()


@bookings_router.callback_query(F.data.startswith("m:mb:day:"))
async def manual_pick_day(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    day_str = (callback.data or "").split(":")[3]
    data = await state.get_data()
    staff_id = UUID(data["mb_staff_id"])
    service_id = UUID(data["mb_service_id"])
    service = await db_session.get(Service, service_id)
    if service is None:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    branch = await get_branch(db_session, tenant)
    day = date.fromisoformat(day_str)
    slots = await list_available_slots(
        db_session,
        tenant_id=tenant.id,
        branch=branch,
        service=service,
        staff_member_id=staff_id,
        rules=tenant.rules or {},
        limit=100,
    )
    day_slots = [s for s in slots if s.start.astimezone(UTC).date() == day]
    kb = InlineKeyboardBuilder()
    for slot in day_slots[:12]:
        t = slot.start.astimezone(UTC).strftime("%H:%M")
        kb.button(text=t, callback_data=f"m:mb:sl:{slot.start.isoformat()}")
    kb.adjust(4)
    if not day_slots:
        await callback.answer("Нет слотов", show_alert=True)
        return
    await state.set_state(ManagerManualBookStates.pick_slot)
    if callback.message:
        await callback.message.edit_text("Выберите время:", reply_markup=kb.as_markup())
    await callback.answer()


@bookings_router.callback_query(F.data.startswith("m:mb:sl:"))
async def manual_pick_slot(callback: CallbackQuery, state: FSMContext) -> None:
    start_iso = (callback.data or "").split(":", 3)[3]
    await state.update_data(mb_start_at=start_iso)
    await state.set_state(ManagerManualBookStates.client_name)
    if callback.message:
        await callback.message.edit_text("Имя клиента:")
    await callback.answer()


@bookings_router.message(ManagerManualBookStates.client_name)
async def manual_client_name(message: Message, state: FSMContext) -> None:
    await state.update_data(mb_client_name=(message.text or "").strip()[:120])
    await state.set_state(ManagerManualBookStates.client_phone)
    await message.answer("Телефон клиента (или «-» если неизвестен):")


@bookings_router.message(ManagerManualBookStates.client_phone)
async def manual_client_phone(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
    user_account: UserAccount | None,
) -> None:
    phone_raw = (message.text or "").strip()
    phone = None if phone_raw in {"", "-"} else phone_raw[:32]
    data = await state.get_data()
    try:
        assert_tenant_can_write(tenant)
        assert_can_write(tenant, subscription_read_only)
        profile = ClientProfile(
            tenant_id=tenant.id,
            name=data["mb_client_name"],
            phone=phone,
            source="manual",
        )
        db_session.add(profile)
        await db_session.flush()
        start_at = datetime.fromisoformat(data["mb_start_at"])
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=UTC)
        booking = await hold_slot(
            db_session,
            tenant=tenant,
            branch_id=get_branch_id(tenant),
            client_profile_id=profile.id,
            staff_member_id=UUID(data["mb_staff_id"]),
            service_id=UUID(data["mb_service_id"]),
            start_at=start_at,
            actor_user_id=user_account.id if user_account else None,
        )
        booking = await confirm_hold(
            db_session,
            tenant=tenant,
            booking_id=booking.id,
            actor_user_id=user_account.id if user_account else None,
        )
        await db_session.commit()
    except (SlotTakenError, DomainError) as exc:
        await db_session.rollback()
        await message.answer(f"Не удалось: {exc}")
        return
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Ошибка: {exc}")
        return
    await state.clear()
    await message.answer(f"Запись создана (#{booking.id}).")


@bookings_router.callback_query(F.data.startswith("m:bcn:"))
async def manager_cancel_booking(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
    user_account: UserAccount | None,
) -> None:
    bid = UUID((callback.data or "").split(":")[2])
    try:
        assert_can_write(tenant, subscription_read_only)
        await cancel_booking(
            db_session,
            tenant=tenant,
            booking_id=bid,
            reason="manager_cancel",
            actor_user_id=user_account.id if user_account else None,
            skip_deadline_check=True,
        )
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Отменено")
    if callback.message:
        await callback.message.edit_text("Запись отменена менеджером.")
