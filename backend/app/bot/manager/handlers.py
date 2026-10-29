from datetime import UTC, datetime, time, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Service, StaffMember, Tenant

manager_router = Router(name="manager")


def _is_manager(roles: set[str]) -> bool:
    return bool(roles.intersection({"owner", "manager", "reception"}))


@manager_router.message(Command("today"))
@manager_router.message(F.text == "Сегодня")
async def cmd_today(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
) -> None:
    if not _is_manager(roles):
        await message.answer("Доступно менеджерам.")
        return
    day = datetime.now(UTC).date()
    day_start = datetime.combine(day, time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    rows = await db_session.execute(
        text(
            """
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
            ORDER BY start_at
            """
        ),
        {"tenant_id": str(tenant.id), "start": day_start, "end": day_end},
    )
    items = rows.all()
    if not items:
        await message.answer("На сегодня записей нет.")
        return
    lines = [f"Сегодня ({day.strftime('%d.%m')}):"]
    for r in items:
        t = r.start_at.strftime("%H:%M") if r.start_at else "?"
        lines.append(f"{t} {r.client_name} — {r.service_name} / {r.staff_name} [{r.status}]")
    await message.answer("\n".join(lines))


@manager_router.message(Command("staff"))
async def cmd_staff_list(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
) -> None:
    if not _is_manager(roles):
        return
    rows = (
        await db_session.scalars(select(StaffMember).where(StaffMember.tenant_id == tenant.id))
    ).all()
    if not rows:
        await message.answer("Нет сотрудников.")
        return
    lines = ["Команда:"]
    for s in rows:
        lines.append(f"• {s.display_name} — {', '.join(s.roles or [])}")
    await message.answer("\n".join(lines))


@manager_router.message(Command("pending"))
async def cmd_pending(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
) -> None:
    if not _is_manager(roles):
        return
    rows = await db_session.execute(
        text(
            """
            SELECT b.id, b.status FROM booking b
            WHERE b.tenant_id = :tenant_id AND b.reschedule_pending = true
            LIMIT 20
            """
        ),
        {"tenant_id": str(tenant.id)},
    )
    items = rows.all()
    if not items:
        await message.answer("Нет нерешённых переносов/форс-мажора.")
        return
    await message.answer("\n".join(f"#{r.id} — {r.status}" for r in items))


@manager_router.message(Command("book_client"))
async def cmd_book_client(message: Message, roles: set[str]) -> None:
    if not _is_manager(roles):
        return
    await message.answer(
        "Ручная запись: попросите клиента написать /start боту и пройти запись, "
        "или используйте API /manager/bookings/manual (расширенный FSM — в backlog)."
    )


@manager_router.message(Command("service_add"))
async def cmd_service_add(message: Message, roles: set[str]) -> None:
    if not _is_manager(roles):
        return
    await message.answer(
        "Добавление услуги через чат: отправьте одной строкой:\n"
        "название; цена_руб; минуты\nПример: Стрижка; 1500; 45"
    )


@manager_router.message(F.text.regexp(r"^.+;\s*\d+\s*;\s*\d+\s*$"))
async def parse_service_add(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
) -> None:
    if not _is_manager(roles):
        return
    from app.api.subscription_gate import assert_tenant_can_write

    parts = [p.strip() for p in (message.text or "").split(";")]
    if len(parts) != 3:
        return
    name, price_rub, mins = parts[0], int(parts[1]), int(parts[2])
    try:
        assert_tenant_can_write(tenant)
        svc = Service(
            tenant_id=tenant.id,
            name=name,
            price_cents=price_rub * 100,
            duration_minutes=mins,
            buffer_minutes=0,
            is_active=True,
        )
        db_session.add(svc)
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Ошибка: {exc}")
        return
    await message.answer(f"Услуга «{name}» добавлена.")
