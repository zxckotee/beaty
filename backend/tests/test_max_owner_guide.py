from app.bot.common.max_owner_guide import (
    TELEGRAM_MESSAGE_LIMIT,
    max_onboarding_guide_parts,
    max_onboarding_guide_short,
    platform_bot_help_text,
)


def test_max_guide_short_is_compact() -> None:
    text = max_onboarding_guide_short()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert 6 <= len(lines) <= 12
    assert "/maxhelp" in text
    assert "модерац" in text.lower() or "48" in text


def test_max_guide_full_covers_steps() -> None:
    joined = "\n".join(max_onboarding_guide_parts())
    for needle in (
        "MAX для партнёров",
        "48",
        "токен",
        "Чат-боты",
        "вебхук",
        "443",
        "Минцифры",
        "30",
        "8",
        "5",
        "самозанят",
        "поддержк",
    ):
        assert needle.lower() in joined.lower(), needle


def test_max_guide_parts_under_limit() -> None:
    for part in max_onboarding_guide_parts():
        assert len(part) <= TELEGRAM_MESSAGE_LIMIT


def test_platform_help_lists_commands() -> None:
    help_text = platform_bot_help_text()
    assert "/maxhelp" in help_text
    assert "/maxquick" in help_text