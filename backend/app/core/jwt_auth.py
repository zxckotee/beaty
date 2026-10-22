from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.settings import get_settings


def create_access_token(
    *,
    tenant_public_id: str,
    user_account_id: UUID,
    roles: list[str],
) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_account_id),
        "tenant": tenant_public_id,
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, object]:
    payload: dict[str, object] = jwt.decode(
        token, get_settings().jwt_secret, algorithms=["HS256"]
    )
    return payload
