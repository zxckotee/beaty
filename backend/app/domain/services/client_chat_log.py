from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from aiogram.types import Message as TgMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.outbound_log_context import OutboundLogKind, current_kind
from app.domain.models import ClientChatMessage, ClientProfile, UserAccount

MAX_BODY = 4096


@dataclass(frozen=True)
class InboundCapture:
    kind: str
    body: str | None
    telegram_file_id: str | None
    telegram_file_unique_id: str | None
    telegram_message_id: int | None
    meta: dict[str, Any]


def inbound_from_telegram_message(message: TgMessage) -> InboundCapture | None:
    if message.voice:
        return InboundCapture(
            kind="voice",
            body=None,
            telegram_file_id=message.voice.file_id,
            telegram_file_unique_id=message.voice.file_unique_id,
            telegram_message_id=message.message_id,
            meta={"duration": message.voice.duration},
        )
    if message.photo:
        photo = message.photo[-1]
        return InboundCapture(
            kind="photo",
            body=(message.caption or "")[:MAX_BODY] or None,
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            telegram_message_id=message.message_id,
            meta={},
        )
    text = (message.text or message.caption or "").strip()
    if not text:
        return None
    if text.startswith("/"):
        return None
    return InboundCapture(
        kind="text",
        body=text[:MAX_BODY],
        telegram_file_id=None,
        telegram_file_unique_id=None,
        telegram_message_id=message.message_id,
        meta={},
    )


async def record_inbound(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    client_profile_id: UUID,
    capture: InboundCapture,
) -> ClientChatMessage:
    row = ClientChatMessage(
        tenant_id=tenant_id,
        client_profile_id=client_profile_id,
        direction="inbound",
        author="client",
        kind=capture.kind,
        body=capture.body,
        telegram_file_id=capture.telegram_file_id,
        telegram_file_unique_id=capture.telegram_file_unique_id,
        telegram_message_id=capture.telegram_message_id,
        meta=capture.meta,
    )
    session.add(row)
    await session.flush()
    return row


async def record_outbound(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    client_profile_id: UUID,
    kind: str,
    author: str,
    body: str | None,
    telegram_file_id: str | None,
    telegram_file_unique_id: str | None,
    telegram_message_id: int | None,
    staff_member_id: UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> ClientChatMessage:
    row = ClientChatMessage(
        tenant_id=tenant_id,
        client_profile_id=client_profile_id,
        direction="outbound",
        author=author,
        kind=kind,
        body=body[:MAX_BODY] if body else None,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        telegram_message_id=telegram_message_id,
        staff_member_id=staff_member_id,
        meta=meta or {},
    )
    session.add(row)
    await session.flush()
    return row


async def resolve_client_by_chat_id(
    session: AsyncSession, *, tenant_id: UUID, chat_id: int
) -> ClientProfile | None:
    user = await session.scalar(select(UserAccount).where(UserAccount.telegram_user_id == chat_id))
    if user is None:
        return None
    return await session.scalar(
        select(ClientProfile).where(
            ClientProfile.tenant_id == tenant_id,
            ClientProfile.user_account_id == user.id,
        )
    )


async def maybe_log_outbound_api_response(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    client_profile_id: UUID,
    kind: str,
    body: str | None,
    telegram_file_id: str | None,
    telegram_file_unique_id: str | None,
    telegram_message_id: int | None,
    meta: dict[str, Any] | None = None,
) -> None:
    log_kind = current_kind()
    if log_kind in (OutboundLogKind.NOTIFICATION, OutboundLogKind.MANAGER):
        return
    await record_outbound(
        session,
        tenant_id=tenant_id,
        client_profile_id=client_profile_id,
        kind=kind,
        author="bot",
        body=body,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        telegram_message_id=telegram_message_id,
        meta=meta,
    )
    await session.commit()