"""Public Beaty platform site (no tenant)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.settings import get_settings

router = APIRouter(tags=["site"])

_STATIC = Path(__file__).resolve().parent.parent / "static"
_PLATFORM_HTML = _STATIC / "platform.html"
_PLATFORM_DOCS_HTML = _STATIC / "platform-docs.html"
_LEGAL_DIR = _STATIC / "legal"

_LEGAL_PAGES = {
    "privacy": "privacy.html",
    "offer": "offer.html",
    "pd-processing": "pd-processing.html",
    "salon-privacy": "salon-privacy.html",
    "marketing-consent": "marketing-consent.html",
    "reviews-policy": "reviews-policy.html",
}


@router.get("/api/platform")
async def platform_meta() -> dict[str, str | None]:
    settings = get_settings()
    demo = (settings.web_default_tenant or "").strip() or None
    return {
        "product": "Beaty",
        "tagline": "Онлайн-запись и кабинет салона в Telegram",
        "demo_tenant_id": demo,
    }


@router.get("/", response_model=None)
async def site_root() -> FileResponse:
    return FileResponse(_PLATFORM_HTML, headers={"Cache-Control": "no-cache"})


@router.get("/docs", response_model=None)
async def platform_docs_page() -> FileResponse:
    return FileResponse(_PLATFORM_DOCS_HTML, headers={"Cache-Control": "no-cache"})


@router.get("/legal/{page}", response_model=None)
async def legal_page(page: str) -> FileResponse:
    fname = _LEGAL_PAGES.get(page)
    if not fname:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="not found")
    path = _LEGAL_DIR / fname
    if not path.is_file():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, headers={"Cache-Control": "no-cache"})