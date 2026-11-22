from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from app.domain.models import ClientProfile, Tenant
from app.domain.services.client_chat_log import inbound_from_telegram_message, record_inbound


class ChatCaptureMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = event if isinstance(event, Update) else data.get("event_update")
        if isinstance(update, Update) and update.message:
            await self._capture_inbound(update.message, data)
        return await handler(event, data)

    async def _capture_inbound(self, message: Message, data: dict[str, Any]) -> None:
        tenant: Tenant | None = data.get("tenant")
        client_profile: ClientProfile | None = data.get("client_profile")
        db_session = data.get("db_session")
        if tenant is None or client_profile is None or db_session is None:
            return
        if message.from_user is None or message.chat.type != "private":
            return
        if message.from_user.id != message.chat.id:
            return

        capture = inbound_from_telegram_message(message)
        if capture is None:
            return
        await record_inbound(
            db_session,
            tenant_id=tenant.id,
            client_profile_id=client_profile.id,
            capture=capture,
        )
        await db_session.commit()