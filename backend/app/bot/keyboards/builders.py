from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_menu_reply(*, is_staff: bool, is_manager: bool) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Запись"), KeyboardButton(text="Мои записи"))
    if is_staff:
        builder.row(KeyboardButton(text="Мой день"))
    if is_manager:
        builder.row(KeyboardButton(text="Сегодня"))
    builder.row(KeyboardButton(text="Помощь"))
    return builder.as_markup(resize_keyboard=True)


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
