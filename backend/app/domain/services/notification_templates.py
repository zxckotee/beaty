from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.domain.models import NotificationType


def _miniapp_markup(miniapp_url: str | None, *, text: str = "Открыть") -> InlineKeyboardMarkup | None:
    if not miniapp_url:
        return None
    kb = InlineKeyboardBuilder()
    kb.button(text=text, web_app=WebAppInfo(url=miniapp_url))
    return kb.as_markup()


def build_notification_message(
    notification_type: str,
    payload: dict[str, Any],
    *,
    chat_writes: bool = True,
    miniapp_url: str | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    booking_id = payload.get("booking_id", "")
    if notification_type in (NotificationType.REMINDER_24H.value, NotificationType.REMINDER_2H.value):
        text = payload.get("text") or "Напоминание о записи. Подтвердите визит или перенесите."
        kb = InlineKeyboardBuilder()
        if chat_writes:
            if booking_id:
                kb.button(text="Подтверждаю", callback_data=f"confirm_visit:{booking_id}")
                kb.button(text="Мои записи", callback_data=f"c:my:{booking_id}")
        else:
            if booking_id:
                kb.button(text="Мои записи", callback_data=f"c:my:{booking_id}")
            if miniapp_url:
                kb.button(text="Открыть", web_app=WebAppInfo(url=miniapp_url))
        kb.adjust(1)
        return text, kb.as_markup()
    if notification_type == NotificationType.BOOKING_CONFIRMED.value:
        return payload.get("text") or "Запись подтверждена.", None
    if notification_type == "revisit":
        if not chat_writes:
            return payload.get("text") or "Пора снова записаться!", _miniapp_markup(
                miniapp_url, text="Записаться"
            )
        kb = InlineKeyboardBuilder()
        kb.button(text="Записаться снова", callback_data="c:back:svc")
        return payload.get("text") or "Пора снова записаться!", kb.as_markup()
    if notification_type == "review_request":
        if not chat_writes:
            return payload.get("text") or "Оцените визит:", _miniapp_markup(miniapp_url, text="Оценить")
        kb = InlineKeyboardBuilder()
        for n in range(1, 6):
            kb.button(text=str(n), callback_data=f"c:rv:{booking_id}:{n}")
        kb.adjust(5)
        return payload.get("text") or "Оцените визит:", kb.as_markup()
    if notification_type == "force_majeure_options":
        if not chat_writes:
            return payload.get("text") or "Запись изменена. Выберите вариант:", _miniapp_markup(
                miniapp_url, text="Выбрать в приложении"
            )
        kb = InlineKeyboardBuilder()
        options = payload.get("options") or []
        for idx, opt in enumerate(options[:4]):
            label = opt.get("label", f"Вариант {idx + 1}")[:40]
            kb.button(text=label, callback_data=f"fm:{booking_id}:{idx}")
        kb.adjust(1)
        return payload.get("text") or "Запись изменена. Выберите вариант:", kb.as_markup()
    return f"Уведомление: {notification_type}", None
