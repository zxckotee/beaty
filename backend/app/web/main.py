"""Web cabinet (manager / specialist / client) served over plain HTTP on port 3030."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging_config import setup_logging
from app.core.redis_client import close_redis
from app.core.sentry_init import init_sentry
from app.domain.exceptions import (
    CellInUseError,
    CellOverlapError,
    ConflictError,
    DoesNotFitError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    SlotTakenError,
    ValidationError,
)
from app.domain.models import StaffMember, Tenant
from app.web.routes import analytics, auth, client, landing, manager, messages, schedule, site_root, staff_schedule, test_login
from app.web.uploads import media_root

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (NotFoundError, 404),
    (ValidationError, 400),
    (ForbiddenError, 403),
    (CellOverlapError, 409),
    (CellInUseError, 409),
    (SlotTakenError, 409),
    (DoesNotFitError, 409),
    (ConflictError, 409),
)

CSP_BROWSER = (
    "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline' https://unpkg.com; "
    "script-src 'self' https://telegram.org https://unpkg.com; "
    "connect-src 'self' https://*.tile.openstreetmap.org; "
    "frame-src https://*.2gis.ru https://*.2gis.com https://widget.2gis.com https://map-widget.api.2gis.com; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

CSP_TELEGRAM = (
    "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline' https://unpkg.com; "
    "script-src 'self' https://telegram.org https://unpkg.com; "
    "connect-src 'self' https://*.tile.openstreetmap.org; "
    "frame-src https://*.2gis.ru https://*.2gis.com https://widget.2gis.com https://map-widget.api.2gis.com; "
    "frame-ancestors https://web.telegram.org https://telegram.org https://*.telegram.org; "
    "base-uri 'none'; form-action 'self'"
)


def _telegram_miniapp_context(request: Request) -> bool:
    if request.headers.get("sec-fetch-dest") == "iframe":
        return True
    if request.query_params.get("tgWebAppData") or request.query_params.get("tgWebAppVersion"):
        return True
    referer = (request.headers.get("referer") or "").lower()
    return "telegram" in referer


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    setup_logging()
    init_sentry()
    media_root()
    yield
    await close_redis()


app = FastAPI(title="Beaty Web", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if _telegram_miniapp_context(request):
        csp = CSP_TELEGRAM
    else:
        csp = CSP_BROWSER
    response.headers.setdefault("Content-Security-Policy", csp)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    status = next((code for cls, code in _STATUS_BY_ERROR if isinstance(exc, cls)), 400)
    return JSONResponse({"detail": str(exc), "code": type(exc).__name__}, status_code=status)


app.include_router(site_root.router)
app.include_router(test_login.router)
app.include_router(auth.router)
app.include_router(schedule.router)
app.include_router(analytics.router)
app.include_router(manager.router)
app.include_router(staff_schedule.router)
app.include_router(client.router)
app.include_router(landing.public_router)
app.include_router(landing.manager_router)
app.include_router(messages.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/media/tg/{tenant_public_id}/{staff_member_id}")
async def telegram_photo(tenant_public_id: str, staff_member_id: UUID) -> FileResponse:
    """Serve a specialist photo that was uploaded through the bot (Telegram file_id), cached on disk."""
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
        staff = await session.get(StaffMember, staff_member_id)
        if tenant is None or staff is None or staff.tenant_id != tenant.id or not staff.photo_file_id:
            raise HTTPException(status_code=404, detail="not found")
        file_id = staff.photo_file_id
    cache_dir = media_root() / "tg"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{hashlib.sha256(file_id.encode()).hexdigest()}.jpg"
    if not cached.exists():
        from app.bot.registry import get_bot_for_tenant

        try:
            bot = get_bot_for_tenant(tenant)
            await bot.download(file_id, destination=cached)
        except Exception:
            logger.warning("telegram photo download failed tenant=%s", tenant_public_id, exc_info=True)
            cached.unlink(missing_ok=True)
            raise HTTPException(status_code=404, detail="not found") from None
    return FileResponse(cached, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


app.mount("/media", StaticFiles(directory=media_root()), name="media")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/t/{tenant_public_id}")
@app.get("/t/{tenant_public_id}/")
async def spa(tenant_public_id: str) -> FileResponse:
    return _index()


@app.get("/t/{tenant_public_id}/studio")
@app.get("/t/{tenant_public_id}/studio/")
async def studio_redirect(tenant_public_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/t/{tenant_public_id}/", status_code=301)


