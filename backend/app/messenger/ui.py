from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def reply_markup_to_max_attachments(reply_markup: Any) -> list[dict[str, Any]] | None:
    if reply_markup is None:
        return None
    if isinstance(reply_markup, InlineKeyboardMarkup):
        rows: list[list[dict[str, Any]]] = []
        for row in reply_markup.inline_keyboard:
            btns: list[dict[str, Any]] = []
            for btn in row:
                if btn.url:
                    btns.append({"type": "link", "text": btn.text, "url": btn.url})
                elif btn.web_app:
                    btns.append({"type": "link", "text": btn.text, "url": btn.web_app.url})
                else:
                    btns.append({"type": "callback", "text": btn.text, "payload": btn.callback_data or ""})
            if btns:
                rows.append(btns)
        if not rows:
            return None
        return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]

    if isinstance(reply_markup, ReplyKeyboardMarkup):
        rows = []
        for row in reply_markup.keyboard:
            btns = []
            for btn in row:
                label = btn.text if isinstance(btn, KeyboardButton) else str(btn)
                btns.append({"type": "callback", "text": label, "payload": f"reply:{label}"})
            rows.append(btns)
        return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]
    return None