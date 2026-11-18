import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ConflictError
from app.domain.services.card_service import create_service
from app.domain.services.provisioning import create_tenant_for_owner
from tests.conftest import random_telegram_id


@pytest.mark.asyncio
async def test_create_service_duplicate_rejected(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="Dup", owner_display_name="O"
    )
    await create_service(
        session, tenant=tenant, name="Стрижка", price_cents=1000, duration_minutes=30, replace_existing=False
    )
    with pytest.raises(ConflictError):
        await create_service(
            session, tenant=tenant, name="  стрижка ", price_cents=2000, duration_minutes=40, replace_existing=False
        )
    replaced = await create_service(
        session, tenant=tenant, name="Стрижка", price_cents=2000, duration_minutes=40, replace_existing=True
    )
    assert replaced.price_cents == 2000
    await session.rollback()