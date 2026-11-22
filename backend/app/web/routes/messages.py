from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.models import NotificationTemplate
from app.domain.services.message_tokens import DEFAULT_BODIES, TOKEN_PREVIEW_CONTEXT, render_template
from app.domain.user_labels import message_token_choices
from app.web.deps import WebContext, require_manager, writable
from app.web.uploads import save_image

router = APIRouter(prefix="/api/t/{tenant_public_id}/manager/messages", tags=["messages"])

TEMPLATE_KINDS = ("booking_confirmed", "reminder_24h", "reminder_2h", "booking_cancelled")

class TemplatePatch(BaseModel):
    body: str = Field(default="", max_length=8000)
    parse_mode: str = Field(default="HTML", max_length=16)
    photo_slots: list[str | dict[str, str]] = Field(default_factory=list, max_length=10)


class PreviewIn(BaseModel):
    kind: str
    body: str = Field(max_length=8000)


@router.get("/meta")
async def template_meta(ctx: WebContext = Depends(require_manager)) -> dict[str, object]:
    writable(ctx)
    return {"kinds": TEMPLATE_KINDS, "tokens": message_token_choices(), "defaults": DEFAULT_BODIES}


@router.get("")
async def list_templates(
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    rows = (
        await session.scalars(select(NotificationTemplate).where(NotificationTemplate.tenant_id == tenant.id))
    ).all()
    by_kind = {r.kind: {"body": r.body, "parse_mode": r.parse_mode, "photo_slots": r.photo_slots or []} for r in rows}
    out = {}
    for kind in TEMPLATE_KINDS:
        out[kind] = by_kind.get(kind) or {
            "body": DEFAULT_BODIES.get(kind, ""),
            "parse_mode": "HTML",
            "photo_slots": [],
        }
    return {"templates": out}


@router.put("/{kind}")
async def put_template(
    kind: str,
    body: TemplatePatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    if kind not in TEMPLATE_KINDS:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="unknown kind")
    tenant = writable(ctx)
    tpl = await session.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.tenant_id == tenant.id, NotificationTemplate.kind == kind
        )
    )
    if tpl is None:
        tpl = NotificationTemplate(tenant_id=tenant.id, kind=kind)
        session.add(tpl)
    tpl.body = body.body
    tpl.parse_mode = body.parse_mode
    tpl.photo_slots = body.photo_slots
    await session.commit()
    return {"kind": kind, "body": tpl.body, "parse_mode": tpl.parse_mode, "photo_slots": tpl.photo_slots}


@router.post("/photo")
async def upload_template_photo(
    file: UploadFile = File(...),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    url = await save_image(file, tenant.id)
    await session.commit()
    return {"url": url}


@router.post("/preview")
async def preview_template(
    body: PreviewIn,
    ctx: WebContext = Depends(require_manager),
) -> dict[str, str]:
    writable(ctx)
    text = render_template(body.body, TOKEN_PREVIEW_CONTEXT)
    return {"text": text}