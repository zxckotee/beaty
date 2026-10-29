from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.roles import HasManagerRole, is_manager
from app.domain.models import Tenant

today_router = Router(name="manager_today")
today_router.message.filter(HasManagerRole())
today_router.callback_query.filter(HasManagerRole())


async def _fetch_day_bookings(
    db_session: AsyncSession,
    tenant: Tenant,
    day: datetime.date,
    staff_filter: UUID | None = None,
):
    day_start = datetime.combine(day, time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    staff_clause = "AND bi.staff_member_id = :staff_id" if staff_filter else ""
    params: dict = {"tenant_id": str(tenant.id), "start": day_start, "end": day_end}
    if staff_filter:
        params["staff_id"] = str(staff_filter)
    return await db_session.execute(
        text(
            f"""
            SELECT b.id, cp.name AS client_name, s.name AS service_name,
                   sm.display_name AS staff_name, lower(bi.during) AS start_at, b.status
            FROM booking b
            JOIN booking_item bi ON bi.booking_id = b.id AND bi.is_active = true
            JOIN client_profile cp ON cp.id = b.client_profile_id
            JOIN service s ON s.id = bi.service_id
            JOIN staff_member sm ON sm.id = bi.staff_member_id
            WHERE b.tenant_id = :tenant_id
              AND bi.during && tstzrange(:start, :end, '[)')
              AND b.status NOT IN ('cancelled')
              {staff_clause}
            ORDER BY start_at
            """
        ),
        params,
    )


async def send_today(
    message: Message,
    db_session: AsyncSession,
    tenant: Tenant,
    *,
    day_offset: int = 0,
    staff_id: UUID | None = None,
) -> None:
    day = (datetime.now(UTC) + timedelta(days=day_offset)).date()
    rows = await _fetch_day_bookings(db_session, tenant, day, staff_id)
    items = rows.all()
    kb = InlineKeyboardBuilder()
    kb.button(text="◀ День", callback_data=f"m:day:{day_offset - 1}:{staff_id or ''}")
    kb.button(text="▶ День", callback_data=f"m:day:{day_offset + 1}:{staff_id or ''}")
    kb.button(text="Все мастера", callback_data=f"m:day:{day_offset}:")
    kb.adjust(2, 1)
    if not items:
        await message.answer(
            f"Записей на {day.strftime('%d.%m.%Y')} нет.",
            reply_markup=kb.as_markup(),
        )
        return
    lines = [f"Записи на {day.strftime('%d.%m.%Y')}:"]
    for r in items:
        t = r.start_at.strftime("%H:%M") if r.start_at else "?"
        lines.append(f"{t} {r.client_name} — {r.service_name} / {r.staff_name} [{r.status}]")
        kb.button(text=f"{t} {r.client_name}"[:38], callback_data=f"m:bdg:{r.id}")
    kb.adjust(1)
    await message.answer("\n".join(lines), reply_markup=kb.as_markup())


@today_router.message(Command("today"))
@today_router.message(F.text == "Сегодня")
async def cmd_today(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
) -> None:
    if not is_manager(roles):
        await message.answer("Доступно менеджерам.")
        return
    await send_today(message, db_session, tenant)


@today_router.callback_query(F.data.startswith("m:day:"))
async def day_nav(callback: CallbackQuery, tenant: Tenant, db_session: AsyncSession) -> None:
    parts = (callback.data or "").split(":")
    offset = int(parts[2])
    staff_raw = parts[3] if len(parts) > 3 else ""
    staff_id = UUID(staff_raw) if staff_raw else None
    if callback.message:
        await callback.message.delete()
        await send_today(callback.message, db_session, tenant, day_offset=offset, staff_id=staff_id)
    await callback.answer()


@today_router.callback_query(F.data.startswith("m:bdg:"))
async def booking_card(callback: CallbackQuery, tenant: Tenant, db_session: AsyncSession) -> None:
    bid = (callback.data or "").split(":")[2]
    kb = InlineKeyboardBuilder()
    kb.button(text="Пришёл", callback_data=f"s:st:{bid}:arrived")
    kb.button(text="Выполнено", callback_data=f"s:st:{bid}:completed")
    kb.button(text="Неявка", callback_data=f"s:st:{bid}:no_show")
    kb.button(text="Отменить", callback_data=f"m:bcn:{bid}")
    kb.adjust(1)
    if callback.message:
        await callback.message.answer("Действия с записью:", reply_markup=kb.as_markup())
    await callback.answer()
