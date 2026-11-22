from aiogram import Bot

from app.bot.session.logging_session import LoggingAiohttpSession
from app.core.settings import get_settings


def create_bot(token: str) -> Bot:
    proxy = get_settings().telegram_proxy
    if proxy:
        return Bot(token=token, session=LoggingAiohttpSession(proxy=proxy))
    return Bot(token=token, session=LoggingAiohttpSession())
