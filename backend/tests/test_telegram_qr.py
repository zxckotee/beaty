from app.bot.telegram_qr import qr_png_bytes
from app.content.user_guide import telegram_bot_url


def test_qr_png_not_empty() -> None:
    url = telegram_bot_url("demo_salon_bot", start="book")
    raw = qr_png_bytes(url)
    assert len(raw) > 200
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_telegram_bot_url() -> None:
    assert telegram_bot_url("mybot", start="book") == "https://t.me/mybot?start=book"