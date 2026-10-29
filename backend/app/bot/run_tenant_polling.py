"""Long polling for all active tenant salon bots."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.bot.dispatcher_setup import build_dispatcher
from app.bot.factory import create_bot
from app.core.crypto import decrypt_bot_token
from app.core.db import SessionLocal
from app.core.logging_config import setup_logging
from app.domain.models import Tenant

logger = logging.getLogger(__name__)

RELOAD_INTERVAL_SEC = 60


async def _load_tenants() -> list[tuple[str, str]]:
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(Tenant).where(
                    Tenant.bot_token_encrypted.isnot(None),
                    Tenant.bot_status == "active",
                )
            )
        ).all()
        out: list[tuple[str, str]] = []
        for t in rows:
            try:
                token = decrypt_bot_token(t.bot_token_encrypted or "")
            except Exception:
                logger.warning("skip tenant %s: token decrypt failed", t.public_id)
                continue
            out.append((t.public_id, token))
        return out


async def _poll_one(public_id: str, token: str) -> None:
    bot = create_bot(token)
    setattr(bot, "tenant_public_id", public_id)
    dp = build_dispatcher()
    me = await bot.get_me()
    logger.info("tenant bot @%s (%s) polling", me.username, public_id)
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await dp.start_polling(bot, handle_signals=False)
    finally:
        await bot.session.close()


async def main() -> None:
    tasks: dict[str, asyncio.Task] = {}

    while True:
        tenants = {pid: tok for pid, tok in await _load_tenants()}
        for pid, task in list(tasks.items()):
            if pid not in tenants:
                task.cancel()
                tasks.pop(pid, None)
        for pid, token in tenants.items():
            if pid not in tasks:
                tasks[pid] = asyncio.create_task(_poll_one(pid, token))
        await asyncio.sleep(RELOAD_INTERVAL_SEC)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
