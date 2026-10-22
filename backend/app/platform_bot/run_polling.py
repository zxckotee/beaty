import asyncio
import logging

from app.bot.factory import create_bot
from app.core.logging_config import setup_logging
from app.core.settings import get_settings
from app.platform_bot.dispatcher_setup import platform_dispatcher

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    if not settings.platform_bot_token:
        raise SystemExit("PLATFORM_BOT_TOKEN is not set")

    bot = create_bot(settings.platform_bot_token)
    me = await bot.get_me()
    logger.info("platform bot @%s starting long polling", me.username)
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await platform_dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
