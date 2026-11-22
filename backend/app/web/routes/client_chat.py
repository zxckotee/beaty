from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.registry import get_bot_for_tenant
from app.core.db import get_session
from app.domain.models import ClientChatMessage
from app.domain.services.client_chat_service import (
    list_messages,
    list_telegram_clients,
    send_manager_message,
    serialize_message,
)
from app.web.deps import WebContext, require_manager, writable
from app.web.uploads import media_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/t/{tenant_public_id}/manager/chat", tags=["client-chat"])
media_router = APIRouter(tags=["client-chat-media"])


@router.get("/clients")
async def chat_clients(
    tenant_public_id: str,
    q: str = "",
    limit: int = 30,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return {"items": await list_telegram_clients(session, ctx.tenant, query=q, limit=limit)}


@router.get("/clients/{client_profile_id}/messages")
async def chat_thread(
    tenant_public_id: str,
    client_profile_id: UUID,
    before: UUID | None = None,
    limit: int = 40,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rows = await list_messages(session, ctx.tenant, client_profile_id, before=before, limit=limit)
    return {"messages": [serialize_message(m) for m in rows]}


@router.post("/clients/{client_profile_id}/messages")
async def chat_send(
    tenant_public_id: str,
    client_profile_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    text: str | None = Form(None),
    photo: UploadFile | None = File(None),
    voice: UploadFile | None = File(None),
) -> dict[str, object]:
    writable(ctx)
    photo_bytes: bytes | None = None
    photo_name: str | None = None
    voice_bytes: bytes | None = None
    voice_name: str | None = None
    if photo is not None and photo.filename:
        photo_bytes = await photo.read()
        photo_name = photo.filename
    if voice is not None and voice.filename:
        voice_bytes = await voice.read()
        voice_name = voice.filename
    msg = await send_manager_message(
        session,
        ctx.tenant,
        client_profile_id,
        staff_member_id=ctx.staff.id,  # type: ignore[union-attr]
        text=text,
        photo_bytes=photo_bytes,
        photo_name=photo_name,
        voice_bytes=voice_bytes,
        voice_name=voice_name,
    )
    return {"message": serialize_message(msg)}


@media_router.get("/media/chat/{tenant_public_id}/{message_id}")
async def chat_media_file(
    tenant_public_id: str,
    message_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    if ctx.tenant.public_id != tenant_public_id:
        raise HTTPException(status_code=404, detail="not found")
    msg = await session.get(ClientChatMessage, message_id)
    if msg is None or msg.tenant_id != ctx.tenant.id or not msg.telegram_file_id:
        raise HTTPException(status_code=404, detail="not found")

    cache_dir = media_root() / "chat"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if msg.kind == "photo" else ".ogg"
    key = msg.telegram_file_unique_id or msg.telegram_file_id or str(msg.id)
    cached = cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}{ext}"
    if not cached.exists():
        if not ctx.tenant.bot_token_encrypted:
            raise HTTPException(status_code=404, detail="not found")
        try:
            bot = get_bot_for_tenant(ctx.tenant)
            await bot.download(msg.telegram_file_id, destination=cached)
        except Exception:
            logger.warning("chat media download failed message=%s", message_id, exc_info=True)
            cached.unlink(missing_ok=True)
            raise HTTPException(status_code=404, detail="not found") from None

    media_type = "image/jpeg" if msg.kind == "photo" else "audio/ogg"
    return FileResponse(cached, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})