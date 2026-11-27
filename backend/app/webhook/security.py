"""Telegram webhook secret validation."""

from __future__ import annotations

import hmac

from fastapi import HTTPException

from app.core.settings import get_settings


def verify_platform_webhook_secret(header_value: str | None) -> None:
    settings = get_settings()
    if not (settings.platform_bot_token or "").strip():
        raise HTTPException(status_code=503, detail="platform bot not configured")
    expected = (settings.platform_telegram_webhook_secret or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="platform webhook secret not configured")
    if not header_value or not hmac.compare_digest(header_value, expected):
        raise HTTPException(status_code=403, detail="invalid secret")


def verify_tenant_webhook_secret(header_value: str | None, tenant_secret: str | None) -> None:
    expected = (tenant_secret or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="webhook not configured")
    if not header_value or not hmac.compare_digest(header_value, expected):
        raise HTTPException(status_code=403, detail="invalid secret")