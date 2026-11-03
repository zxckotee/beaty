"""Active UI role: which hat the user wears in the tenant bot right now."""

from __future__ import annotations

from typing import Literal

from app.domain.models import StaffMember

_MANAGER = frozenset({"owner", "manager"})
_STAFF = frozenset({"owner", "manager", "specialist"})

UiRole = Literal["manager", "specialist", "client"]

UI_ROLE_MANAGER: UiRole = "manager"
UI_ROLE_SPECIALIST: UiRole = "specialist"
UI_ROLE_CLIENT: UiRole = "client"

UI_ROLE_LABELS: dict[UiRole, str] = {
    UI_ROLE_MANAGER: "Управляющий",
    UI_ROLE_SPECIALIST: "Мастер",
    UI_ROLE_CLIENT: "Клиент",
}


def available_ui_roles(*, granted_roles: set[str], has_staff_profile: bool) -> list[UiRole]:
    """Roles this Telegram user may switch to in this tenant."""
    if not has_staff_profile:
        return [UI_ROLE_CLIENT]
    options: list[UiRole] = []
    if granted_roles.intersection(_MANAGER):
        options.append(UI_ROLE_MANAGER)
    if granted_roles.intersection(_STAFF):
        options.append(UI_ROLE_SPECIALIST)
    options.append(UI_ROLE_CLIENT)
    # preserve order, dedupe
    seen: set[UiRole] = set()
    ordered: list[UiRole] = []
    for role in options:
        if role not in seen:
            seen.add(role)
            ordered.append(role)
    return ordered


def default_ui_role(available: list[UiRole]) -> UiRole:
    if UI_ROLE_MANAGER in available:
        return UI_ROLE_MANAGER
    if UI_ROLE_SPECIALIST in available:
        return UI_ROLE_SPECIALIST
    return UI_ROLE_CLIENT


def resolve_active_ui_role(stored: str | None, available: list[UiRole]) -> UiRole:
    if stored in available:
        return stored  # type: ignore[return-value]
    return default_ui_role(available)


def read_stored_ui_role(staff_member: StaffMember | None) -> str | None:
    if staff_member is None:
        return None
    prefs = staff_member.ui_prefs or {}
    raw = prefs.get("active_ui_role")
    return raw if isinstance(raw, str) else None


def write_stored_ui_role(staff_member: StaffMember, role: UiRole) -> None:
    prefs = dict(staff_member.ui_prefs or {})
    prefs["active_ui_role"] = role
    staff_member.ui_prefs = prefs
