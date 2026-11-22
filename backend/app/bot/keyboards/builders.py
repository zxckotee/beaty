from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.bot.active_role import UI_ROLE_CLIENT, UI_ROLE_MANAGER, UI_ROLE_SPECIALIST, UiRole
from app.bot.filters.roles import is_manager, is_staff
from app.bot.miniapp import bot_chat_write_enabled


def tenant_reply_keyboard(
    *,
    active_ui_role: UiRole,
    can_switch_ui_role: bool,
    granted_roles: set[str] | None = None,
    has_staff_profile: bool = False,
) -> ReplyKeyboardMarkup:
    if bot_chat_write_enabled():
        return main_menu_reply(
            active_ui_role=active_ui_role,
            can_switch_ui_role=can_switch_ui_role,
        )
    return view_menu_reply(
        granted_roles=granted_roles or {"client"},
        has_staff_profile=has_staff_profile,
    )


def view_menu_reply(
    *,
    granted_roles: set[str],
    has_staff_profile: bool = False,
) -> ReplyKeyboardMarkup:
    """Persistent reply buttons for read-only chat (no slash-command hints)."""
    builder = ReplyKeyboardBuilder()
    if is_manager(granted_roles):
        builder.row(KeyboardButton(text="Сегодня"), KeyboardButton(text="Мой день"))
        builder.row(KeyboardButton(text="Команда"), KeyboardButton(text="Услуги"))
        builder.row(KeyboardButton(text="Мои записи"))
    elif is_staff(granted_roles) or has_staff_profile:
        builder.row(KeyboardButton(text="Мой день"), KeyboardButton(text="Мои записи"))
    else:
        builder.row(KeyboardButton(text="Мои записи"))
    builder.row(KeyboardButton(text="Помощь"))
    return builder.as_markup(resize_keyboard=True)


def main_menu_reply(
    *,
    active_ui_role: UiRole,
    can_switch_ui_role: bool,
) -> ReplyKeyboardMarkup:
    """Reply menu for the role the user chose to act as right now (bot mode)."""
    builder = ReplyKeyboardBuilder()
    if active_ui_role == UI_ROLE_MANAGER:
        builder.row(KeyboardButton(text="Сегодня"), KeyboardButton(text="Команда"))
        builder.row(KeyboardButton(text="Услуги"), KeyboardButton(text="Клиенты"))
        builder.row(KeyboardButton(text="Ещё"), KeyboardButton(text="Записать клиента"))
    elif active_ui_role == UI_ROLE_SPECIALIST:
        builder.row(KeyboardButton(text="Мой день"))
    elif active_ui_role == UI_ROLE_CLIENT:
        builder.row(KeyboardButton(text="Запись"), KeyboardButton(text="Мои записи"))
        builder.row(KeyboardButton(text="Повторить прошлую"))
    if can_switch_ui_role:
        builder.row(KeyboardButton(text="Сменить режим"))
    builder.row(KeyboardButton(text="Помощь"))
    return builder.as_markup(resize_keyboard=True)


def role_switch_inline(available: list[UiRole], *, active: UiRole) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for role in available:
        label = {
            UI_ROLE_MANAGER: "Управляющий",
            UI_ROLE_SPECIALIST: "Мастер",
            UI_ROLE_CLIENT: "Клиент",
        }[role]
        prefix = "✓ " if role == active else ""
        kb.button(text=f"{prefix}{label}".strip(), callback_data=f"ui:role:{role}")
    kb.adjust(1)
    return kb.as_markup()


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Поделиться телефоном", request_contact=True))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def paginate_row(page: int, total_pages: int, prefix: str) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀", callback_data=f"{prefix}:p:{page - 1}"))
    if page + 1 < total_pages:
        row.append(InlineKeyboardButton(text="▶", callback_data=f"{prefix}:p:{page + 1}"))
    return row


def inline_back(cancel_data: str = "c:cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_data)]]
    )


def reply_button_texts(markup: ReplyKeyboardMarkup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]
