import logging
from uuid import UUID

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramUnauthorizedError
from aiogram.types import InputMediaPhoto
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.miniapp import bot_chat_write_enabled, miniapp_url_for_tenant
from app.bot.outbound_log_context import OutboundLogKind, outbound_log_context
from app.bot.registry import get_bot_for_tenant
from app.domain.models import ClientProfile, Notification, NotificationStatus, NotificationType, Tenant, UserAccount
from app.domain.services.message_tokens import render_booking_notification
from app.domain.services.notification_templates import build_notification_message
from app.max.client import MaxApiError, MaxClient
from app.max.session import create_max_bot
from app.messenger.ui import reply_markup_to_max_attachments

logger = logging.getLogger(__name__)

_RENDERABLE = {
    NotificationType.BOOKING_CONFIRMED.value,
    NotificationType.REMINDER_24H.value,
    NotificationType.REMINDER_2H.value,
    NotificationType.BOOKING_CANCELLED.value,
}


async def _build_message(session: AsyncSession, tenant: Tenant, notification: Notification):
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
    template_kwargs = {
        "chat_writes": bot_chat_write_enabled(),
        "miniapp_url": miniapp_url_for_tenant(tenant),
    }

    if booking_id and notification.notification_type in _RENDERABLE:
        rendered = await render_booking_notification(
            session,
            tenant_id=notification.tenant_id,
            kind=notification.notification_type,
            booking_id=UUID(str(booking_id)),
        )
        if rendered:
            text, parse_mode, photo_urls = rendered
            _, reply_markup = build_notification_message(
                notification.notification_type, payload, **template_kwargs
            )
        else:
            text, reply_markup = build_notification_message(
                notification.notification_type, payload, **template_kwargs
            )
    else:
        text, reply_markup = build_notification_message(
            notification.notification_type, payload, **template_kwargs
        )
    return text, parse_mode, photo_urls, reply_markup


async def send_notification(session: AsyncSession, notification: Notification) -> None:
    tenant = await session.get(Tenant, notification.tenant_id)
    if tenant is None:
        notification.status = NotificationStatus.FAILED.value
        return

    user: UserAccount | None = None
    if notification.recipient_type == "client":
        profile = await session.get(ClientProfile, notification.recipient_id)
        if profile and profile.user_account_id:
            user = await session.get(UserAccount, profile.user_account_id)
    if user is None:
        notification.status = NotificationStatus.FAILED.value
        return

    text, parse_mode, photo_urls, reply_markup = await _build_message(session, tenant, notification)
    sent_any = False
    failures: list[str] = []

    if user.telegram_user_id and tenant.bot_token_encrypted:
        bot = get_bot_for_tenant(tenant)
        try:
            with outbound_log_context(OutboundLogKind.NOTIFICATION):
                kwargs: dict = {}
                if parse_mode:
                    kwargs["parse_mode"] = parse_mode
                chat_id = user.telegram_user_id
                if photo_urls:
                    if len(photo_urls) == 1:
                        await bot.send_photo(
                            chat_id, photo_urls[0], caption=text[:1024], reply_markup=reply_markup, **kwargs
                        )
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
            sent_any = True
        except TelegramForbiddenError:
            await session.execute(
                update(ClientProfile)
                .where(ClientProfile.id == notification.recipient_id)
                .values(telegram_unreachable=True)
            )
            failures.append("telegram_forbidden")
        except TelegramUnauthorizedError:
            tenant.bot_status = "revoked"
            failures.append("telegram_unauthorized")
        except TelegramAPIError as exc:
            logger.warning("telegram send failed: %s", exc)
            failures.append("telegram_api")

    if user.max_user_id and tenant.max_bot_token_encrypted:
        from app.core.crypto import decrypt_bot_token

        token = decrypt_bot_token(tenant.max_bot_token_encrypted)
        client = MaxClient(token)
        bot = create_max_bot(token)
        attachments = reply_markup_to_max_attachments(reply_markup)
        fmt = "html" if parse_mode and str(parse_mode).lower() == "html" else None
        try:
            if photo_urls:
                await client.send_message(user_id=user.max_user_id, text=text[:1024] or "📷", format=fmt)
            else:
                await client.send_message(
                    user_id=user.max_user_id,
                    text=text,
                    attachments=attachments,
                    format=fmt,
                )
            sent_any = True
        except MaxApiError as exc:
            logger.warning("max send failed: %s", exc)
            failures.append("max_api")
        finally:
            await bot.session.close()

    if sent_any:
        notification.status = NotificationStatus.SENT.value
        if failures:
            notification.payload = {**(notification.payload or {}), "partial_failures": failures}
    else:
        notification.status = NotificationStatus.FAILED.value
        notification.payload = {**(notification.payload or {}), "failures": failures}