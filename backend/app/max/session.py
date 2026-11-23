from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods.base import TelegramMethod

from app.max.client import MaxClient
from app.messenger.ui import reply_markup_to_max_attachments


class MaxApiSession(BaseSession):
    """Aiogram session that sends Telegram Bot API calls to MAX HTTP API."""

    def __init__(self, max_client: MaxClient) -> None:
        super().__init__()
        self._max = max_client

    async def close(self) -> None:  # noqa: D401
        return None

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        name = method.__api_method__  # type: ignore[attr-defined]
        if name == "sendMessage":
            attachments = None
            reply_markup = getattr(method, "reply_markup", None)
            if reply_markup is not None:
                attachments = reply_markup_to_max_attachments(reply_markup)
            parse_mode = getattr(method, "parse_mode", None)
            fmt = "html" if parse_mode and str(parse_mode).lower() == "html" else None
            return await self._max.send_message(
                user_id=int(method.chat_id),  # type: ignore[attr-defined]
                text=str(method.text or ""),  # type: ignore[attr-defined]
                attachments=attachments,
                format=fmt,
            )
        if name == "editMessageText":
            # MAX supports message edit; minimal path — send new message fallback
            attachments = None
            reply_markup = getattr(method, "reply_markup", None)
            if reply_markup is not None:
                attachments = reply_markup_to_max_attachments(reply_markup)
            return await self._max.send_message(
                user_id=int(method.chat_id),  # type: ignore[attr-defined]
                text=str(method.text or ""),  # type: ignore[attr-defined]
                attachments=attachments,
            )
        if name == "answerCallbackQuery":
            cb_id = str(getattr(method, "callback_query_id", ""))  # type: ignore[attr-defined]
            if cb_id:
                await self._max.answer_callback(cb_id)
            return True
        if name == "deleteMessage":
            return True
        if name in {"setChatMenuButton", "setMyCommands", "setMyName", "setMyDescription"}:
            return True
        # Photo paths — send text placeholder with URL if provided
        if name == "sendPhoto":
            caption = str(getattr(method, "caption", "") or "")  # type: ignore[attr-defined]
            return await self._max.send_message(
                user_id=int(method.chat_id),  # type: ignore[attr-defined]
                text=caption or "📷",
            )
        return await self._send_fallback(name, method)

    async def _send_fallback(self, name: str, method: TelegramMethod[Any]) -> bool:
        payload = method.model_dump(exclude_none=True) if hasattr(method, "model_dump") else {}
        if payload:
            text = json.dumps(payload, ensure_ascii=False)[:3500]
            chat_id = payload.get("chat_id")
            if chat_id is not None:
                await self._max.send_message(user_id=int(chat_id), text=f"({name}) {text[:500]}")
        return True

    async def stream_content(self, url: str, timeout: int) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError("MAX session does not stream telegram file URLs")


def create_max_bot(token: str) -> Bot:
    client = MaxClient(token)
    return Bot(token=token, session=MaxApiSession(client))