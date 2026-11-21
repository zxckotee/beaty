from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://beaty:beaty@localhost:5432/beaty"
    redis_url: str = "redis://localhost:6379/0"

    platform_bot_token: str = ""
    webhook_base_url: str = "http://localhost:8000"
    public_web_url: str = ""
    token_encryption_key: str = "change-me-32-bytes-base64-fernet-key!!"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "beaty"
    s3_region: str = "us-east-1"

    sentry_dsn: str = ""

    jwt_secret: str = "dev-jwt-secret-change-in-prod"
    jwt_ttl_minutes: int = 60

    telegram_proxy: str = ""
    run_scheduler_in_api: bool = True

    hold_ttl_seconds: int = 600
    environment: str = "development"
    tenant_ui_mode: str = "bot"  # bot | miniapp | both (miniapp disabled in code)
    enable_public_api: bool = False

    web_ui_port: int = 3030
    media_dir: str = "./media"
    web_default_tenant: str = ""
    web_cookie_secure: bool = False
    web_session_days: int = 14
    web_dev_login: bool = False
    web_max_upload_bytes: int = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
