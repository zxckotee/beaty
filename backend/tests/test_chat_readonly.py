import pytest

from app.bot.chat_readonly import is_write_callback
from app.bot.shared import CHAT_WRITE_DISABLED, assert_can_write
from app.core.settings import get_settings
from app.domain.exceptions import DomainError
from app.domain.models import Tenant
from app.domain.services.notification_templates import build_notification_message


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("confirm_visit:abc", True),
        ("fm:1:0", True),
        ("c:ok:123", True),
        ("c:slot:tok", True),
        ("c:cn:ask:1", True),
        ("c:wait:svc:2026-01-01", True),
        ("c:rv:1:5", True),
        ("m:mb:st:1", True),
        ("m:bcn:1", True),
        ("m:svc:add", True),
        ("m:svc:toggle:1", True),
        ("m:team:add", True),
        ("s:st:menu:1", True),
        ("s:sick:day", True),
        ("c:my:123", False),
        ("m:day:0:", False),
        ("m:bdg:1", False),
        ("m:svc:view:1", False),
        ("m:team:view:1", False),
        ("m:team:list", False),
        ("m:more:pending", False),
        ("c:onb:name:ok", False),
        ("ui:role:client", False),
    ],
)
def test_is_write_callback(data: str, expected: bool) -> None:
    assert is_write_callback(data) is expected


def test_assert_can_write_blocked_in_miniapp_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_UI_MODE", "miniapp")
    get_settings.cache_clear()
    tenant = Tenant(public_id="demo", name="Demo")
    with pytest.raises(DomainError, match=CHAT_WRITE_DISABLED):
        assert_can_write(tenant, read_only=False)


def test_assert_can_write_allows_bot_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_UI_MODE", "bot")
    get_settings.cache_clear()
    tenant = Tenant(public_id="demo", name="Demo")
    assert_can_write(tenant, read_only=False)
    with pytest.raises(DomainError, match="subscription inactive"):
        assert_can_write(tenant, read_only=True)


def test_reminder_keyboard_is_view_only_without_chat_writes() -> None:
    text, markup = build_notification_message(
        "reminder_24h",
        {"booking_id": "b1", "text": "Напоминание"},
        chat_writes=False,
        miniapp_url="https://example.com/t/demo/",
    )
    assert "Напоминание" in text
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    kinds = {
        (btn.text, btn.callback_data, btn.web_app.url if btn.web_app else None) for btn in buttons
    }
    assert ("Мои записи", "c:my:b1", None) in kinds
    assert ("Открыть", None, "https://example.com/t/demo/") in kinds
    assert all(btn.callback_data != "confirm_visit:b1" for btn in buttons)


def test_reminder_keyboard_keeps_confirm_when_chat_writes() -> None:
    _, markup = build_notification_message(
        "reminder_24h",
        {"booking_id": "b1"},
        chat_writes=True,
    )
    assert markup is not None
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "confirm_visit:b1" in callbacks


def test_review_and_force_majeure_redirect_to_miniapp() -> None:
    _, review_markup = build_notification_message(
        "review_request",
        {"booking_id": "b1"},
        chat_writes=False,
        miniapp_url="https://example.com/t/demo/",
    )
    assert review_markup is not None
    review_btn = review_markup.inline_keyboard[0][0]
    assert review_btn.web_app is not None
    assert review_btn.callback_data is None

    _, fm_markup = build_notification_message(
        "force_majeure_options",
        {"booking_id": "b1", "options": [{"label": "Другой мастер"}]},
        chat_writes=False,
        miniapp_url="https://example.com/t/demo/",
    )
    assert fm_markup is not None
    assert fm_markup.inline_keyboard[0][0].web_app is not None
    assert not any(
        (btn.callback_data or "").startswith("fm:")
        for row in fm_markup.inline_keyboard
        for btn in row
    )
