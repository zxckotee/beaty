"""Telegram Mini App (Web App) helpers."""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.settings import get_settings
from app.domain.models import Tenant


def tenant_ui_mode_allows_miniapp() -> bool:
    mode = get_settings().tenant_ui_mode.strip().lower()
    return mode in {"both", "miniapp"}


def miniapp_enabled() -> bool:
    return tenant_ui_mode_allows_miniapp()


def bot_chat_write_enabled() -> bool:
    """In-chat booking and salon management. Off unless TENANT_UI_MODE=bot.

    Mini App (`miniapp` / `both`) is the only write surface; the chat bot is read-only.
    """
    return get_settings().tenant_ui_mode.strip().lower() == "bot"


def bot_reply_keyboard_enabled() -> bool:
    """Persistent reply keyboard under the input (view buttons, or full bot-mode menu)."""
    return True


def miniapp_open_hint() -> str:
    return "Запись и управление — в мини-приложении."


def resolve_public_web_url() -> str:
    settings = get_settings()
    raw = (settings.public_web_url or "").strip()
    if raw:
        return raw.rstrip("/")
    parsed = urlparse(settings.webhook_base_url.strip())
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def miniapp_url_for_tenant(tenant: Tenant) -> str | None:
    """HTTPS cabinet URL for WebAppInfo; None if Mini App unavailable for this tenant."""
    if not miniapp_enabled():
        return None
    if not tenant.bot_token_encrypted or not tenant.bot_username:
        return None
    base = resolve_public_web_url()
    if not base.startswith("https://"):
        return None
    return f"{base}/t/{tenant.public_id}/"