import logging
from uuid import UUID

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramUnauthorizedError
from aiogram.types import InputMediaPhoto
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.registry import get_bot_for_tenant
from app.domain.models import ClientProfile, Notification, NotificationStatus, NotificationType, Tenant
from app.domain.services.message_tokens import render_booking_notification
from app.domain.services.notification_templates import build_notification_message

logger = logging.getLogger(__name__)

_RENDERABLE = {
    NotificationType.BOOKING_CONFIRMED.value,
    NotificationType.REMINDER_24H.value,
    NotificationType.REMINDER_2H.value,
    NotificationType.BOOKING_CANCELLED.value,
}


async def send_notification(session: AsyncSession, notification: Notification) -> None:
    tenant = await session.get(Tenant, notification.tenant_id)
    if tenant is None or not tenant.bot_token_encrypted:
        notification.status = NotificationStatus.FAILED.value
        return
    bot = get_bot_for_tenant(tenant)
    payload = notification.payload or {}
    booking_id = payload.get("booking_id") or (
        str(notification.booking_id) if notification.booking_id else None
    )
    if booking_id and "booking_id" not in payload:
        payload = {**payload, "booking_id": booking_id}

    parse_mode: str | None = None
    photo_urls: list[str] = []
    text: str
    reply_markup = None

    if booking_id and notification.notification_type in _RENDERABLE:
        rendered = await render_booking_notification(
            session,
            tenant_id=notification.tenant_id,
            kind=notification.notification_type,
            booking_id=UUID(str(booking_id)),
        )
        if rendered:
            text, parse_mode, photo_urls = rendered
            _, reply_markup = build_notification_message(notification.notification_type, payload)
        else:
            text, reply_markup = build_notification_message(notification.notification_type, payload)
    else:
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
        kwargs: dict = {}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        if photo_urls:
            if len(photo_urls) == 1:
                await bot.send_photo(chat_id, photo_urls[0], caption=text[:1024], reply_markup=reply_markup, **kwargs)
            else:
                cap_kwargs: dict = {"caption": text[:1024]}
                if parse_mode:
                    cap_kwargs["parse_mode"] = parse_mode
                media = [InputMediaPhoto(media=photo_urls[0], **cap_kwargs)]
                for url in photo_urls[1:10]:
                    media.append(InputMediaPhoto(media=url))
                await bot.send_media_group(chat_id, media)
                if reply_markup:
                    await bot.send_message(chat_id, "👇", reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id, text, reply_markup=reply_markup, **kwargs)
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