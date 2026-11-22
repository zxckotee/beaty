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


def test_bot_chat_writes_only_in_bot_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_UI_MODE", "miniapp")
    get_settings.cache_clear()
    assert miniapp_mod.bot_reply_keyboard_enabled() is True
    assert miniapp_mod.bot_chat_write_enabled() is False

    monkeypatch.setenv("TENANT_UI_MODE", "both")
    get_settings.cache_clear()
    assert miniapp_mod.bot_reply_keyboard_enabled() is True
    assert miniapp_mod.bot_chat_write_enabled() is False

    monkeypatch.setenv("TENANT_UI_MODE", "bot")
    get_settings.cache_clear()
    assert miniapp_mod.bot_reply_keyboard_enabled() is True
    assert miniapp_mod.bot_chat_write_enabled() is True


def test_miniapp_open_hint_has_no_slash_commands() -> None:
    hint = miniapp_mod.miniapp_open_hint()
    assert "/" not in hint
    assert "мини-приложении" in hint


def test_view_menu_client_is_bookings_and_help() -> None:
    from app.bot.keyboards.builders import reply_button_texts, view_menu_reply

    texts = reply_button_texts(view_menu_reply(granted_roles={"client"}))
    assert texts == ["Мои записи", "Помощь"]


def test_view_menu_manager_has_no_write_actions() -> None:
    from app.bot.keyboards.builders import reply_button_texts, view_menu_reply

    texts = reply_button_texts(
        view_menu_reply(granted_roles={"owner", "manager", "specialist", "client"})
    )
    assert "Сегодня" in texts
    assert "Мой день" in texts
    assert "Мои записи" in texts
    assert "Команда" in texts
    assert "Услуги" in texts
    assert "Запись" not in texts
    assert "Записать клиента" not in texts
    assert "Ещё" not in texts


def test_tenant_keyboard_is_view_only_in_miniapp_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.bot.keyboards.builders import reply_button_texts, tenant_reply_keyboard

    monkeypatch.setenv("TENANT_UI_MODE", "miniapp")
    get_settings.cache_clear()
    texts = reply_button_texts(
        tenant_reply_keyboard(
            active_ui_role="client",
            can_switch_ui_role=False,
            granted_roles={"client"},
        )
    )
    assert "Мои записи" in texts
    assert "Запись" not in texts
