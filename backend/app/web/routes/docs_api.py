"""Product documentation JSON for platform and tenant web apps."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.content.user_guide import docs_sections, platform_landing_url
from app.web.deps import WebContext, get_context

platform_docs_router = APIRouter(tags=["docs"])
tenant_docs_router = APIRouter(prefix="/api/t/{tenant_public_id}/docs", tags=["docs"])


@platform_docs_router.get("/api/docs/platform")
async def platform_docs() -> dict:
    return {
        "product": "Beaty-Welcome",
        "sections": docs_sections(audience="platform"),
        "legal_links": [
            {"href": "/legal/privacy", "label": "Политика конфиденциальности"},
            {"href": "/legal/offer", "label": "Оферта для салонов"},
            {"href": "/legal/pd-processing", "label": "Поручение на обработку ПДн"},
        ],
        "landing_url": platform_landing_url(),
    }


@tenant_docs_router.get("")
async def tenant_docs(
    ctx: WebContext = Depends(get_context),
) -> dict:
    if ctx and ctx.is_manager:
        sections = docs_sections(audience="manager")
    else:
        sections = docs_sections(audience="client")
    return {
        "sections": sections,
        "legal_links": [
            {"href": "/legal/privacy", "label": "Политика Beaty-Welcome"},
            {"href": "/legal/salon-privacy", "label": "Шаблон политики салона"},
        ],
    }