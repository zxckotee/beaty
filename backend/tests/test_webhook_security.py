import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.provisioning import create_tenant_for_owner
from app.main import app
from tests.conftest import random_telegram_id


@pytest.fixture
async def webhook_http(monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    monkeypatch.setenv("PLATFORM_BOT_TOKEN", "123456:platform-test-token")
    monkeypatch.setenv("PLATFORM_TELEGRAM_WEBHOOK_SECRET", "super-platform-secret")
    from app.core.settings import get_settings

    get_settings.cache_clear()

    async def _dedupe(*_args: object, **_kwargs: object) -> bool:
        return True

    async def _feed(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.webhook.routes._dedupe_update", _dedupe)
    monkeypatch.setattr("app.webhook.routes.platform_dispatcher.feed_update", _feed)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_platform_webhook_rejects_bad_secret(webhook_http: httpx.AsyncClient) -> None:
    r = await webhook_http.post(
        "/tg/platform",
        headers={"x-telegram-bot-api-secret-token": "wrong"},
        content=json.dumps({"update_id": 1}),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_platform_webhook_accepts_valid_secret(webhook_http: httpx.AsyncClient) -> None:
    r = await webhook_http.post(
        "/tg/platform",
        headers={"x-telegram-bot-api-secret-token": "super-platform-secret"},
        content=json.dumps({"update_id": 900001}),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_tenant_webhook_requires_secret(
    session: AsyncSession,
    webhook_http: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _dedupe(*_args: object, **_kwargs: object) -> bool:
        return True

    monkeypatch.setattr("app.webhook.routes._dedupe_update", _dedupe)
    tenant = await create_tenant_for_owner(
        session,
        owner_telegram_id=random_telegram_id(),
        business_name="Webhook salon",
        owner_display_name="Owner",
    )
    tenant.webhook_secret = None
    await session.commit()

    r = await webhook_http.post(f"/tg/{tenant.public_id}", content=json.dumps({"update_id": 2}))
    assert r.status_code == 503

    tenant.webhook_secret = "tenant-secret-value"
    await session.commit()

    r = await webhook_http.post(
        f"/tg/{tenant.public_id}",
        headers={"x-telegram-bot-api-secret-token": "wrong"},
        content=json.dumps({"update_id": 3}),
    )
    assert r.status_code == 403

    from app.domain.services.provisioning import attach_bot_token

    await attach_bot_token(
        session,
        tenant,
        bot_token="123456:test-webhook-bot",
        bot_id=900_001_234,
        bot_username="test_webhook_bot",
    )
    await session.commit()

    r = await webhook_http.post(
        f"/tg/{tenant.public_id}",
        headers={"x-telegram-bot-api-secret-token": "tenant-secret-value"},
        content=json.dumps({"update_id": 4}),
    )
    assert r.status_code == 200