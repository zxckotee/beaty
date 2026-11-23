"""Load tenant-scoped messenger user context (shared by Telegram and MAX adapters)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ClientProfile, StaffMember, Tenant, UserAccount
from app.domain.services.client_service import get_user_by_messenger
from app.messenger.types import Channel


async def load_messenger_context(
    session: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    messenger_user_id: int,
) -> dict:
    roles: set[str] = {"client"}
    user_account = await get_user_by_messenger(session, channel, messenger_user_id)
    client_profile: ClientProfile | None = None
    staff_member: StaffMember | None = None
    if user_account:
        client_profile = await session.scalar(
            select(ClientProfile).where(
                ClientProfile.tenant_id == tenant.id,
                ClientProfile.user_account_id == user_account.id,
            )
        )
        staff_member = await session.scalar(
            select(StaffMember).where(
                StaffMember.tenant_id == tenant.id,
                StaffMember.user_account_id == user_account.id,
            )
        )
        if staff_member and staff_member.roles:
            roles.update(staff_member.roles)
        if staff_member:
            roles.add("specialist")
    return {
        "tenant": tenant,
        "user_account": user_account,
        "client_profile": client_profile,
        "staff_member": staff_member,
        "roles": roles,
        "messenger_channel": channel,
    }