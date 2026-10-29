"""Long polling for all active tenant salon bots.

Uses one shared Dispatcher (routers are process singletons) and per-tenant
getUpdates loops, same pattern as webhook ``feed_update``.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramUnauthorizedError
from sqlalchemy import select

from app.bot.dispatcher_setup import dispatcher
from app.bot.factory import create_bot
from app.core.crypto import decrypt_bot_token
from app.core.db import SessionLocal
from app.core.logging_config import setup_logging
from app.domain.models import Tenant
from app.domain.services.bot_token_alerts import notify_owner_bot_token_revoked
from app.domain.services.provisioning import mark_tenant_bot_revoked

logger = logging.getLogger(__name__)

RELOAD_INTERVAL_SEC = 60
GET_UPDATES_TIMEOUT = 30
POLL_ERROR_BACKOFF_SEC = 5


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


async def _handle_unauthorized(public_id: str) -> None:
    async with SessionLocal() as session:
        newly_revoked = await mark_tenant_bot_revoked(session, public_id=public_id)
        if newly_revoked:
            await session.commit()
            logger.error(
                "tenant %s: bot token unauthorized — marked revoked, polling stopped",
                public_id,
            )
            await notify_owner_bot_token_revoked(public_id)
        else:
            logger.warning("tenant %s: unauthorized (already revoked)", public_id)


async def _poll_one(public_id: str, token: str) -> None:
    bot = create_bot(token)
    setattr(bot, "tenant_public_id", public_id)
    offset: int | None = None
    try:
        try:
            me = await bot.get_me()
        except TelegramUnauthorizedError:
            await _handle_unauthorized(public_id)
            return
        logger.info("tenant bot @%s (%s) polling", me.username, public_id)
        await bot.delete_webhook(drop_pending_updates=False)
        while True:
            try:
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=GET_UPDATES_TIMEOUT,
                    allowed_updates=dispatcher.resolve_used_update_types(),
                )
                for update in updates:
                    offset = update.update_id + 1
                    await dispatcher.feed_update(bot, update)
            except asyncio.CancelledError:
                raise
            except TelegramUnauthorizedError:
                await _handle_unauthorized(public_id)
                return
            except Exception:
                logger.exception("poll error tenant=%s", public_id)
                await asyncio.sleep(POLL_ERROR_BACKOFF_SEC)
    finally:
        await bot.session.close()


async def main() -> None:
    tasks: dict[str, asyncio.Task] = {}

    while True:
        tenants = {pid: tok for pid, tok in await _load_tenants()}
        if tenants:
            logger.info("tenant polling: %d active bot(s)", len(tenants))
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
