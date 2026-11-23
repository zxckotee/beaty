import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_bot_token
from app.core.settings import get_settings
from app.domain.default_rules import DEFAULT_TENANT_RULES
from app.domain.exceptions import BotAlreadyLinkedError
from app.domain.models import Branch, StaffMember, StaffRole, Tenant
from app.domain.services.client_service import get_or_create_user_by_messenger
from app.max.client import MaxClient
from app.messenger.registry import invalidate_max_bot
from app.messenger.types import Channel


def _public_id() -> str:
    return secrets.token_urlsafe(12)[:16]


async def create_tenant_for_owner(
    session: AsyncSession,
    *,
    owner_telegram_id: int | None = None,
    owner_max_user_id: int | None = None,
    business_name: str,
    owner_display_name: str,
    public_id: str | None = None,
) -> Tenant:
    if owner_telegram_id is not None:
        user = await get_or_create_user_by_messenger(session, Channel.TELEGRAM, owner_telegram_id)
    elif owner_max_user_id is not None:
        user = await get_or_create_user_by_messenger(session, Channel.MAX, owner_max_user_id)
    else:
        raise ValueError("owner messenger id required")

    tenant = Tenant(
        public_id=public_id or _public_id(),
        name=business_name,
        rules=DEFAULT_TENANT_RULES.copy(),
        brand={"tone": "formal", "primary": "#2481cc"},
        webhook_secret=secrets.token_hex(16),
        max_webhook_secret=secrets.token_hex(16),
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


async def find_tenant_by_max_bot_id(session: AsyncSession, bot_id: int) -> Tenant | None:
    return await session.scalar(select(Tenant).where(Tenant.max_bot_id == bot_id))


async def find_tenant_by_channel_bot_id(session: AsyncSession, channel: Channel, bot_id: int) -> Tenant | None:
    if channel is Channel.MAX:
        return await find_tenant_by_max_bot_id(session, bot_id)
    return await find_tenant_by_bot_id(session, bot_id)


async def find_owned_tenant_for_user(
    session: AsyncSession,
    *,
    channel: Channel,
    messenger_user_id: int,
) -> Tenant | None:
    from app.domain.services.client_service import get_user_by_messenger

    user = await get_user_by_messenger(session, channel, messenger_user_id)
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


async def find_owned_tenant_for_telegram_user(
    session: AsyncSession,
    telegram_user_id: int,
) -> Tenant | None:
    return await find_owned_tenant_for_user(
        session, channel=Channel.TELEGRAM, messenger_user_id=telegram_user_id
    )


async def find_owned_tenant_for_max_user(
    session: AsyncSession,
    max_user_id: int,
) -> Tenant | None:
    return await find_owned_tenant_for_user(session, channel=Channel.MAX, messenger_user_id=max_user_id)


async def mark_tenant_bot_revoked(session: AsyncSession, *, public_id: str) -> bool:
    tenant = await session.scalar(select(Tenant).where(Tenant.public_id == public_id))
    if tenant is None:
        return False
    if tenant.bot_status == "revoked":
        return False
    tenant.bot_status = "revoked"
    await session.flush()
    return True


async def mark_tenant_max_bot_revoked(session: AsyncSession, *, public_id: str) -> bool:
    tenant = await session.scalar(select(Tenant).where(Tenant.public_id == public_id))
    if tenant is None:
        return False
    if tenant.max_bot_status == "revoked":
        return False
    tenant.max_bot_status = "revoked"
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
    await attach_telegram_bot_token(
        session,
        tenant,
        bot_token=bot_token,
        bot_id=bot_id,
        bot_username=bot_username,
    )


async def attach_telegram_bot_token(
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
    if not tenant.webhook_secret:
        tenant.webhook_secret = secrets.token_hex(16)


async def ensure_max_webhook(tenant: Tenant, *, bot_token: str) -> None:
    settings = get_settings()
    base = settings.webhook_base_url.rstrip("/")
    if not tenant.max_webhook_secret:
        tenant.max_webhook_secret = secrets.token_hex(16)
    url = f"{base}/max/{tenant.public_id}"
    client = MaxClient(bot_token)
    await client.set_subscription(url=url, secret=tenant.max_webhook_secret)


async def ensure_platform_max_webhook() -> None:
    settings = get_settings()
    token = settings.platform_max_bot_token
    secret = settings.max_platform_webhook_secret
    if not token or not secret:
        return
    base = settings.webhook_base_url.rstrip("/")
    client = MaxClient(token)
    await client.set_subscription(url=f"{base}/max/platform", secret=secret)


async def attach_max_bot_token(
    session: AsyncSession,
    tenant: Tenant,
    *,
    bot_token: str,
    bot_id: int,
    bot_username: str,
) -> None:
    existing = await find_tenant_by_max_bot_id(session, bot_id)
    if existing is not None and existing.id != tenant.id:
        raise BotAlreadyLinkedError(
            f"max bot_id={bot_id} already linked to tenant {existing.public_id}"
        )
    tenant.max_bot_token_encrypted = encrypt_bot_token(bot_token)
    tenant.max_bot_id = bot_id
    tenant.max_bot_username = bot_username
    tenant.max_bot_status = "active"
    if not tenant.max_webhook_secret:
        tenant.max_webhook_secret = secrets.token_hex(16)
    await session.flush()
    try:
        await ensure_max_webhook(tenant, bot_token=bot_token)
    except Exception:
        pass
    invalidate_max_bot(tenant.public_id)