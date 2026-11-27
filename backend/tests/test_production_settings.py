import pytest

from app.core.production_guard import validate_production_settings
from app.core.settings import Settings


def test_production_rejects_default_secrets() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="dev-jwt-secret",
        token_encryption_key="dev-encryption-key-change-me-in-production",
        database_url="postgresql+asyncpg://beaty:beaty@localhost:5432/beaty",
        web_dev_login=True,
        platform_telegram_webhook_secret="",
    )
    with pytest.raises(RuntimeError, match="unsafe production configuration"):
        validate_production_settings(settings)


def test_production_accepts_strong_config() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="x" * 32,
        token_encryption_key="y" * 32,
        database_url="postgresql+asyncpg://beaty:strong-pass-here@postgres:5432/beaty",
        web_dev_login=False,
        platform_telegram_webhook_secret="platform-webhook-secret",
    )
    validate_production_settings(settings)