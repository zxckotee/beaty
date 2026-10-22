import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.domain.models import Notification, NotificationStatus
from app.workers.telegram_sender import send_notification

logger = logging.getLogger(__name__)


async def process_due_notifications(batch_size: int = 50) -> int:
    processed = 0
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(Notification)
                .where(
                    Notification.status == NotificationStatus.PENDING.value,
                    Notification.send_at <= datetime.now(UTC),
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for n in rows:
            await send_notification(session, n)
            processed += 1
        await session.commit()
    return processed


async def scheduler_loop(interval_seconds: int = 60) -> None:
    while True:
        try:
            count = await process_due_notifications()
            if count:
                logger.info("sent notifications batch=%s", count)
        except Exception:
            logger.exception("scheduler iteration failed")
        await asyncio.sleep(interval_seconds)
