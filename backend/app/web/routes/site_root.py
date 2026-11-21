"""Production site root — no tenant enumeration."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.core.settings import get_settings

router = APIRouter(tags=["site"])


@router.get("/", response_model=None)
async def site_root() -> RedirectResponse:
    settings = get_settings()
    tenant = (settings.web_default_tenant or "").strip()
    if tenant:
        return RedirectResponse(url=f"/t/{tenant}/", status_code=302)
    raise HTTPException(status_code=404, detail="not found")