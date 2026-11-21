import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_bot_token
from app.domain.services.provisioning import create_tenant_for_owner
from app.web.main import app
from tests.conftest import random_telegram_id


@pytest.fixture
async def web_client() -> AsyncIterator[httpx.AsyncClient]:
    from app.core.db import engine

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await engine.dispose()


def _init_data(bot_token: str, user_id: int) -> str:
    user = f'{{"id":{user_id},"first_name":"Mini"}}'
    auth_date = str(int(time.time()))
    pairs = {"auth_date": auth_date, "user": user}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    check_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": check_hash})


@pytest.mark.asyncio
async def test_auth_telegram_sets_session(session: AsyncSession, web_client: httpx.AsyncClient) -> None:
    bot_token = "5768333441:AAHkT0X7G8m9Y8Z7X6W5V4U3T2S1R0Q9P8O7N6"
    tg = random_telegram_id()
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="Mini", owner_display_name="O"
    )
    tenant.bot_token_encrypted = encrypt_bot_token(bot_token)
    tenant.bot_username = "mini_bot"
    await session.commit()

    init_data = _init_data(bot_token, tg)
    r = await web_client.post(f"/api/t/{tenant.public_id}/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "confirmed"

    me = await web_client.get(f"/api/t/{tenant.public_id}/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is True