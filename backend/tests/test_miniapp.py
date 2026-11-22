import pytest

from app.bot import miniapp as miniapp_mod
from app.core.settings import get_settings
from app.domain.models import Tenant


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_miniapp_enabled_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_UI_MODE", "bot")
    get_settings.cache_clear()
    assert miniapp_mod.miniapp_enabled() is False

    monkeypatch.setenv("TENANT_UI_MODE", "both")
    get_settings.cache_clear()
    assert miniapp_mod.miniapp_enabled() is True

    monkeypatch.setenv("TENANT_UI_MODE", "miniapp")
    get_settings.cache_clear()
    assert miniapp_mod.miniapp_enabled() is True


def test_miniapp_url_requires_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_UI_MODE", "both")
    monkeypatch.setenv("PUBLIC_WEB_URL", "http://localhost:3030")
    get_settings.cache_clear()
    tenant = Tenant(public_id="demo", name="Demo", bot_username="demo_bot", bot_token_encrypted="x")
    assert miniapp_mod.miniapp_url_for_tenant(tenant) is None

    monkeypatch.setenv("PUBLIC_WEB_URL", "https://betwelc.ru")
    get_settings.cache_clear()
    url = miniapp_mod.miniapp_url_for_tenant(tenant)
    assert url == "https://betwelc.ru/t/demo/"


def test_bot_reply_keyboard_only_in_bot_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_UI_MODE", "miniapp")
    get_settings.cache_clear()
    assert miniapp_mod.bot_reply_keyboard_enabled() is False
    assert miniapp_mod.bot_chat_write_enabled() is False

    monkeypatch.setenv("TENANT_UI_MODE", "both")
    get_settings.cache_clear()
    assert miniapp_mod.bot_reply_keyboard_enabled() is False
    assert miniapp_mod.bot_chat_write_enabled() is False

    monkeypatch.setenv("TENANT_UI_MODE", "bot")
    get_settings.cache_clear()
    assert miniapp_mod.bot_reply_keyboard_enabled() is True
    assert miniapp_mod.bot_chat_write_enabled() is True
