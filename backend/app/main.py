import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.phase2_routes import phase2_router
from app.api.router import api_router
from app.core.logging_config import setup_logging
from app.core.production_guard import validate_production_settings
from app.core.redis_client import close_redis
from app.core.sentry_init import init_sentry
from app.core.settings import get_settings
from app.webhook.routes import webhook_router
from app.workers.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_sentry()
    settings = get_settings()
    validate_production_settings(settings)
    scheduler_task: asyncio.Task | None = None
    if settings.environment != "test" and settings.run_scheduler_in_api:
        scheduler_task = asyncio.create_task(scheduler_loop())
    yield
    if scheduler_task:
        scheduler_task.cancel()
    await close_redis()


app = FastAPI(title="Beaty-Welcome API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_security_headers(request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response
app.include_router(webhook_router)
if settings.enable_public_api:
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
