from __future__ import annotations

import logging
from typing import Any, TypeVar

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import SendMessage, SendPhoto, SendVoice
from aiogram.methods.base import TelegramMethod
from aiogram.types import Message
from sqlalchemy import select

from app.bot.outbound_log_context import OutboundLogKind, current_kind
from app.core.db import SessionLocal
from app.domain.models import Tenant
from app.domain.services.client_chat_log import maybe_log_outbound_api_response, resolve_client_by_chat_id

logger = logging.getLogger(__name__)

TelegramType = TypeVar("TelegramType")

_LOG_METHODS = (SendMessage, SendPhoto, SendVoice)


class LoggingAiohttpSession(AiohttpSession):
    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        result = await super().make_request(bot, method, timeout=timeout)
        if isinstance(method, _LOG_METHODS) and current_kind() == OutboundLogKind.INTERACTIVE:
            try:
                await self._log_sent(bot, method, result)
            except Exception:
                logger.exception("client chat outbound log failed")
        return result

    async def _log_sent(self, bot: Bot, method: TelegramMethod[Any], result: TelegramType) -> None:
        if not isinstance(result, Message):
            return
        tenant_public_id = getattr(bot, "tenant_public_id", None)
        if not tenant_public_id:
            return

        chat_id = int(method.chat_id)  # type: ignore[attr-defined]
        kind, body, file_id, file_unique_id, meta = _parse_outbound(method, result)
        if kind is None:
            return

        async with SessionLocal() as session:
            tenant = await session.scalar(select(Tenant).where(Tenant.public_id == tenant_public_id))
            if tenant is None:
                return
            profile = await resolve_client_by_chat_id(session, tenant_id=tenant.id, chat_id=chat_id)
            if profile is None:
                return
            await maybe_log_outbound_api_response(
                session,
                tenant_id=tenant.id,
                client_profile_id=profile.id,
                kind=kind,
                body=body,
                telegram_file_id=file_id,
                telegram_file_unique_id=file_unique_id,
                telegram_message_id=result.message_id,
                meta=meta,
            )


def _parse_outbound(
    method: TelegramMethod[Any],
    message: Message,
) -> tuple[str | None, str | None, str | None, str | None, dict[str, Any]]:
    if isinstance(method, SendMessage):
        text = (method.text or "").strip()
        if not text:
            return None, None, None, None, {}
        return "text", text[:4096], None, None, {}

    if isinstance(method, SendPhoto):
        caption = (method.caption or message.caption or "")[:4096] or None
        photo = message.photo[-1] if message.photo else None
        if photo is None:
            return None, None, None, None, {}
        return "photo", caption, photo.file_id, photo.file_unique_id, {}

    if isinstance(method, SendVoice):
        voice = message.voice
        if voice is None:
            return None, None, None, None, {}
        return (
            "voice",
            None,
            voice.file_id,
            voice.file_unique_id,
            {"duration": voice.duration},
        )
    return None, None, None, None, {}