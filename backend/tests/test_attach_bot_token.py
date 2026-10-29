import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.exceptions import BotAlreadyLinkedError
from app.domain.models import Tenant
from app.domain.services.provisioning import attach_bot_token


def _tenant(*, bot_id: int | None = None) -> MagicMock:
    tenant = MagicMock(spec=Tenant)
    tenant.id = uuid.uuid4()
    tenant.public_id = "pub-" + uuid.uuid4().hex[:8]
    tenant.bot_id = bot_id
    return tenant


@pytest.mark.asyncio
async def test_attach_bot_token_rejects_bot_linked_to_other_tenant() -> None:
    current = _tenant()
    other = _tenant(bot_id=8359112669)
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=other)

    with pytest.raises(BotAlreadyLinkedError):
        await attach_bot_token(
            session,
            current,
            bot_token="123456:AATestTokenValueForUnitTest",
            bot_id=8359112669,
            bot_username="azazel_ai_bot",
        )


@pytest.mark.asyncio
async def test_attach_bot_token_allows_same_tenant_reattach() -> None:
    tenant = _tenant(bot_id=8359112669)
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=tenant)

    await attach_bot_token(
        session,
        tenant,
        bot_token="123456:AATestTokenValueForUnitTest",
        bot_id=8359112669,
        bot_username="azazel_ai_bot",
    )

    assert tenant.bot_id == 8359112669
    assert tenant.bot_username == "azazel_ai_bot"
    assert tenant.bot_status == "active"
    assert tenant.bot_token_encrypted


@pytest.mark.asyncio
async def test_attach_bot_token_allows_unused_bot_id() -> None:
    tenant = _tenant()
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    await attach_bot_token(
        session,
        tenant,
        bot_token="123456:AATestTokenValueForUnitTest",
        bot_id=111222333,
        bot_username="new_salon_bot",
    )

    assert tenant.bot_id == 111222333
    assert tenant.bot_username == "new_salon_bot"
    assert tenant.bot_status == "active"
