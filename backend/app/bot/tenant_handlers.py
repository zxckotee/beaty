from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.settings import get_settings

tenant_router = Router(name="tenant")


@tenant_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    settings = get_settings()
    kb = InlineKeyboardBuilder()
    kb.button(text="Открыть запись", web_app=WebAppInfo(url=settings.miniapp_public_url))
    await message.answer(
        "Добро пожаловать! Запишитесь через мини-приложение или используйте кнопки в уведомлениях.",
        reply_markup=kb.as_markup(),
    )


@tenant_router.callback_query(F.data == "confirm_visit")
async def confirm_visit(callback: CallbackQuery) -> None:
    await callback.answer("Подтверждено")
    if callback.message:
        await callback.message.edit_text("Спасибо! Ждём вас на приёме.")
