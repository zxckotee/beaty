from __future__ import annotations

from typing import Any
from uuid import UUID

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import BufferedInputFile
from sqlalchemy import desc, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.outbound_log_context import OutboundLogKind, outbound_log_context
from app.bot.registry import get_bot_for_tenant
from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.models import ClientChatMessage, ClientProfile, Tenant, UserAccount
from app.domain.services.client_chat_log import MAX_BODY, record_outbound

MAX_LIST = 50


async def list_telegram_clients(
    session: AsyncSession,
    tenant: Tenant,
    *,
    query: str = "",
    limit: int = 30,
) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), MAX_LIST)
    q = (
        select(ClientProfile)
        .where(
            ClientProfile.tenant_id == tenant.id,
            ClientProfile.user_account_id.is_not(None),
        )
        .order_by(ClientProfile.name)
        .limit(limit)
    )
    if query.strip():
        pattern = f"%{query.strip()}%"
        q = q.where(or_(ClientProfile.name.ilike(pattern), ClientProfile.phone.ilike(pattern)))

    profiles = (await session.scalars(q)).all()
    if not profiles:
        return []

    items: list[dict[str, Any]] = []
    for p in profiles:
        last = await session.scalar(
            select(ClientChatMessage)
            .where(ClientChatMessage.client_profile_id == p.id)
            .order_by(desc(ClientChatMessage.created_at))
            .limit(1)
        )
        preview = _preview(last)
        items.append(
            {
                "id": str(p.id),
                "name": p.name,
                "phone": p.phone,
                "telegram_unreachable": p.telegram_unreachable,
                "can_write": not p.telegram_unreachable,
                "last_message_at": last.created_at.isoformat() if last else None,
                "last_preview": preview,
            }
        )
    items.sort(key=lambda x: x["last_message_at"] or "", reverse=True)
    return items


def _preview(msg: ClientChatMessage | None) -> str | None:
    if msg is None:
        return None
    if msg.kind == "text" and msg.body:
        return msg.body[:120]
    if msg.kind == "photo":
        return msg.body or "Фото"
    if msg.kind == "voice":
        return "Голосовое сообщение"
    return msg.body


async def list_messages(
    session: AsyncSession,
    tenant: Tenant,
    client_profile_id: UUID,
    *,
    before: UUID | None = None,
    limit: int = 40,
) -> list[ClientChatMessage]:
    limit = min(max(limit, 1), 100)
    profile = await session.get(ClientProfile, client_profile_id)
    if profile is None or profile.tenant_id != tenant.id:
        raise NotFoundError("client not found")

    q = (
        select(ClientChatMessage)
        .where(
            ClientChatMessage.tenant_id == tenant.id,
            ClientChatMessage.client_profile_id == client_profile_id,
        )
        .order_by(desc(ClientChatMessage.created_at), desc(ClientChatMessage.id))
        .limit(limit)
    )
    if before:
        pivot = await session.get(ClientChatMessage, before)
        if pivot and pivot.client_profile_id == client_profile_id:
            q = q.where(
                (ClientChatMessage.created_at < pivot.created_at)
                | (
                    (ClientChatMessage.created_at == pivot.created_at)
                    & (ClientChatMessage.id < pivot.id)
                )
            )

    rows = (await session.scalars(q)).all()
    return list(reversed(rows))


def serialize_message(msg: ClientChatMessage) -> dict[str, Any]:
    return {
        "id": str(msg.id),
        "direction": msg.direction,
        "author": msg.author,
        "kind": msg.kind,
        "body": msg.body,
        "has_media": bool(msg.telegram_file_id),
        "created_at": msg.created_at.isoformat(),
        "meta": msg.meta or {},
    }


async def send_manager_message(
    session: AsyncSession,
    tenant: Tenant,
    client_profile_id: UUID,
    *,
    staff_member_id: UUID,
    text: str | None = None,
    photo_bytes: bytes | None = None,
    photo_name: str | None = None,
    voice_bytes: bytes | None = None,
    voice_name: str | None = None,
) -> ClientChatMessage:
    profile = await session.get(ClientProfile, client_profile_id)
    if profile is None or profile.tenant_id != tenant.id:
        raise NotFoundError("client not found")
    if not profile.user_account_id:
        raise ValidationError("Клиент не привязан к Telegram")
    if profile.telegram_unreachable:
        raise ValidationError("Бот не может писать этому клиенту в Telegram")
    if not tenant.bot_token_encrypted:
        raise ValidationError("У салона не настроен бот")

    user = await session.get(UserAccount, profile.user_account_id)
    if user is None:
        raise ValidationError("Клиент не привязан к Telegram")

    has_photo = bool(photo_bytes)
    has_voice = bool(voice_bytes)
    has_text_only = bool(text and text.strip()) and not has_photo and not has_voice
    if sum((has_photo, has_voice, has_text_only)) != 1:
        raise ValidationError("Отправьте один тип: текст, фото или голос")

    bot = get_bot_for_tenant(tenant)
    chat_id = user.telegram_user_id
    try:
        with outbound_log_context(OutboundLogKind.MANAGER, staff_member_id=staff_member_id):
            if photo_bytes:
                inp = BufferedInputFile(photo_bytes, filename=photo_name or "photo.jpg")
                sent = await bot.send_photo(chat_id, inp, caption=(text or "")[:1024] or None)
                photo = sent.photo[-1] if sent.photo else None
                msg = await record_outbound(
                    session,
                    tenant_id=tenant.id,
                    client_profile_id=profile.id,
                    kind="photo",
                    author="manager",
                    body=(sent.caption or "")[:MAX_BODY] or None,
                    telegram_file_id=photo.file_id if photo else None,
                    telegram_file_unique_id=photo.file_unique_id if photo else None,
                    telegram_message_id=sent.message_id,
                    staff_member_id=staff_member_id,
                )
                await session.commit()
                return msg
            if voice_bytes:
                inp = BufferedInputFile(voice_bytes, filename=voice_name or "voice.ogg")
                sent = await bot.send_voice(chat_id, inp, caption=(text or "")[:1024] or None)
                voice = sent.voice
                msg = await record_outbound(
                    session,
                    tenant_id=tenant.id,
                    client_profile_id=profile.id,
                    kind="voice",
                    author="manager",
                    body=None,
                    telegram_file_id=voice.file_id if voice else None,
                    telegram_file_unique_id=voice.file_unique_id if voice else None,
                    telegram_message_id=sent.message_id,
                    staff_member_id=staff_member_id,
                    meta={"duration": voice.duration if voice else None},
                )
                await session.commit()
                return msg
            body = (text or "").strip()
            if not body:
                raise ValidationError("Пустое сообщение")
            sent = await bot.send_message(chat_id, body[:MAX_BODY])
            msg = await record_outbound(
                session,
                tenant_id=tenant.id,
                client_profile_id=profile.id,
                kind="text",
                author="manager",
                body=body[:MAX_BODY],
                telegram_file_id=None,
                telegram_file_unique_id=None,
                telegram_message_id=sent.message_id,
                staff_member_id=staff_member_id,
            )
            await session.commit()
            return msg
    except TelegramForbiddenError:
        await session.execute(
            update(ClientProfile).where(ClientProfile.id == profile.id).values(telegram_unreachable=True)
        )
        await session.commit()
        raise ValidationError("Клиент заблокировал бота или недоступен") from None