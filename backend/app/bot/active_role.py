"""Re-export: the active-role logic lives in the shared domain module."""

from app.domain.active_role import *  # noqa: F403
from app.domain.active_role import (  # noqa: F401
    UI_ROLE_CLIENT,
    UI_ROLE_LABELS,
    UI_ROLE_MANAGER,
    UI_ROLE_SPECIALIST,
    UiRole,
    available_ui_roles,
    default_ui_role,
    read_stored_ui_role,
    resolve_active_ui_role,
    write_stored_ui_role,
)
