"""Optional Mini App entry when TENANT_UI_MODE is miniapp or both."""

from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.settings import get_settings


def miniapp_enabled() -> bool:
    mode = get_settings().tenant_ui_mode.lower()
    return mode in ("miniapp", "both")


def miniapp_book_url(tenant_public_id: str, start_param: str | None = None) -> str:
    settings = get_settings()
    base = settings.miniapp_public_url.rstrip("/")
    path = f"/t/{tenant_public_id}/book"
    if start_param:
        return f"{base}{path}?entry={start_param}"
    return f"{base}{path}"


def miniapp_book_keyboard(tenant_public_id: str, start_param: str | None = None):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Открыть мини-приложение",
        web_app=WebAppInfo(url=miniapp_book_url(tenant_public_id, start_param)),
    )
    return kb.as_markup()
