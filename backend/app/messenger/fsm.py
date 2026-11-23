from __future__ import annotations

import json

from app.core.redis_client import get_redis
from app.messenger.types import Channel

_KEY = "mfsm:{channel}:{tenant}:{user_id}"
_TTL = 86400


async def fsm_get(channel: Channel, tenant_public_id: str, user_id: int) -> dict[str, str]:
    redis = await get_redis()
    raw = await redis.get(_KEY.format(channel=channel.value, tenant=tenant_public_id, user_id=user_id))
    if not raw:
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


async def fsm_set(
    channel: Channel, tenant_public_id: str, user_id: int, state: str | None, **data: str
) -> None:
    redis = await get_redis()
    payload = {"state": state or "", **data}
    await redis.set(
        _KEY.format(channel=channel.value, tenant=tenant_public_id, user_id=user_id),
        json.dumps(payload),
        ex=_TTL,
    )


async def fsm_clear(channel: Channel, tenant_public_id: str, user_id: int) -> None:
    redis = await get_redis()
    await redis.delete(_KEY.format(channel=channel.value, tenant=tenant_public_id, user_id=user_id))