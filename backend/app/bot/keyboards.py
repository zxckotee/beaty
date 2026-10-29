from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

BTN_BOOK = "Записаться"
BTN_MY = "Мои записи"
BTN_REPEAT = "Повторить прошлую"
BTN_PROFILE = "Профиль"


def client_main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=BTN_BOOK)
    kb.button(text=BTN_MY)
    kb.button(text=BTN_REPEAT)
    kb.button(text=BTN_PROFILE)
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


def request_contact_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Отправить телефон", request_contact=True))
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def confirm_visit_keyboard(booking_id: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="Подтверждаю", callback_data=f"confirm_visit:{booking_id}")
    return kb
