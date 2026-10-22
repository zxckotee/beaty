import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.phase2_routes import phase2_router
from app.core.sentry_init import init_sentry
from app.core.logging_config import setup_logging
from app.core.redis_client import close_redis
from app.core.settings import get_settings
from app.webhook.routes import webhook_router
from app.workers.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_sentry()
    settings = get_settings()
    scheduler_task: asyncio.Task | None = None
    if settings.environment != "test" and settings.run_scheduler_in_api:
        scheduler_task = asyncio.create_task(scheduler_loop())
    yield
    if scheduler_task:
        scheduler_task.cancel()
    await close_redis()


app = FastAPI(title="Beaty API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.miniapp_public_url, "https://web.telegram.org"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(webhook_router)
app.include_router(api_router)
app.include_router(phase2_router)


@app.get("/ready")
async def ready() -> dict[str, str]:
    from sqlalchemy import text

    from app.core.db import SessionLocal
    from app.core.redis_client import get_redis

    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
    redis = await get_redis()
    await redis.ping()
    return {"status": "ready"}
