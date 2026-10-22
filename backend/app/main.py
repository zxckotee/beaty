import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router, manager_router, staff_router
from app.core.logging_config import setup_logging
from app.core.redis_client import close_redis
from app.core.settings import get_settings
from app.webhook.routes import webhook_router
from app.workers.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
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
app.include_router(manager_router, prefix="/api/v1")
app.include_router(staff_router, prefix="/api/v1")
