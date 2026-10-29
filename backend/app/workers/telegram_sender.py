import logging

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramUnauthorizedError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.registry import get_bot_for_tenant
from app.domain.models import ClientProfile, Notification, NotificationStatus, NotificationType, Tenant

logger = logging.getLogger(__name__)

_REMINDER_LABELS = {
    NotificationType.BOOKING_CONFIRMED.value: "Запись подтверждена",
    NotificationType.REMINDER_24H.value: "Напоминание: визит завтра",
    NotificationType.REMINDER_2H.value: "Напоминание: визит через 2 часа",
}


async def send_notification(session: AsyncSession, notification: Notification) -> None:
    tenant = await session.get(Tenant, notification.tenant_id)
    if tenant is None or not tenant.bot_token_encrypted:
        notification.status = NotificationStatus.FAILED.value
        return
    bot = get_bot_for_tenant(tenant)
    label = _REMINDER_LABELS.get(notification.notification_type, f"Уведомление: {notification.notification_type}")
    text = label
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

    reply_markup: InlineKeyboardMarkup | None = None
    booking_id = notification.booking_id or (notification.payload or {}).get("booking_id")
    require_confirm = False
    if notification.notification_type == NotificationType.REMINDER_24H.value:
        require_confirm = True
        for off in (tenant.rules or {}).get("reminder_offsets") or []:
            if isinstance(off, dict) and off.get("type") == NotificationType.REMINDER_24H.value:
                require_confirm = bool(off.get("require_confirm", True))
                break
    if require_confirm and booking_id:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Подтверждаю", callback_data=f"confirm_visit:{booking_id}")]
            ]
        )

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
