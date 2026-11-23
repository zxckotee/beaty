"""Redis state for attaching a second messenger bot to an existing tenant via platform bots."""

from __future__ import annotations

import json
import secrets

from app.core.redis_client import get_redis
from app.messenger.types import Channel

_TTL = 900


def _key(owner_id: int, channel: Channel) -> str:
    return f"platlink:{channel.value}:{owner_id}"


async def start_dual_attach(owner_id: int, channel: Channel, *, has_other: bool) -> None:
    redis = await get_redis()
    await redis.set(
        _key(owner_id, channel),
        json.dumps({"step": "other_token" if has_other else "first_token", "has_other": has_other}),
        ex=_TTL,
    )


async def get_dual_attach(owner_id: int, channel: Channel) -> dict | None:
    redis = await get_redis()
    raw = await redis.get(_key(owner_id, channel))
    if raw is None:
        return None
    data = json.loads(raw)
    return data if isinstance(data, dict) else None


async def set_dual_attach_step(owner_id: int, channel: Channel, step: str, **extra: object) -> None:
    redis = await get_redis()
    current = await get_dual_attach(owner_id, channel) or {}
    current.update({"step": step, **extra})
    await redis.set(_key(owner_id, channel), json.dumps(current), ex=_TTL)


async def clear_dual_attach(owner_id: int, channel: Channel) -> None:
    redis = await get_redis()
    await redis.delete(_key(owner_id, channel))