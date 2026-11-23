from __future__ import annotations

import time
from typing import Any

from aiogram.types import CallbackQuery, Chat, Message, Update, User


def _max_user(raw: dict[str, Any]) -> User:
    uid = int(raw.get("user_id") or raw.get("id") or 0)
    name = (raw.get("name") or raw.get("first_name") or "") or "User"
    return User(
        id=uid,
        is_bot=False,
        first_name=name,
        username=raw.get("username"),
    )


def _chat_id(update: dict[str, Any], user: User) -> int:
    if update.get("chat_id") is not None:
        return int(update["chat_id"])
    if update.get("message", {}).get("recipient", {}).get("chat_id") is not None:
        return int(update["message"]["recipient"]["chat_id"])
    return user.id


def max_update_to_aiogram(data: dict[str, Any]) -> Update | None:
    update_type = data.get("update_type") or ""
    ts = int(data.get("timestamp") or time.time() * 1000)
    update_id = ts

    if update_type == "bot_started":
        user = _max_user(data.get("user") or {})
        payload = (data.get("payload") or "").strip()
        text = f"/start {payload}".strip() if payload else "/start"
        chat_id = _chat_id(data, user)
        message = Message(
            message_id=update_id,
            date=ts // 1000,
            chat=Chat(id=chat_id, type="private"),
            from_user=user,
            text=text,
        )
        return Update(update_id=update_id, message=message)

    if update_type == "message_created":
        raw_msg = data.get("message") or {}
        body = raw_msg.get("body") or {}
        user = _max_user(raw_msg.get("sender") or data.get("user") or {})
        text = body.get("text") or ""
        chat_id = _chat_id({"message": raw_msg, **data}, user)
        message = Message(
            message_id=int(raw_msg.get("message_id") or raw_msg.get("id") or update_id),
            date=int(raw_msg.get("created_at") or ts) // 1000 if raw_msg.get("created_at") else ts // 1000,
            chat=Chat(id=chat_id, type="private"),
            from_user=user,
            text=text,
        )
        return Update(update_id=update_id, message=message)

    if update_type == "message_callback":
        cb = data.get("callback") or {}
        user = _max_user(cb.get("user") or data.get("user") or {})
        payload = cb.get("payload") or ""
        cb_id = str(cb.get("callback_id") or cb.get("id") or update_id)
        raw_msg = data.get("message")
        message: Message | None = None
        if raw_msg:
            body = raw_msg.get("body") or {}
            chat_id = _chat_id(data, user)
            message = Message(
                message_id=int(raw_msg.get("message_id") or raw_msg.get("id") or update_id),
                date=ts // 1000,
                chat=Chat(id=chat_id, type="private"),
                from_user=user,
                text=body.get("text") or "",
            )
        chat_id = _chat_id(data, user)
        callback = CallbackQuery(
            id=cb_id,
            from_user=user,
            chat_instance=str(chat_id),
            data=str(payload),
            message=message,
        )
        return Update(update_id=update_id, callback_query=callback)

    return None