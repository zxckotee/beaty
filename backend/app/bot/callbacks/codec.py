"""Short callback tokens (Telegram limit 64 bytes) backed by Redis."""

from __future__ import annotations

import json
import secrets
from typing import Any

from app.core.redis_client import get_redis

_PREFIX = "cb:"
_TTL_SECONDS = 1800


async def store_payload(payload: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(6)
    redis = await get_redis()
    await redis.setex(f"{_PREFIX}{token}", _TTL_SECONDS, json.dumps(payload, default=str))
    return token


async def load_payload(token: str) -> dict[str, Any] | None:
    redis = await get_redis()
    raw = await redis.get(f"{_PREFIX}{token}")
    if raw is None:
        return None
    return json.loads(raw)
