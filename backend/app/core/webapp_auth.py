"""Validate WebApp initData for Telegram and MAX (same HMAC algorithm)."""

from app.core.telegram_auth import verify_webapp_init_data

__all__ = ["verify_webapp_init_data"]