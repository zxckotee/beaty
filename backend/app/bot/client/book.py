from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.codec import load_payload, store_payload
from app.bot.client.states import BookFlow
from app.bot.shared import assert_can_write, get_branch
from app.domain.exceptions import DomainError, SlotTakenError
from app.domain.models import ClientProfile, Service, SpecialistService, StaffMember, Tenant
from app.domain.services.booking_service import confirm_hold, hold_slot
from app.domain.services.slot_repository import list_available_slots

client_book_router = Router(name="client_book")

PAGE_SIZE = 6


def _parse_entity_id(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


async def _go_pick_specialist(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    svc_id: UUID,
) -> None:
    await state.update_data(service_id=str(svc_id))
    await state.set_state(BookFlow.pick_specialist)
    staff_ids = (
        await db_session.scalars(
            select(SpecialistService.staff_member_id).where(
                SpecialistService.tenant_id == tenant.id,
                SpecialistService.service_id == svc_id,
            )
        )
    ).all()
    if staff_ids:
        links = (
            await db_session.scalars(
                select(StaffMember).where(
                    StaffMember.id.in_(staff_ids),
                    StaffMember.is_active.is_(True),
                )
            )
        ).all()
    else:
        links = (
            await db_session.scalars(
                select(StaffMember).where(
                    StaffMember.tenant_id == tenant.id,
                    StaffMember.is_active.is_(True),
                )
            )
        ).all()
    kb = InlineKeyboardBuilder()
    kb.button(text="Любой мастер", callback_data="c:mst:any")
    for st in links:
        kb.button(text=st.display_name, callback_data=f"c:mst:{st.id}")
    kb.adjust(1)
    kb.button(text="🔙 Услуги", callback_data="c:back:svc")
    await message.answer("Выберите мастера:", reply_markup=kb.as_markup())


async def _go_pick_service_for_staff(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    staff_id: UUID,
) -> None:
    await state.update_data(staff_id=str(staff_id), any_staff=False)
    await state.set_state(BookFlow.pick_service)
    svc_ids = (
        await db_session.scalars(
            select(SpecialistService.service_id).where(
                SpecialistService.tenant_id == tenant.id,
                SpecialistService.staff_member_id == staff_id,
            )
        )
    ).all()
    if svc_ids:
        rows = (
            await db_session.scalars(
                select(Service).where(
                    Service.tenant_id == tenant.id,
                    Service.is_active.is_(True),
                    Service.id.in_(svc_ids),
                )
            )
        ).all()
    else:
        rows = (
            await db_session.scalars(
                select(Service).where(Service.tenant_id == tenant.id, Service.is_active.is_(True))
            )
        ).all()
    if not rows:
        await message.answer("Пока нет услуг для этого мастера.")
        return
    kb = InlineKeyboardBuilder()
    for svc in rows[:PAGE_SIZE]:
        label = f"{svc.name} — {svc.price_cents // 100}₽, {svc.duration_minutes}м"
        kb.button(text=label[:60], callback_data=f"c:svc:{svc.id}")
    kb.adjust(1)
    kb.button(text="❌ Отмена", callback_data="c:cancel")
    await message.answer("Выберите услугу:", reply_markup=kb.as_markup())


async def start_book_flow(
    message: Message,
    state: FSMContext,
    *,
    entry: str = "service",
    tenant: Tenant | None = None,
    db_session: AsyncSession | None = None,
) -> None:
    data = await state.get_data()
    entry = data.get("book_entry") or entry
    pre_service = _parse_entity_id(data.get("pre_service_id"))
    pre_staff = _parse_entity_id(data.get("pre_staff_id"))
    await state.update_data(book_entry=entry)
    if tenant is None or db_session is None:
        await state.set_state(BookFlow.pick_service)
        return

    if entry == "master" and pre_staff is not None:
        await _go_pick_service_for_staff(message, state, tenant, db_session, pre_staff)
        return
    if pre_service is not None:
        await _go_pick_specialist(message, state, tenant, db_session, pre_service)
        return
    await state.set_state(BookFlow.pick_service)
    await state.update_data(service_id=None, staff_id=None, any_staff=False)
    await _send_services(message, tenant, db_session, page=0)


@client_book_router.message(Command("book"))
async def cmd_book(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
) -> None:
    if not client_profile:
        await message.answer("Сначала /start и поделитесь телефоном.")
        return
    await start_book_flow(message, state, entry="service", tenant=tenant, db_session=db_session)


@client_book_router.message(Command("book_time"))
async def cmd_book_time(
    message: Message,
    state: FSMContext,
    client_profile: ClientProfile | None,
) -> None:
    if not client_profile:
        await message.answer("Сначала /start.")
        return
    await state.set_state(BookFlow.pick_day)
    await state.update_data(book_entry="time", service_id=None, staff_id=None, any_staff=True)
    kb = InlineKeyboardBuilder()
    today = date.today()
    for i in range(7):
        d = today + timedelta(days=i)
        kb.button(text=d.strftime("%d.%m"), callback_data=f"c:day:{d.isoformat()}")
    kb.adjust(4)
    kb.button(text="❌ Отмена", callback_data="c:cancel")
    await message.answer("Сначала выберите день:", reply_markup=kb.as_markup())


async def _send_services(
    message: Message,
    tenant: Tenant,
    session: AsyncSession,
    page: int = 0,
) -> None:
    rows = (
        await session.scalars(
            select(Service).where(Service.tenant_id == tenant.id, Service.is_active.is_(True))
        )
    ).all()
    if not rows:
        await message.answer("Пока нет услуг.")
        return
    total_pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    kb = InlineKeyboardBuilder()
    for svc in chunk:
        label = f"{svc.name} — {svc.price_cents // 100}₽, {svc.duration_minutes}м"
        kb.button(text=label[:60], callback_data=f"c:svc:{svc.id}")
    kb.adjust(1)
    nav = []
    if page > 0:
        nav.append(("◀", f"c:svc:p:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(("▶", f"c:svc:p:{page + 1}"))
    for text, data in nav:
        kb.button(text=text, callback_data=data)
    if nav:
        kb.adjust(len(nav))
    kb.button(text="❌ Отмена", callback_data="c:cancel")
    await message.answer("Выберите услугу:", reply_markup=kb.as_markup())


@client_book_router.callback_query(F.data.startswith("c:svc:p:"))
async def services_page(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    page = int((callback.data or "c:svc:p:0").split(":")[-1])
    if callback.message:
        await callback.message.delete()
        await _send_services(callback.message, tenant, db_session, page=page)
    await callback.answer()


@client_book_router.callback_query(F.data.startswith("c:svc:"))
async def pick_service(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    if callback.data and callback.data.startswith("c:svc:p:"):
        return
    svc_id = UUID((callback.data or "").split(":", 2)[2])
    await state.update_data(service_id=str(svc_id))
    await state.set_state(BookFlow.pick_specialist)
    staff_ids = (
        await db_session.scalars(
            select(SpecialistService.staff_member_id).where(
                SpecialistService.tenant_id == tenant.id,
                SpecialistService.service_id == svc_id,
            )
        )
    ).all()
    if staff_ids:
        links = (
            await db_session.scalars(
                select(StaffMember).where(
                    StaffMember.id.in_(staff_ids),
                    StaffMember.is_active.is_(True),
                )
            )
        ).all()
    else:
        links = (
            await db_session.scalars(
                select(StaffMember).where(
                    StaffMember.tenant_id == tenant.id,
                    StaffMember.is_active.is_(True),
                )
            )
        ).all()
    kb = InlineKeyboardBuilder()
    kb.button(text="Любой мастер", callback_data="c:mst:any")
    for st in links:
        kb.button(text=st.display_name, callback_data=f"c:mst:{st.id}")
    kb.adjust(1)
    kb.button(text="🔙 Услуги", callback_data="c:back:svc")
    if callback.message:
        await callback.message.edit_text("Выберите мастера:", reply_markup=kb.as_markup())
    await callback.answer()


@client_book_router.callback_query(F.data == "c:back:svc")
async def back_services(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    await state.set_state(BookFlow.pick_service)
    if callback.message:
        await callback.message.delete()
        await _send_services(callback.message, tenant, db_session)
    await callback.answer()


@client_book_router.callback_query(F.data.startswith("c:mst:"))
async def pick_specialist(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    part = (callback.data or "").split(":", 2)[2]
    any_staff = part == "any"
    await state.update_data(staff_id=None if any_staff else part, any_staff=any_staff)
    await state.set_state(BookFlow.pick_day)
    if not any_staff and callback.message:
        st = await db_session.get(StaffMember, UUID(part))
        if st and st.tenant_id == tenant.id:
            caption_parts = [st.display_name]
            if st.specialization:
                caption_parts.append(st.specialization)
            if st.bio:
                caption_parts.append(st.bio[:500])
            caption = "\n".join(caption_parts)
            if st.photo_file_id:
                await callback.message.answer_photo(st.photo_file_id, caption=caption)
            elif caption:
                await callback.message.answer(caption)
    kb = InlineKeyboardBuilder()
    today = date.today()
    for i in range(7):
        d = today + timedelta(days=i)
        kb.button(text=d.strftime("%d.%m"), callback_data=f"c:day:{d.isoformat()}")
    kb.adjust(4)
    if callback.message:
        await callback.message.edit_text("Выберите день:", reply_markup=kb.as_markup())
    await callback.answer()


@client_book_router.callback_query(F.data.startswith("c:day:"))
async def pick_day(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    day_str = (callback.data or "").split(":", 2)[2]
    picked = date.fromisoformat(day_str)
    data = await state.get_data()
    if not data.get("service_id"):
        if data.get("book_entry") == "time":
            await state.update_data(preferred_day=day_str)
            await state.set_state(BookFlow.pick_service)
            if callback.message:
                await callback.message.delete()
                await _send_services(callback.message, tenant, db_session, page=0)
            await callback.answer()
            return
        await callback.answer("Сначала выберите услугу", show_alert=True)
        return
    service_id = UUID(data["service_id"])
    service = await db_session.get(Service, service_id)
    if service is None:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    branch = await get_branch(db_session, tenant)
    staff_id = UUID(data["staff_id"]) if data.get("staff_id") else None
    slots = await list_available_slots(
        db_session,
        tenant_id=tenant.id,
        branch=branch,
        service=service,
        staff_member_id=staff_id,
        rules=tenant.rules or {},
        limit=100,
    )
    day_slots = [s for s in slots if s.start.astimezone(UTC).date() == picked]
    if not day_slots:
        kb = InlineKeyboardBuilder()
        kb.button(text="Лист ожидания", callback_data=f"c:wait:{service_id}:{day_str}")
        if callback.message:
            await callback.message.edit_text(
                "Нет свободных слотов на этот день.",
                reply_markup=kb.as_markup(),
            )
        await callback.answer()
        return
    kb = InlineKeyboardBuilder()
    for sl in day_slots[:12]:
        token = await store_payload(
            {
                "service_id": str(service_id),
                "staff_id": str(sl.staff_member_id),
                "start": sl.start.isoformat(),
            }
        )
        label = sl.start.astimezone(UTC).strftime("%H:%M")
        kb.button(text=label, callback_data=f"c:slot:{token}")
    kb.adjust(3)
    await state.set_state(BookFlow.pick_slot)
    if callback.message:
        await callback.message.edit_text("Выберите время:", reply_markup=kb.as_markup())
    await callback.answer()


@client_book_router.callback_query(F.data.startswith("c:slot:"))
async def pick_slot(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
    subscription_read_only: bool,
) -> None:
    token = (callback.data or "").split(":", 2)[2]
    payload = await load_payload(token)
    if not payload or not client_profile:
        await callback.answer("Данные устарели", show_alert=True)
        return
    try:
        assert_can_write(tenant, subscription_read_only)
        branch = await get_branch(db_session, tenant)
        start_at = datetime.fromisoformat(payload["start"])
        booking = await hold_slot(
            db_session,
            tenant=tenant,
            branch_id=branch.id,
            client_profile_id=client_profile.id,
            staff_member_id=UUID(payload["staff_id"]),
            service_id=UUID(payload["service_id"]),
            start_at=start_at,
            actor_user_id=None,
        )
        await db_session.commit()
    except (SlotTakenError, DomainError) as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    await state.update_data(hold_booking_id=str(booking.id))
    await state.set_state(BookFlow.confirm_hold)
    kb = InlineKeyboardBuilder()
    kb.button(text="Подтвердить запись", callback_data=f"c:ok:{booking.id}")
    kb.button(text="Отменить бронь", callback_data=f"c:cn:{booking.id}")
    exp = booking.hold_expires_at.strftime("%H:%M") if booking.hold_expires_at else "—"
    text = f"Слот удержан до {exp} UTC.\nПодтвердите запись:"
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@client_book_router.callback_query(F.data.startswith("c:ok:"))
async def confirm_booking_cb(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    booking_id = UUID((callback.data or "").split(":", 2)[2])
    try:
        assert_can_write(tenant, subscription_read_only)
        await confirm_hold(db_session, tenant=tenant, booking_id=booking_id, actor_user_id=None)
        await db_session.commit()
    except DomainError as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Запись подтверждена! Ждём вас.")
    await callback.answer("Готово")


@client_book_router.callback_query(F.data.startswith("c:cn:"))
async def cancel_hold_cb(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    from app.domain.services.booking_service import cancel_booking

    booking_id = UUID((callback.data or "").split(":", 2)[2])
    try:
        await cancel_booking(
            db_session,
            tenant=tenant,
            booking_id=booking_id,
            reason="user_cancelled_hold",
            skip_deadline_check=True,
        )
        await db_session.commit()
    except DomainError as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Бронь отменена.")
    await callback.answer()


@client_book_router.callback_query(F.data == "c:cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Отменено.")
    await callback.answer()
