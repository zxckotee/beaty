from app.bot.active_role import (
    UI_ROLE_CLIENT,
    UI_ROLE_MANAGER,
    UI_ROLE_SPECIALIST,
    available_ui_roles,
    default_ui_role,
    resolve_active_ui_role,
)


def test_owner_gets_three_modes() -> None:
    roles = {"owner", "manager", "specialist", "client"}
    assert available_ui_roles(granted_roles=roles, has_staff_profile=True) == [
        UI_ROLE_MANAGER,
        UI_ROLE_SPECIALIST,
        UI_ROLE_CLIENT,
    ]


def test_pure_client_only_client_mode() -> None:
    assert available_ui_roles(granted_roles={"client"}, has_staff_profile=False) == [UI_ROLE_CLIENT]


def test_default_is_manager_when_possible() -> None:
    avail = [UI_ROLE_MANAGER, UI_ROLE_SPECIALIST, UI_ROLE_CLIENT]
    assert default_ui_role(avail) == UI_ROLE_MANAGER


def test_resolve_falls_back_when_stored_invalid() -> None:
    avail = [UI_ROLE_MANAGER, UI_ROLE_SPECIALIST, UI_ROLE_CLIENT]
    assert resolve_active_ui_role("client", avail) == UI_ROLE_CLIENT
    assert resolve_active_ui_role("unknown", avail) == UI_ROLE_MANAGER
