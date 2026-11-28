from fastapi import HTTPException, Request

from app.core.redis_client import get_redis


def client_ip_from_request(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


async def limit_by_ip(request: Request, bucket: str, *, limit: int, window_seconds: int = 60) -> None:
    client_ip = client_ip_from_request(request)
    redis = await get_redis()
    key = f"rl:{bucket}:{client_ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > limit:
        raise HTTPException(status_code=429, detail="too many requests")
