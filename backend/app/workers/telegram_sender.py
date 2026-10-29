import logging

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramUnauthorizedError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.registry import get_bot_for_tenant
from app.domain.models import ClientProfile, Notification, NotificationStatus, Tenant
from app.domain.services.notification_templates import build_notification_message

logger = logging.getLogger(__name__)


async def send_notification(session: AsyncSession, notification: Notification) -> None:
    tenant = await session.get(Tenant, notification.tenant_id)
    if tenant is None or not tenant.bot_token_encrypted:
        notification.status = NotificationStatus.FAILED.value
        return
    bot = get_bot_for_tenant(tenant)
    payload = notification.payload or {}
    if "booking_id" not in payload and notification.booking_id:
        payload = {**payload, "booking_id": str(notification.booking_id)}
    text, reply_markup = build_notification_message(notification.notification_type, payload)
    chat_id: int | None = None
    if notification.recipient_type == "client":
        profile = await session.get(ClientProfile, notification.recipient_id)
        if profile and profile.user_account_id:
            from app.domain.models import UserAccount

            user = await session.get(UserAccount, profile.user_account_id)
            if user:
                chat_id = user.telegram_user_id
    if chat_id is None:
        notification.status = NotificationStatus.FAILED.value
        return
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        notification.status = NotificationStatus.SENT.value
    except TelegramForbiddenError:
        await session.execute(
            update(ClientProfile)
            .where(ClientProfile.id == notification.recipient_id)
            .values(telegram_unreachable=True)
        )
        notification.status = NotificationStatus.FAILED.value
    except TelegramUnauthorizedError:
        tenant.bot_status = "revoked"
        notification.status = NotificationStatus.FAILED.value
    except TelegramAPIError as exc:
        logger.warning("telegram send failed: %s", exc)
        notification.status = NotificationStatus.FAILED.value
