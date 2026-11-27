"""Send help text with optional docs URL button."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from app.content.user_guide import docs_inline_button_label


def docs_url_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=docs_inline_button_label(), url=url)]]
    )


def open_bot_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть", url=url)]]
    )


async def send_help_parts(
    message: Message,
    text: str,
    *,
    part2: str | None = None,
    docs_url: str | None = None,
    reply_markup: ReplyKeyboardMarkup | None = None,
) -> None:
    kb = docs_url_keyboard(docs_url) if docs_url else None
    if part2:
        await message.answer(text, reply_markup=reply_markup)
        await message.answer(part2, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb or reply_markup)