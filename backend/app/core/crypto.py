import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.settings import get_settings


def _fernet() -> Fernet:
    raw = get_settings().token_encryption_key.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_bot_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_bot_token(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode()).decode()
