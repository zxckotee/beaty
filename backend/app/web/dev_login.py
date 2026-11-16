"""Resolve Telegram user id from test login identifier (numeric id or @username)."""

from __future__ import annotations

import re

from app.bot.registry import get_bot_for_tenant
from app.domain.exceptions import ValidationError
from app.domain.models import Tenant

_USER_ID_RE = re.compile(r"^-?\d+$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,32}$")


async def resolve_telegram_user_id(tenant: Tenant, identifier: str) -> tuple[int, str | None]:
    raw = identifier.strip()
    if not raw:
        raise ValidationError("укажите Telegram user id или @username")
    if raw.startswith("@"):
        raw = raw[1:]
    if _USER_ID_RE.match(raw):
        return int(raw), None
    if not _USERNAME_RE.match(raw):
        raise ValidationError("некорректный формат: числовой id или @username (латиница, цифры, _)")
    try:
        bot = get_bot_for_tenant(tenant)
    except ValueError as exc:
        raise ValidationError(
            "у салона нет токена бота в базе — используйте числовой telegram user id (узнать в @userinfobot)"
        ) from exc
    try:
        chat = await bot.get_chat(f"@{raw}")
    except Exception as exc:
        raise ValidationError(
            "не удалось найти пользователя по @username (нужен публичный username и хотя бы один диалог с ботом салона)"
        ) from exc
    if getattr(chat, "id", None) is None:
        raise ValidationError("Telegram не вернул id пользователя")
    parts = [getattr(chat, "first_name", None), getattr(chat, "last_name", None)]
    display = " ".join(p for p in parts if p).strip() or None
    return int(chat.id), display