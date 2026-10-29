from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import DomainError
from app.domain.models import ClientProfile, Tenant
from app.domain.services.booking_service import cancel_booking

client_my_router = Router(name="client_my")


async def send_my_bookings(
    message: Message,
    state: FSMContext,
    tenant: Tenant | None = None,
    db_session: AsyncSession | None = None,
    client_profile: ClientProfile | None = None,
) -> None:
    if not all([tenant, db_session, client_profile]):
        await message.answer("Сначала /start")
        return
    rows = await db_session.execute(  # type: ignore[union-attr]
        text(
            """
            SELECT b.id, b.status, b.total_price_cents,
                   lower(bi.during) AS start_at,
                   s.name AS service_name, sm.display_name AS staff_name
            FROM booking b
            LEFT JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            LEFT JOIN service s ON s.id = bi.service_id
            LEFT JOIN staff_member sm ON sm.id = bi.staff_member_id
            WHERE b.tenant_id = :tenant_id AND b.client_profile_id = :client_id
              AND b.status NOT IN ('cancelled')
            ORDER BY start_at DESC NULLS LAST
            LIMIT 15
            """
        ),
        {"tenant_id": str(tenant.id), "client_id": str(client_profile.id)},  # type: ignore[union-attr]
    )
    items = rows.all()
    if not items:
        await message.answer("Пока нет активных записей.")
        return
    kb = InlineKeyboardBuilder()
    lines = ["Мои записи:"]
    for r in items:
        when = r.start_at.strftime("%d.%m %H:%M") if r.start_at else "—"
        lines.append(f"• {when} — {r.service_name or 'Услуга'} ({r.status})")
        kb.button(text=f"{when} {r.service_name or 'Запись'}"[:40], callback_data=f"c:my:{r.id}")
    kb.adjust(1)
    await message.answer("\n".join(lines), reply_markup=kb.as_markup())


@client_my_router.message(Command("my"))
async def cmd_my(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
) -> None:
    await send_my_bookings(message, state, tenant, db_session, client_profile)


@client_my_router.callback_query(F.data.startswith("c:my:"))
async def booking_detail(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    booking_id = UUID((callback.data or "").split(":", 2)[2])
    row = await db_session.execute(
        text(
            """
            SELECT b.status, b.total_price_cents, lower(bi.during) AS start_at,
                   s.name AS service_name, sm.display_name AS staff_name
            FROM booking b
            LEFT JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            LEFT JOIN service s ON s.id = bi.service_id
            LEFT JOIN staff_member sm ON sm.id = bi.staff_member_id
            WHERE b.id = :id AND b.tenant_id = :tenant_id
            """
        ),
        {"id": str(booking_id), "tenant_id": str(tenant.id)},
    )
    r = row.one_or_none()
    if r is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    when = r.start_at.strftime("%d.%m.%Y %H:%M") if r.start_at else "—"
    text_msg = (
        f"{r.service_name}\n{when}\nМастер: {r.staff_name or '—'}\n"
        f"Статус: {r.status}\n{(r.total_price_cents or 0) // 100} ₽"
    )
    kb = InlineKeyboardBuilder()
    if r.status in ("booked", "confirmed", "held"):
        kb.button(text="Подтвердить визит", callback_data=f"confirm_visit:{booking_id}")
        kb.button(text="Отменить", callback_data=f"c:cn:ask:{booking_id}")
        kb.button(text="Перенести", callback_data=f"c:rs:{booking_id}")
    kb.adjust(1)
    if callback.message:
        await callback.message.edit_text(text_msg, reply_markup=kb.as_markup())
    await callback.answer()


@client_my_router.callback_query(F.data.startswith("c:cn:ask:"))
async def cancel_ask(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    booking_id = (callback.data or "").split(":", 3)[3]
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, отменить", callback_data=f"c:cn:yes:{booking_id}")
    kb.button(text="Нет", callback_data=f"c:my:{booking_id}")
    if callback.message:
        await callback.message.edit_text("Отменить запись?", reply_markup=kb.as_markup())
    await callback.answer()


@client_my_router.callback_query(F.data.startswith("c:cn:yes:"))
async def cancel_yes(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
) -> None:
    booking_id = UUID((callback.data or "").split(":", 3)[3])
    try:
        from app.bot.shared import assert_can_write

        assert_can_write(tenant, subscription_read_only)
        await cancel_booking(
            db_session,
            tenant=tenant,
            booking_id=booking_id,
            reason="client_cancel",
            actor_user_id=None,
        )
        await db_session.commit()
    except DomainError as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text("Запись отменена.")
    await callback.answer()


@client_my_router.callback_query(F.data.startswith("c:rs:"))
async def reschedule_start(callback: CallbackQuery) -> None:
    await callback.answer("Перенос: выберите /book и новый слот (улучшение в следующей версии)", show_alert=True)
