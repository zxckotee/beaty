from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_menu_reply(*, is_manager: bool, is_specialist: bool, is_solo: bool = False) -> ReplyKeyboardMarkup:
    """Role-based reply menu. is_solo = owner-master with manager + specialist roles."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Запись"), KeyboardButton(text="Мои записи"))
    builder.row(KeyboardButton(text="Повторить прошлую"))
    if is_solo:
        builder.row(KeyboardButton(text="Сегодня"), KeyboardButton(text="Мой день"))
    else:
        if is_specialist:
            builder.row(KeyboardButton(text="Мой день"))
        if is_manager:
            builder.row(KeyboardButton(text="Сегодня"), KeyboardButton(text="Команда"))
            builder.row(KeyboardButton(text="Услуги"), KeyboardButton(text="Клиенты"))
            builder.row(KeyboardButton(text="Ещё"))
    builder.row(KeyboardButton(text="Помощь"))
    return builder.as_markup(resize_keyboard=True)


def menu_flags(roles: set[str], *, has_staff_profile: bool) -> tuple[bool, bool, bool]:
    from app.bot.filters.roles import is_manager, is_staff

    mgr = is_manager(roles)
    spec = has_staff_profile and is_staff(roles)
    solo = mgr and spec and not roles.intersection({"reception"})
    return mgr, spec, solo


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
