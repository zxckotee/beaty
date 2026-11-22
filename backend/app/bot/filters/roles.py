"""Shared role checks for tenant bot handlers."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.bot.miniapp import bot_chat_write_enabled

MANAGER_ROLES = frozenset({"owner", "manager"})
STAFF_ROLES = frozenset({"owner", "manager", "specialist"})


def is_manager(roles: set[str]) -> bool:
    return bool(roles.intersection(MANAGER_ROLES))


def is_staff(roles: set[str]) -> bool:
    return bool(roles.intersection(STAFF_ROLES))


def is_owner(roles: set[str]) -> bool:
    return "owner" in roles


def _ignore_ui_role() -> bool:
    """Read-only chat has no role menu; view commands follow granted roles."""
    return not bot_chat_write_enabled()


class HasManagerRole(BaseFilter):
    async def __call__(self, _event: TelegramObject, roles: set[str], active_ui_role: str) -> bool:
        if not is_manager(roles):
            return False
        return _ignore_ui_role() or active_ui_role == "manager"


class HasStaffRole(BaseFilter):
    async def __call__(self, _event: TelegramObject, roles: set[str], active_ui_role: str) -> bool:
        if not is_staff(roles):
            return False
        return _ignore_ui_role() or active_ui_role == "specialist"


class HasActiveClientRole(BaseFilter):
    async def __call__(self, _event: TelegramObject, active_ui_role: str) -> bool:
        return _ignore_ui_role() or active_ui_role == "client"
