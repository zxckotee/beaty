from fastapi import HTTPException, Request

from app.core.redis_client import get_redis


async def limit_by_ip(request: Request, bucket: str, *, limit: int, window_seconds: int = 60) -> None:
    client_ip = request.client.host if request.client else "unknown"
    redis = await get_redis()
    key = f"rl:{bucket}:{client_ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > limit:
        raise HTTPException(status_code=429, detail="too many requests")
