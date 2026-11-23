import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import BotAlreadyLinkedError
from app.domain.models import Tenant
from app.domain.services.provisioning import attach_max_bot_token, attach_telegram_bot_token, create_tenant_for_owner


@pytest.mark.asyncio
async def test_attach_max_bot_rejects_other_tenant(session: AsyncSession) -> None:
    t1 = await create_tenant_for_owner(
        session,
        owner_telegram_id=1,
        business_name="A",
        owner_display_name="O",
        public_id="tenant-a",
    )
    await attach_max_bot_token(session, t1, bot_token="tok1", bot_id=100, bot_username="maxa")
    t2 = await create_tenant_for_owner(
        session,
        owner_telegram_id=2,
        business_name="B",
        owner_display_name="O",
        public_id="tenant-b",
    )
    await session.commit()
    with pytest.raises(BotAlreadyLinkedError):
        await attach_max_bot_token(session, t2, bot_token="tok2", bot_id=100, bot_username="maxa")


@pytest.mark.asyncio
async def test_dual_channel_same_tenant(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session,
        owner_telegram_id=11,
        business_name="Dual",
        owner_display_name="Owner",
        public_id="dual-tenant",
    )
    await attach_telegram_bot_token(session, tenant, bot_token="123:abc", bot_id=222, bot_username="tg_bot")
    await attach_max_bot_token(session, tenant, bot_token="maxtok", bot_id=333, bot_username="max_bot")
    await session.commit()
    loaded = await session.get(Tenant, tenant.id)
    assert loaded is not None
    assert loaded.bot_id == 222
    assert loaded.max_bot_id == 333