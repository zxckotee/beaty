from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.core.settings import get_settings


def create_bot(token: str) -> Bot:
    proxy = get_settings().telegram_proxy
    if proxy:
        return Bot(token=token, session=AiohttpSession(proxy=proxy))
    return Bot(token=token)
