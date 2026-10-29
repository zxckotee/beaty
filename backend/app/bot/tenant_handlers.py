"""Legacy notification callbacks (confirm visit, force majeure)."""

from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import BookingEvent, Tenant
from app.domain.services.booking_service import confirm_visit
from app.domain.services.force_majeure import apply_force_majeure_choice

legacy_router = Router(name="legacy")


@legacy_router.callback_query(F.data.startswith("confirm_visit:"))
async def confirm_visit_callback(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    booking_id = callback.data.split(":", 1)[1] if callback.data else ""
    try:
        await confirm_visit(
            db_session,
            tenant=tenant,
            booking_id=UUID(booking_id),
            actor_user_id=None,
        )
        await db_session.commit()
    except Exception:
        await db_session.rollback()
        await callback.answer("Не удалось подтвердить", show_alert=True)
        return
    await callback.answer("Подтверждено")
    if callback.message:
        await callback.message.edit_text("Спасибо! Ждём вас на приёме.")


@legacy_router.callback_query(F.data.startswith("fm:"))
async def force_majeure_callback(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await callback.answer("Неверные данные")
        return
    booking_id = UUID(parts[1])
    option_index = int(parts[2])
    event = await db_session.scalar(
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
    try:
        await apply_force_majeure_choice(
            db_session,
            tenant_id=tenant.id,
            booking_id=booking_id,
            choice=options[option_index],
            actor_user_id=None,
        )
        await db_session.commit()
    except Exception:
        await db_session.rollback()
        await callback.answer("Ошибка", show_alert=True)
        return
    await callback.answer("Готово")
    if callback.message:
        await callback.message.edit_text("Ваш выбор сохранён. Спасибо!")
