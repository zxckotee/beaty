import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_bot_token
from app.domain.default_rules import DEFAULT_TENANT_RULES
from app.domain.exceptions import BotAlreadyLinkedError
from app.domain.models import Branch, StaffMember, StaffRole, Tenant, UserAccount


def _public_id() -> str:
    return secrets.token_urlsafe(12)[:16]


async def create_tenant_for_owner(
    session: AsyncSession,
    *,
    owner_telegram_id: int,
    business_name: str,
    owner_display_name: str,
    public_id: str | None = None,
) -> Tenant:
    user = await session.scalar(
        select(UserAccount).where(UserAccount.telegram_user_id == owner_telegram_id)
    )
    if user is None:
        user = UserAccount(telegram_user_id=owner_telegram_id)
        session.add(user)
        await session.flush()

    tenant = Tenant(
        public_id=public_id or _public_id(),
        name=business_name,
        rules=DEFAULT_TENANT_RULES.copy(),
        brand={"tone": "formal", "primary": "#2481cc"},
        webhook_secret=secrets.token_hex(16),
    )
    session.add(tenant)
    await session.flush()

    branch = Branch(tenant_id=tenant.id, name="Основной", timezone="Europe/Moscow")
    session.add(branch)
    await session.flush()

    staff = StaffMember(
        tenant_id=tenant.id,
        user_account_id=user.id,
        display_name=owner_display_name,
        roles=[StaffRole.OWNER.value, StaffRole.MANAGER.value, StaffRole.SPECIALIST.value],
    )
    session.add(staff)
    await session.flush()
    tenant.rules = {**tenant.rules, "default_branch_id": str(branch.id)}
    return tenant


async def find_tenant_by_bot_id(session: AsyncSession, bot_id: int) -> Tenant | None:
    return await session.scalar(select(Tenant).where(Tenant.bot_id == bot_id))


async def find_owned_tenant_for_telegram_user(
    session: AsyncSession,
    telegram_user_id: int,
) -> Tenant | None:
    user = await session.scalar(
        select(UserAccount).where(UserAccount.telegram_user_id == telegram_user_id)
    )
    if user is None:
        return None
    staff_rows = (
        await session.scalars(select(StaffMember).where(StaffMember.user_account_id == user.id))
    ).all()
    for staff in staff_rows:
        if StaffRole.OWNER.value in (staff.roles or []):
            tenant = await session.get(Tenant, staff.tenant_id)
            if tenant is not None:
                return tenant
    return None


async def mark_tenant_bot_revoked(session: AsyncSession, *, public_id: str) -> bool:
    """Mark tenant bot token invalid. Returns True if status changed to revoked."""
    tenant = await session.scalar(select(Tenant).where(Tenant.public_id == public_id))
    if tenant is None:
        return False
    if tenant.bot_status == "revoked":
        return False
    tenant.bot_status = "revoked"
    await session.flush()
    return True


async def attach_bot_token(
    session: AsyncSession,
    tenant: Tenant,
    *,
    bot_token: str,
    bot_id: int,
    bot_username: str,
) -> None:
    existing = await find_tenant_by_bot_id(session, bot_id)
    if existing is not None and existing.id != tenant.id:
        raise BotAlreadyLinkedError(
            f"bot_id={bot_id} already linked to tenant {existing.public_id}"
        )
    tenant.bot_token_encrypted = encrypt_bot_token(bot_token)
    tenant.bot_id = bot_id
    tenant.bot_username = bot_username
    tenant.bot_status = "active"
