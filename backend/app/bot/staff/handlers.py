from datetime import UTC, datetime, timedelta
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.subscription_gate import assert_tenant_can_write
from app.bot.filters.roles import is_manager, is_staff
from app.bot.shared import assert_can_write
from app.domain.exceptions import DomainError
from app.domain.models import Booking, BookingItem, BookingStatus, StaffMember, Tenant
from app.domain.services.force_majeure import declare_unavailable

staff_router = Router(name="staff")


async def _can_update_booking_status(
    session: AsyncSession,
    *,
    tenant: Tenant,
    booking_id: UUID,
    roles: set[str],
    staff_member: StaffMember | None,
) -> bool:
    if not is_staff(roles):
        return False
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant.id:
        return False
    if is_manager(roles):
        return True
    if staff_member is None:
        return False
    item = await session.scalar(
        select(BookingItem).where(
            BookingItem.booking_id == booking_id,
            BookingItem.is_active.is_(True),
        )
    )
    return item is not None and item.staff_member_id == staff_member.id


@staff_router.message(Command("day"))
@staff_router.message(F.text == "Мой день")
async def cmd_day(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
    staff_member: StaffMember | None,
    roles: set[str],
) -> None:
    if not is_staff(roles) or staff_member is None:
        await message.answer("Доступно мастерам.")
        return
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    rows = await db_session.execute(
        text(
            """
            SELECT b.id, b.status, cp.name AS client_name, s.name AS service_name,
                   lower(bi.during) AS start_at
            FROM booking b
            JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            JOIN client_profile cp ON cp.id = b.client_profile_id
            JOIN service s ON s.id = bi.service_id
            WHERE b.tenant_id = :tenant_id AND bi.staff_member_id = :staff_id
              AND bi.during && tstzrange(:start, :end, '[)')
              AND b.status NOT IN ('cancelled')
            ORDER BY start_at
            """
        ),
        {
            "tenant_id": str(tenant.id),
            "staff_id": str(staff_member.id),
            "start": day_start,
            "end": day_end,
        },
    )
    items = rows.all()
    if not items:
        await message.answer("На сегодня записей нет.")
        return
    lines = ["Мой день:"]
    kb = InlineKeyboardBuilder()
    for r in items:
        t = r.start_at.strftime("%H:%M") if r.start_at else "?"
        lines.append(f"{t} {r.client_name} — {r.service_name} ({r.status})")
        kb.button(text=f"{t} {r.client_name}"[:40], callback_data=f"s:st:menu:{r.id}")
    kb.adjust(1)
    await message.answer("\n".join(lines), reply_markup=kb.as_markup())


@staff_router.callback_query(F.data.startswith("s:st:menu:"))
async def staff_booking_menu(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
    staff_member: StaffMember | None,
) -> None:
    bid = (callback.data or "").split(":")[-1]
    try:
        booking_id = UUID(bid)
    except ValueError:
        await callback.answer("Неверная запись", show_alert=True)
        return
    if not await _can_update_booking_status(
        db_session,
        tenant=tenant,
        booking_id=booking_id,
        roles=roles,
        staff_member=staff_member,
    ):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Пришёл", callback_data=f"s:st:{bid}:arrived")
    kb.button(text="Выполнено", callback_data=f"s:st:{bid}:completed")
    kb.button(text="Неявка", callback_data=f"s:st:{bid}:no_show")
    kb.adjust(1)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
    await callback.answer()


@staff_router.callback_query(F.data.startswith("s:st:"))
async def staff_status(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
    roles: set[str],
    staff_member: StaffMember | None,
) -> None:
    if callback.data and callback.data.startswith("s:st:menu:"):
        return
    parts = (callback.data or "").split(":")
    if len(parts) < 4 or parts[2] == "menu":
        await callback.answer()
        return
    booking_id = UUID(parts[2])
    status = parts[3]
    mapping = {
        "arrived": BookingStatus.ARRIVED.value,
        "completed": BookingStatus.COMPLETED.value,
        "no_show": BookingStatus.NO_SHOW.value,
    }
    if status not in mapping:
        await callback.answer()
        return
    if not await _can_update_booking_status(
        db_session,
        tenant=tenant,
        booking_id=booking_id,
        roles=roles,
        staff_member=staff_member,
    ):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        assert_can_write(tenant, subscription_read_only)
        booking = await db_session.get(Booking, booking_id)
        if booking is None or booking.tenant_id != tenant.id:
            raise DomainError("not found")
        booking.status = mapping[status]
        if booking.status == BookingStatus.COMPLETED.value:
            from app.domain.services.revisit_service import schedule_revisit_for_completed_booking

            await schedule_revisit_for_completed_booking(
                db_session, tenant_id=tenant.id, booking_id=booking.id
            )
        await db_session.commit()
    except DomainError as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Сохранено")
    if callback.message:
        await callback.message.edit_text(f"Статус записи: {mapping[status]}")


@staff_router.message(Command("sick"))
async def cmd_sick(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
    staff_member: StaffMember | None,
    roles: set[str],
    subscription_read_only: bool,
) -> None:
    if not is_staff(roles) or staff_member is None:
        await message.answer("Доступно мастерам.")
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Сегодня (4ч)", callback_data="s:sick:4h")
    kb.button(text="Сегодня (весь день)", callback_data="s:sick:day")
    await message.answer("Форс-мажур:", reply_markup=kb.as_markup())


@staff_router.callback_query(F.data.startswith("s:sick:"))
async def sick_preset(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    staff_member: StaffMember | None,
    subscription_read_only: bool,
) -> None:
    if staff_member is None:
        await callback.answer("Нет профиля мастера", show_alert=True)
        return
    try:
        assert_tenant_can_write(tenant)
        assert_can_write(tenant, subscription_read_only)
        start = datetime.now(UTC)
        end = start + timedelta(hours=4)
        if (callback.data or "").endswith(":day"):
            end = start.replace(hour=23, minute=59) + timedelta(hours=0)
        await declare_unavailable(
            db_session,
            tenant_id=tenant.id,
            staff_member_id=staff_member.id,
            start_at=start,
            end_at=end,
            reason="force_majeure",
        )
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text("Форс-мажор применён, клиенты получат варианты.")
    await callback.answer("Готово")
