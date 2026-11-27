"""Public Beaty-Welcome platform site (no tenant)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.content.legal_documents import (
    get_legal_document,
    legal_document_as_dict,
    operator_block,
    related_legal_links,
)
from app.core.settings import get_settings

router = APIRouter(tags=["site"])

_STATIC = Path(__file__).resolve().parent.parent / "static"
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
_PLATFORM_HTML = _STATIC / "platform.html"
_PLATFORM_DOCS_HTML = _STATIC / "platform-docs.html"


@router.get("/api/platform")
async def platform_meta() -> dict[str, str | None]:
    settings = get_settings()
    demo = (settings.web_default_tenant or "").strip() or None
    return {
        "product": "Beaty-Welcome",
        "tagline": "Онлайн-запись и кабинет салона в Telegram",
        "demo_tenant_id": demo,
    }


@router.get("/", response_model=None)
async def site_root() -> FileResponse:
    return FileResponse(_PLATFORM_HTML, headers={"Cache-Control": "no-cache"})


@router.get("/docs", response_model=None)
async def platform_docs_page() -> FileResponse:
    return FileResponse(_PLATFORM_DOCS_HTML, headers={"Cache-Control": "no-cache"})


@router.get("/legal/{page}", response_class=HTMLResponse)
async def legal_page(request: Request, page: str) -> HTMLResponse:
    doc = get_legal_document(page)
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")
    response = templates.TemplateResponse(
        request,
        "legal_page.html",
        {
            "doc": legal_document_as_dict(doc),
            "operator": operator_block(),
            "related_links": related_legal_links(page),
            "current_slug": page,
        },
    )
    response.headers["Cache-Control"] = "no-cache"
    return response