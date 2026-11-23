from app.max.session import aiogram_token_stub, create_max_bot


def test_aiogram_token_stub_for_max_secret() -> None:
    secret = "a" * 64
    assert aiogram_token_stub(secret) == f"9:{secret}"


def test_aiogram_token_stub_passthrough_telegram() -> None:
    tg = "123456:ABC-DEF"
    assert aiogram_token_stub(tg) == tg


def test_create_max_bot_accepts_max_token() -> None:
    bot = create_max_bot("x" * 40)
    assert bot.token == f"9:{'x' * 40}"