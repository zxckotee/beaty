from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.booking_flow import start_booking
from app.bot.keyboards import client_main_menu
from app.core.db import SessionLocal
from app.domain.models import BookingEvent, Tenant
from app.domain.services.booking_service import confirm_visit
from app.domain.services.force_majeure import apply_force_majeure_choice

tenant_router = Router(name="tenant")


@tenant_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    start_param = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else None
    greet = (
        "Добро пожаловать! Запись, перенос и напоминания — прямо в этом чате.\n"
        "Нажмите «Записаться» или выберите пункт меню."
    )
    if start_param and start_param.startswith("service_"):
        greet = "Вы выбрали услугу — продолжите шаги ниже."
    elif start_param and start_param.startswith("master_"):
        greet = "Запись к выбранному мастеру — продолжите шаги ниже."
    await message.answer(greet, reply_markup=client_main_menu())
    if start_param and (
        start_param.startswith("service_") or start_param.startswith("master_")
    ):
        await start_booking(message, state, start_param=start_param)


@tenant_router.callback_query(F.data.startswith("confirm_visit:"))
async def confirm_visit_callback(callback: CallbackQuery) -> None:
    booking_id = callback.data.split(":", 1)[1] if callback.data else ""
    tenant_public_id = getattr(callback.bot, "tenant_public_id", None)
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
        if tenant is None:
            await callback.answer("Ошибка", show_alert=True)
            return
        try:
            await confirm_visit(
                session,
                tenant=tenant,
                booking_id=UUID(booking_id),
                actor_user_id=None,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            await callback.answer("Не удалось подтвердить", show_alert=True)
            return
    await callback.answer("Подтверждено")
    if callback.message:
        await callback.message.edit_text("Спасибо! Ждём вас на приёме.")


@tenant_router.callback_query(F.data.startswith("fm:"))
async def force_majeure_callback(callback: CallbackQuery) -> None:
    """fm:{booking_id}:{option_index} — applies stored options from booking_event."""
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await callback.answer("Неверные данные")
        return
    booking_id = UUID(parts[1])
    option_index = int(parts[2])
    tenant_public_id = getattr(callback.bot, "tenant_public_id", None)
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
        if tenant is None:
            await callback.answer("Ошибка", show_alert=True)
            return
        event = await session.scalar(
            select(BookingEvent)
            .where(
                BookingEvent.booking_id == booking_id,
                BookingEvent.event_type == "force_majeure_options",
            )
            .order_by(BookingEvent.created_at.desc())
        )
        if event is None:
            await callback.answer("Варианты устарели", show_alert=True)
            return
        options = event.payload.get("options") or []
        if option_index >= len(options):
            await callback.answer("Вариант недоступен", show_alert=True)
            return
        await apply_force_majeure_choice(
            session,
            tenant_id=tenant.id,
            booking_id=booking_id,
            choice=options[option_index],
            actor_user_id=None,
        )
        await session.commit()
    await callback.answer("Готово")
    if callback.message:
        await callback.message.edit_text("Ваш выбор сохранён. Спасибо!")
