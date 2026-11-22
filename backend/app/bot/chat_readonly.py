"""When Mini App is the product UI, the chat bot only shows information.

Booking, cancellations, reviews, force-majeure choices and salon management
live in the Mini App. Leftover reply-keyboard taps and old inline buttons are
redirected there instead of writing data.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.filters.chat_write import ChatWritesDisabled
from app.bot.miniapp import miniapp_open_hint, miniapp_url_for_tenant
from app.domain.models import Tenant

readonly_router = Router(name="chat_readonly")
readonly_router.message.filter(ChatWritesDisabled())
readonly_router.callback_query.filter(ChatWritesDisabled())

WRITE_INTENT_TEXTS = frozenset(
    {
        "Запись",
        "Повторить прошлую",
        "Записать клиента",
        "Ещё",
    }
)

# Callback prefixes that create/update/cancel domain data from chat.
WRITE_CALLBACK_PREFIXES = (
    "confirm_visit:",
    "fm:",
    "c:wait:",
    "c:rv:",
    "c:crs:",
    "c:ok:",
    "c:slot:",
    "c:svc:",
    "c:mst:",
    "c:day:",
    "c:back:",
    "c:cn:",
    "c:rs:",
    "m:mb:",
    "m:bcn:",
    "m:svc:add",
    "m:svc:ep:",
    "m:svc:ed:",
    "m:svc:toggle:",
    "m:svc:tpl:",
    "m:team:add",
    "m:team:inv:",
    "m:team:mgr:",
    "m:more:book",
    "m:more:settings",
    "m:set:",
    "s:st:",
    "s:sick:",
)


def is_write_callback(data: str | None) -> bool:
    raw = data or ""
    return any(raw == prefix.rstrip(":") or raw.startswith(prefix) for prefix in WRITE_CALLBACK_PREFIXES)


def open_miniapp_markup(tenant: Tenant, *, text: str = "Открыть") -> InlineKeyboardMarkup | None:
    url = miniapp_url_for_tenant(tenant)
    if not url:
        return None
    kb = InlineKeyboardBuilder()
    kb.button(text=text, web_app=WebAppInfo(url=url))
    return kb.as_markup()


async def reply_use_miniapp(message: Message, tenant: Tenant, text: str | None = None) -> None:
    await message.answer(text or miniapp_open_hint(), reply_markup=open_miniapp_markup(tenant))


async def callback_use_miniapp(callback: CallbackQuery, tenant: Tenant) -> None:
    await callback.answer("Это действие доступно в мини-приложении", show_alert=True)
    if callback.message:
        await callback.message.answer(miniapp_open_hint(), reply_markup=open_miniapp_markup(tenant))


@readonly_router.message(Command("book"))
@readonly_router.message(Command("book_time"))
@readonly_router.message(Command("book_client"))
@readonly_router.message(Command("sick"))
@readonly_router.message(Command("courses"))
@readonly_router.message(F.text.in_(WRITE_INTENT_TEXTS))
async def redirect_write_command(message: Message, tenant: Tenant) -> None:
    await reply_use_miniapp(message, tenant)


@readonly_router.callback_query()
async def redirect_write_callback(callback: CallbackQuery, tenant: Tenant) -> None:
    if not is_write_callback(callback.data):
        raise SkipHandler
    await callback_use_miniapp(callback, tenant)
