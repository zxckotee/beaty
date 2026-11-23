import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ConflictError, ValidationError
from app.domain.models import ClientProfile, StaffMember, UserAccount
from app.messenger.types import Channel


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    return digits


async def get_or_create_manual_client(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    name: str,
    phone: str,
    source: str = "manual",
) -> ClientProfile:
    """Offline / manager-entered client card keyed by phone; bot registration later links user_account."""
    cleaned_name = name.strip() or "Клиент"
    normalized = normalize_phone(phone)
    if len(normalized) < 10:
        raise ValidationError("phone is required")
    existing = await session.scalar(
        select(ClientProfile).where(
            ClientProfile.tenant_id == tenant_id,
            ClientProfile.phone == normalized,
        )
    )
    if existing is not None:
        existing.name = cleaned_name
        if not existing.source:
            existing.source = source
        await session.flush()
        return existing
    profile = ClientProfile(
        tenant_id=tenant_id,
        user_account_id=None,
        name=cleaned_name,
        phone=normalized,
        source=source,
        consents={},
    )
    session.add(profile)
    await session.flush()
    return profile


async def get_user_by_messenger(
    session: AsyncSession, channel: Channel, messenger_user_id: int
) -> UserAccount | None:
    if channel is Channel.TELEGRAM:
        return await session.scalar(
            select(UserAccount).where(UserAccount.telegram_user_id == messenger_user_id)
        )
    return await session.scalar(select(UserAccount).where(UserAccount.max_user_id == messenger_user_id))


async def get_or_create_user_by_messenger(
    session: AsyncSession, channel: Channel, messenger_user_id: int
) -> UserAccount:
    user = await get_user_by_messenger(session, channel, messenger_user_id)
    if user is None:
        if channel is Channel.TELEGRAM:
            user = UserAccount(telegram_user_id=messenger_user_id)
        else:
            user = UserAccount(max_user_id=messenger_user_id)
        session.add(user)
        await session.flush()
    return user


async def get_or_create_user_account(session: AsyncSession, telegram_user_id: int) -> UserAccount:
    return await get_or_create_user_by_messenger(session, Channel.TELEGRAM, telegram_user_id)


async def link_messenger_id(
    session: AsyncSession,
    user: UserAccount,
    *,
    channel: Channel,
    messenger_user_id: int,
) -> UserAccount:
    field = channel.user_id_field
    existing_val = getattr(user, field)
    if existing_val is not None and int(existing_val) != messenger_user_id:
        raise ConflictError(f"{field} already set on account")
    conflict = await get_user_by_messenger(session, channel, messenger_user_id)
    if conflict is not None and conflict.id != user.id:
        raise ConflictError("messenger id linked to another account")
    setattr(user, field, messenger_user_id)
    await session.flush()
    return user


async def merge_user_accounts(
    session: AsyncSession, primary_id: UUID, secondary_id: UUID
) -> UserAccount:
    if primary_id == secondary_id:
        primary = await session.get(UserAccount, primary_id)
        if primary is None:
            raise ValidationError("account not found")
        return primary

    primary = await session.get(UserAccount, primary_id)
    secondary = await session.get(UserAccount, secondary_id)
    if primary is None or secondary is None:
        raise ValidationError("account not found")

    tg_from_secondary = secondary.telegram_user_id
    max_from_secondary = secondary.max_user_id

    if (
        tg_from_secondary
        and primary.telegram_user_id
        and tg_from_secondary != primary.telegram_user_id
    ):
        raise ConflictError("both accounts have different telegram ids")

    if (
        max_from_secondary
        and primary.max_user_id
        and max_from_secondary != primary.max_user_id
    ):
        raise ConflictError("both accounts have different max ids")

    secondary.telegram_user_id = None
    secondary.max_user_id = None
    await session.flush()

    if tg_from_secondary and not primary.telegram_user_id:
        primary.telegram_user_id = tg_from_secondary
    if max_from_secondary and not primary.max_user_id:
        primary.max_user_id = max_from_secondary
    await session.flush()

    prefs = {**(secondary.messenger_prefs or {}), **(primary.messenger_prefs or {})}
    primary.messenger_prefs = prefs

    for profile in (
        await session.scalars(select(ClientProfile).where(ClientProfile.user_account_id == secondary.id))
    ).all():
        duplicate = await session.scalar(
            select(ClientProfile).where(
                ClientProfile.tenant_id == profile.tenant_id,
                ClientProfile.user_account_id == primary.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("client profile conflict on merge")
        profile.user_account_id = primary.id

    for staff in (
        await session.scalars(select(StaffMember).where(StaffMember.user_account_id == secondary.id))
    ).all():
        duplicate = await session.scalar(
            select(StaffMember).where(
                StaffMember.tenant_id == staff.tenant_id,
                StaffMember.user_account_id == primary.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("staff profile conflict on merge")
        staff.user_account_id = primary.id

    await session.delete(secondary)
    await session.flush()
    if primary.telegram_user_id is None and primary.max_user_id is None:
        raise ValidationError("merged account has no messenger ids")
    return primary


async def register_client(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_account_id: UUID,
    name: str,
    phone: str,
    source: str | None = None,
) -> ClientProfile:
    normalized = normalize_phone(phone)
    existing = await session.scalar(
        select(ClientProfile).where(
            ClientProfile.tenant_id == tenant_id,
            ClientProfile.phone == normalized,
        )
    )
    if existing is not None:
        existing.user_account_id = user_account_id
        existing.name = name
        existing.consents = {**existing.consents, "pd_consent": True}
        return existing

    profile = ClientProfile(
        tenant_id=tenant_id,
        user_account_id=user_account_id,
        name=name,
        phone=normalized,
        source=source,
        consents={"pd_consent": True},
    )
    session.add(profile)
    await session.flush()
    return profile


async def upsert_client_profile(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_account_id: UUID,
    name: str,
    phone: str | None,
    source: str | None = None,
) -> ClientProfile:
    """Create or update the client card of a signed-in user (one card per user per tenant)."""
    own = await session.scalar(
        select(ClientProfile).where(
            ClientProfile.tenant_id == tenant_id,
            ClientProfile.user_account_id == user_account_id,
        )
    )
    if own is None:
        if not phone:
            raise ValidationError("phone is required")
        return await register_client(
            session,
            tenant_id=tenant_id,
            user_account_id=user_account_id,
            name=name,
            phone=phone,
            source=source,
        )
    if name:
        own.name = name
    if phone:
        normalized = normalize_phone(phone)
        taken = await session.scalar(
            select(ClientProfile).where(
                ClientProfile.tenant_id == tenant_id,
                ClientProfile.phone == normalized,
                ClientProfile.id != own.id,
            )
        )
        if taken is None:
            own.phone = normalized
    own.consents = {**own.consents, "pd_consent": True}
    await session.flush()
    return own