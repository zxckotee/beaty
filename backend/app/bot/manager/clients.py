from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.roles import HasManagerRole
from app.domain.models import ClientProfile, Tenant

clients_router = Router(name="manager_clients")
clients_router.message.filter(HasManagerRole())


@clients_router.message(F.text == "Клиенты")
async def clients_hint(message: Message) -> None:
    await message.answer(
        "Поиск клиента: отправьте имя или телефон одним сообщением после команды /find_client"
    )


@clients_router.message(F.text.startswith("/find_client"))
async def find_client(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    q = (message.text or "").removeprefix("/find_client").strip()
    if len(q) < 2:
        await message.answer("Пример: /find_client Иван")
        return
    pattern = f"%{q}%"
    rows = (
        await db_session.scalars(
            select(ClientProfile)
            .where(
                ClientProfile.tenant_id == tenant.id,
                or_(ClientProfile.name.ilike(pattern), ClientProfile.phone.ilike(pattern)),
            )
            .limit(10)
        )
    ).all()
    if not rows:
        await message.answer("Никого не нашли.")
        return
    lines = ["Клиенты:"]
    for c in rows:
        phone = c.phone or "—"
        lines.append(f"• {c.name}, {phone}")
    await message.answer("\n".join(lines))
