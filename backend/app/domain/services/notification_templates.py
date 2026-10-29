from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.domain.models import NotificationType


def build_notification_message(
    notification_type: str,
    payload: dict[str, Any],
) -> tuple[str, InlineKeyboardMarkup | None]:
    booking_id = payload.get("booking_id", "")
    if notification_type in (NotificationType.REMINDER_24H.value, NotificationType.REMINDER_2H.value):
        text = payload.get("text") or "Напоминание о записи. Подтвердите визит или перенесите."
        kb = InlineKeyboardBuilder()
        if booking_id:
            kb.button(text="Подтверждаю", callback_data=f"confirm_visit:{booking_id}")
            kb.button(text="Мои записи", callback_data=f"c:my:{booking_id}")
        kb.adjust(1)
        return text, kb.as_markup()
    if notification_type == NotificationType.BOOKING_CONFIRMED.value:
        return payload.get("text") or "Запись подтверждена.", None
    if notification_type == "revisit":
        kb = InlineKeyboardBuilder()
        kb.button(text="Записаться снова", callback_data="c:back:svc")
        return payload.get("text") or "Пора снова записаться!", kb.as_markup()
    if notification_type == "review_request":
        kb = InlineKeyboardBuilder()
        for n in range(1, 6):
            kb.button(text=str(n), callback_data=f"c:rv:{booking_id}:{n}")
        kb.adjust(5)
        return payload.get("text") or "Оцените визит:", kb.as_markup()
    if notification_type == "force_majeure_options":
        kb = InlineKeyboardBuilder()
        options = payload.get("options") or []
        for idx, opt in enumerate(options[:4]):
            label = opt.get("label", f"Вариант {idx + 1}")[:40]
            kb.button(text=label, callback_data=f"fm:{booking_id}:{idx}")
        kb.adjust(1)
        return payload.get("text") or "Запись изменена. Выберите вариант:", kb.as_markup()
    return f"Уведомление: {notification_type}", None
