import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.core.jwt_auth import create_access_token
from app.domain.services.provisioning import create_tenant_for_owner
from tests.conftest import random_telegram_id


def _api_app() -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    return app


@pytest.mark.asyncio
async def test_manager_calendar_cross_tenant_forbidden(session: AsyncSession) -> None:
    owner_a = random_telegram_id()
    owner_b = random_telegram_id()
    tenant_a = await create_tenant_for_owner(
        session, owner_telegram_id=owner_a, business_name="Salon A", owner_display_name="Owner A"
    )
    tenant_b = await create_tenant_for_owner(
        session, owner_telegram_id=owner_b, business_name="Salon B", owner_display_name="Owner B"
    )
    from sqlalchemy import select

    from app.domain.models import StaffMember, UserAccount

    user = await session.scalar(select(UserAccount).where(UserAccount.telegram_user_id == owner_a))
    assert user is not None
    staff_a = await session.scalar(
        select(StaffMember).where(StaffMember.tenant_id == tenant_a.id, StaffMember.user_account_id == user.id)
    )
    assert staff_a is not None
    await session.commit()

    token = create_access_token(
        tenant_public_id=tenant_a.public_id,
        user_account_id=user.id,
        roles=["owner", "manager"],
    )
    app = _api_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/api/v1/manager/calendar",
            params={"tenant_public_id": tenant_b.public_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403, r.text