from app.core.crypto import decrypt_bot_token, encrypt_bot_token


def test_token_encryption_roundtrip() -> None:
    token = "123456:ABC-DEF"
    enc = encrypt_bot_token(token)
    assert enc != token
    assert decrypt_bot_token(enc) == token
