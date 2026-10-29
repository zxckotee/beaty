from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.roles import HasManagerRole
from app.domain.models import Tenant

pending_router = Router(name="manager_pending")
pending_router.message.filter(HasManagerRole())


@pending_router.message(Command("pending"))
@pending_router.message(F.text == "Нерешённое")
async def cmd_pending(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
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
