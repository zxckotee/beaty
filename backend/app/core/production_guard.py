"""Refuse to start in production when secrets or flags are unsafe."""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.settings import Settings

_INSECURE_JWT = frozenset({"dev-jwt-secret", "dev-jwt-secret-change-in-prod", "test-jwt", "ci-jwt"})
_INSECURE_TOKEN_ENC = frozenset(
    {
        "change-me-32-bytes-base64-fernet-key!!",
        "dev-encryption-key-change-me-in-production",
        "test-key",
        "ci-test-key",
    }
)


def _bad_postgres_password(database_url: str) -> bool:
    try:
        parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
        password = parsed.password or ""
    except Exception:
        return True
    return password in {"", "beaty", "CHANGEME_POSTGRES"}


def validate_production_settings(settings: Settings) -> None:
    if settings.environment != "production":
        return
    problems: list[str] = []
    if settings.jwt_secret in _INSECURE_JWT or len(settings.jwt_secret) < 24:
        problems.append("JWT_SECRET must be a strong random value (≥24 chars)")
    if settings.token_encryption_key in _INSECURE_TOKEN_ENC or len(settings.token_encryption_key) < 24:
        problems.append("TOKEN_ENCRYPTION_KEY must be a strong random value (≥24 chars)")
    if _bad_postgres_password(settings.database_url):
        problems.append("DATABASE_URL must not use a default or empty Postgres password")
    if settings.web_dev_login:
        problems.append("WEB_DEV_LOGIN must be false in production")
    if not (settings.platform_telegram_webhook_secret or "").strip():
        problems.append("PLATFORM_TELEGRAM_WEBHOOK_SECRET is required in production")
    if problems:
        joined = "; ".join(problems)
        raise RuntimeError(f"unsafe production configuration: {joined}")