import pytest

from app.domain.exceptions import ValidationError
from app.web.dev_login import resolve_telegram_user_id


class _Tenant:
    public_id = "demo"
    bot_token_encrypted = None


@pytest.mark.asyncio
async def test_resolve_numeric_id() -> None:
    assert await resolve_telegram_user_id(_Tenant(), "100001") == (100001, None)
    assert await resolve_telegram_user_id(_Tenant(), "@100001") == (100001, None)


@pytest.mark.asyncio
async def test_resolve_bad_username_without_bot() -> None:
    with pytest.raises(ValidationError, match="токена бота"):
        await resolve_telegram_user_id(_Tenant(), "@someuser")