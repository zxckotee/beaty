"""Public Beaty platform site (no tenant)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.settings import get_settings

router = APIRouter(tags=["site"])

_STATIC = Path(__file__).resolve().parent.parent / "static"
_PLATFORM_HTML = _STATIC / "platform.html"


@router.get("/api/platform")
async def platform_meta() -> dict[str, str | None]:
    settings = get_settings()
    demo = (settings.web_default_tenant or "").strip() or None
    return {
        "product": "Beaty",
        "tagline": "Онлайн-запись и кабинет салона в Telegram и MAX",
        "demo_tenant_id": demo,
    }


@router.get("/", response_model=None)
async def site_root() -> FileResponse:
    return FileResponse(_PLATFORM_HTML, headers={"Cache-Control": "no-cache"})