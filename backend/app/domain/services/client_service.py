import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ClientProfile, UserAccount


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    return digits


async def get_or_create_user_account(session: AsyncSession, telegram_user_id: int) -> UserAccount:
    user = await session.scalar(select(UserAccount).where(UserAccount.telegram_user_id == telegram_user_id))
    if user is None:
        user = UserAccount(telegram_user_id=telegram_user_id)
        session.add(user)
        await session.flush()
    return user


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
