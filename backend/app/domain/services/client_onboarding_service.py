from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ClientProfile, UserAccount
from app.domain.services.client_service import get_or_create_user_by_messenger, register_client
from app.messenger.types import Channel


async def ensure_user_account(
    session: AsyncSession, messenger_user_id: int, *, channel: Channel = Channel.TELEGRAM
) -> UserAccount:
    return await get_or_create_user_by_messenger(session, channel, messenger_user_id)


async def complete_client_onboarding(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    messenger_user_id: int,
    channel: Channel = Channel.TELEGRAM,
    name: str,
    phone: str,
    source: str | None = None,
    marketing_opt_in: bool = False,
) -> ClientProfile:
    user = await get_or_create_user_by_messenger(session, channel, messenger_user_id)
    profile = await register_client(
        session,
        tenant_id=tenant_id,
        user_account_id=user.id,
        name=name,
        phone=phone,
        source=source,
    )
    profile.consents = {
        **profile.consents,
        "pd_consent": True,
        "marketing": marketing_opt_in,
    }
    await session.flush()
    return profile


def client_has_phone(profile: ClientProfile | None) -> bool:
    if profile is None:
        return False
    if not profile.consents.get("pd_consent"):
        return False
    phone = (profile.phone or "").strip()
    return len(phone) >= 10
