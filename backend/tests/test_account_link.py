import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.account_link_service import create_account_link_code, parse_link_code, start_param_for_link
from app.domain.services.client_service import get_or_create_user_by_messenger, merge_user_accounts
from app.messenger.types import Channel


@pytest.mark.asyncio
async def test_merge_user_accounts(session: AsyncSession) -> None:
    tg = await get_or_create_user_by_messenger(session, Channel.TELEGRAM, 9001)
    mx = await get_or_create_user_by_messenger(session, Channel.MAX, 9002)
    await session.flush()
    merged = await merge_user_accounts(session, tg.id, mx.id)
    assert merged.telegram_user_id == 9001
    assert merged.max_user_id == 9002
    await session.commit()


def test_parse_link_code() -> None:
    assert parse_link_code(start_param_for_link("abc12345")) == "abc12345"
    assert parse_link_code("web_code") is None


@pytest.mark.asyncio
async def test_create_link_code() -> None:
    from redis.asyncio import Redis

    from app.core import redis_client as rc
    from app.core.settings import get_settings

    rc._redis = None
    probe = Redis.from_url(get_settings().redis_url)
    try:
        await probe.ping()
    except Exception as exc:
        pytest.skip(f"redis: {exc}")
    finally:
        await probe.aclose()
    code = await create_account_link_code(
        tenant_public_id="t1", user_account_id="00000000-0000-0000-0000-000000000001", channel=Channel.TELEGRAM
    )
    assert len(code) >= 8