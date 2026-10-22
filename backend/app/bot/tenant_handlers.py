from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.db import SessionLocal
from app.core.settings import get_settings
from app.domain.services.booking_service import confirm_visit

tenant_router = Router(name="tenant")


def _miniapp_url(tenant_public_id: str, start_param: str | None = None) -> str:
    settings = get_settings()
    base = settings.miniapp_public_url.rstrip("/")
    path = f"/t/{tenant_public_id}/book"
    if start_param:
        return f"{base}{path}?entry={start_param}"
    return f"{base}{path}"


@tenant_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    settings = get_settings()
    start_param = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else None
    tenant_public_id = getattr(message.bot, "tenant_public_id", "demo")
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Открыть запись",
        web_app=WebAppInfo(url=_miniapp_url(tenant_public_id, start_param)),
    )
    greet = "Добро пожаловать! Запишитесь через мини-приложение или используйте кнопки в уведомлениях."
    if start_param and start_param.startswith("service_"):
        greet = "Вы выбрали услугу — откройте запись, чтобы выбрать время."
    elif start_param and start_param.startswith("master_"):
        greet = "Запись к выбранному мастеру — откройте мини-приложение."
    await message.answer(greet, reply_markup=kb.as_markup())


@tenant_router.callback_query(F.data.startswith("confirm_visit:"))
async def confirm_visit_callback(callback: CallbackQuery) -> None:
    booking_id = callback.data.split(":", 1)[1] if callback.data else ""
    tenant_public_id = getattr(callback.bot, "tenant_public_id", None)
    async with SessionLocal() as session:
        from sqlalchemy import select

        from app.domain.models import Booking, Tenant

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
        from sqlalchemy import select

        from app.domain.models import BookingEvent, Tenant
        from app.domain.services.force_majeure import apply_force_majeure_choice

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
