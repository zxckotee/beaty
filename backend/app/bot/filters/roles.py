"""Shared role checks for tenant bot handlers."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

MANAGER_ROLES = frozenset({"owner", "manager"})
STAFF_ROLES = frozenset({"owner", "manager", "specialist"})


def is_manager(roles: set[str]) -> bool:
    return bool(roles.intersection(MANAGER_ROLES))


def is_staff(roles: set[str]) -> bool:
    return bool(roles.intersection(STAFF_ROLES))


def is_owner(roles: set[str]) -> bool:
    return "owner" in roles


class HasManagerRole(BaseFilter):
    async def __call__(self, _event: TelegramObject, roles: set[str]) -> bool:
        return is_manager(roles)


class HasStaffRole(BaseFilter):
    async def __call__(self, _event: TelegramObject, roles: set[str]) -> bool:
        return is_staff(roles)
