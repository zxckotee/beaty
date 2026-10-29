from app.bot.telegram_format import bot_mention_html


def test_bot_mention_preserves_underscores() -> None:
    html = bot_mention_html("barber228_edward_bot")
    assert "barber228_edward_bot" in html
    assert 'href="https://t.me/barber228_edward_bot"' in html
