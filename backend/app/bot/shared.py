from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import DomainError
from app.domain.models import Branch, Tenant


def get_branch_id(tenant: Tenant) -> UUID:
    raw = (tenant.rules or {}).get("default_branch_id")
    if not raw:
        raise DomainError("branch not configured")
    return UUID(str(raw))


async def get_branch(session: AsyncSession, tenant: Tenant) -> Branch:
    branch = await session.get(Branch, get_branch_id(tenant))
    if branch is None:
        raise DomainError("branch not configured")
    return branch


CHAT_WRITE_DISABLED = "Запись и управление доступны в мини-приложении"


def assert_can_write(tenant: Tenant, read_only: bool) -> None:
    from app.bot.miniapp import bot_chat_write_enabled

    if not bot_chat_write_enabled():
        raise DomainError(CHAT_WRITE_DISABLED)
    if read_only:
        raise DomainError("subscription inactive")
