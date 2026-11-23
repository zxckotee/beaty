import pytest
from redis.asyncio import Redis

from app.core import redis_client
from app.core.settings import get_settings
from app.domain.services import web_auth_service as auth


@pytest.fixture(autouse=True)
async def fresh_redis():  # type: ignore[no-untyped-def]
    redis_client._redis = None
    probe = Redis.from_url(get_settings().redis_url)
    try:
        await probe.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"redis is not available: {exc}")
    finally:
        await probe.aclose()
    yield
    await redis_client.close_redis()


def test_start_param_roundtrip() -> None:
    assert auth.parse_login_code(auth.start_param_for("abcdefgh1234")) == "abcdefgh1234"
    assert auth.parse_login_code("inv_abcdefgh1234") is None
    assert auth.parse_login_code("web_x") is None
    assert auth.parse_login_code(None) is None


async def test_login_flow() -> None:
    code = await auth.create_login_request("tenant1")
    assert (await auth.poll_login(code, tenant_public_id="tenant1")).state == "pending"
    ok = await auth.confirm_login(code, tenant_public_id="tenant1", telegram_user_id=42, display_name="Anna")
    assert ok.ok and ok.reason == "ok"
    poll = await auth.poll_login(code, tenant_public_id="tenant1")
    assert poll.state == "confirmed"
    assert poll.telegram_user_id == 42


async def test_code_is_bound_to_tenant() -> None:
    code = await auth.create_login_request("tenant1")
    bad = await auth.confirm_login(code, tenant_public_id="other", telegram_user_id=1, display_name=None)
    assert not bad.ok and bad.reason == "wrong_tenant"
    assert (await auth.poll_login(code, tenant_public_id="other")).state == "expired"
    assert (await auth.poll_login("unknown-code-123", tenant_public_id="tenant1")).state == "expired"


async def test_confirmed_code_is_single_use() -> None:
    code = await auth.create_login_request("tenant1")
    await auth.confirm_login(code, tenant_public_id="tenant1", telegram_user_id=7, display_name=None)
    assert (await auth.poll_login(code, tenant_public_id="tenant1")).state == "confirmed"
    assert (await auth.poll_login(code, tenant_public_id="tenant1")).state == "expired"
    reused = await auth.confirm_login(code, tenant_public_id="tenant1", telegram_user_id=7, display_name=None)
    assert not reused.ok and reused.reason == "missing"


async def test_confirm_idempotent_for_same_user() -> None:
    code = await auth.create_login_request("tenant1")
    first = await auth.confirm_login(code, tenant_public_id="tenant1", telegram_user_id=11, display_name="A")
    assert first.ok and first.reason == "ok"
    again = await auth.confirm_login(code, tenant_public_id="tenant1", telegram_user_id=11, display_name="A")
    assert again.ok and again.reason == "already_ok"
    other = await auth.confirm_login(code, tenant_public_id="tenant1", telegram_user_id=12, display_name="B")
    assert not other.ok and other.reason == "used"