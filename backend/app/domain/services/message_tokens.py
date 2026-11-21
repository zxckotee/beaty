from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.models import Booking, Branch, NotificationTemplate, Tenant, TenantLanding

_TOKEN = re.compile(r"\{([a-z_]+)\}")


@dataclass
class BookingMessageContext:
    service: str
    staff: str
    address: str
    price: str
    tenant_name: str
    dgis_url: str
    start_at: datetime | None
    timezone: str
    staff_photo_url: str | None
    venue_cover_url: str | None


TOKEN_PREVIEW_CONTEXT = BookingMessageContext(
    service="Стрижка",
    staff="Анна",
    address="ул. Примерная, 5",
    price="1500 ₽",
    tenant_name="Beauty Studio",
    dgis_url="https://2gis.ru",
    start_at=datetime(2026, 3, 15, 14, 30, tzinfo=ZoneInfo("Europe/Moscow")),
    timezone="Europe/Moscow",
    staff_photo_url=None,
    venue_cover_url=None,
)

DEFAULT_BODIES: dict[str, str] = {
    "booking_confirmed": (
        "✅ <b>Запись подтверждена!</b>\n\n"
        "📅 {datetime}\n"
        "✂️ {service}\n"
        "👤 Мастер: {staff}\n"
        "📍 {address}\n"
        "🗺 <a href=\"{dgis_url}\">Маршрут в 2ГИС</a>"
    ),
    "reminder_24h": (
        "⏰ <b>Напоминание о визите</b>\n\n"
        "Ждём вас {datetime}\n"
        "📍 {address}\n"
        "✂️ {service} · 👤 {staff}"
    ),
    "reminder_2h": (
        "⏰ <b>Скоро ваш визит!</b>\n\n"
        "{datetime}\n"
        "📍 {address}\n"
        "Не забудьте подтвердить запись кнопкой ниже 👇"
    ),
    "booking_cancelled": (
        "❌ Запись отменена.\n\n"
        "Было: {datetime}\n"
        "{service} · {staff}"
    ),
}


def render_template(body: str, ctx: BookingMessageContext) -> str:
    tz = ZoneInfo(ctx.timezone or "Europe/Moscow")
    local = ctx.start_at.astimezone(tz) if ctx.start_at else None
    values = {
        "service": ctx.service or "—",
        "staff": ctx.staff or "—",
        "address": ctx.address or "адрес уточните у салона",
        "price": ctx.price or "—",
        "tenant_name": ctx.tenant_name or "—",
        "dgis_url": ctx.dgis_url or "",
        "date": local.strftime("%d.%m.%Y") if local else "—",
        "time": local.strftime("%H:%M") if local else "—",
        "datetime": local.strftime("%d.%m.%Y в %H:%M") if local else "—",
    }

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return values.get(key, m.group(0))

    return _TOKEN.sub(repl, body)


def abs_media_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    settings = get_settings()
    base = (settings.public_web_url or settings.webhook_base_url or "").rstrip("/")
    if not base:
        return None
    return f"{base}{path}"


async def build_booking_context(session: AsyncSession, booking_id: UUID) -> BookingMessageContext | None:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        return None
    tenant = await session.get(Tenant, booking.tenant_id)
    branch = await session.get(Branch, booking.branch_id)
    row = await session.execute(
        text(
            """
            SELECT lower(bi.during) AS start_at,
                   s.name AS service_name,
                   sm.display_name AS staff_name,
                   sm.photo_url AS staff_photo,
                   bi.price_cents
            FROM booking_item bi
            JOIN service s ON s.id = bi.service_id
            JOIN staff_member sm ON sm.id = bi.staff_member_id
            WHERE bi.booking_id = :bid AND bi.is_active = true
            ORDER BY lower(bi.during)
            LIMIT 1
            """
        ),
        {"bid": str(booking_id)},
    )
    item = row.mappings().first()
    landing = await session.scalar(select(TenantLanding).where(TenantLanding.tenant_id == booking.tenant_id))
    dgis_url = landing.dgis_url if landing and landing.dgis_url else ""
    price = ""
    if item and item.get("price_cents") is not None:
        price = f"{int(item['price_cents']) // 100} ₽"
    return BookingMessageContext(
        service=(item or {}).get("service_name") or "Услуга",
        staff=(item or {}).get("staff_name") or "Мастер",
        address=(branch.address if branch else None) or "",
        price=price,
        tenant_name=tenant.name if tenant else "",
        dgis_url=dgis_url,
        start_at=item.get("start_at") if item else None,
        timezone=branch.timezone if branch else "Europe/Moscow",
        staff_photo_url=(item or {}).get("staff_photo"),
        venue_cover_url=landing.cover_url if landing else None,
    )


async def get_template_body(session: AsyncSession, tenant_id: UUID, kind: str) -> tuple[str, str]:
    tpl = await session.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.tenant_id == tenant_id, NotificationTemplate.kind == kind
        )
    )
    if tpl and tpl.body.strip():
        return tpl.body, tpl.parse_mode or "HTML"
    return DEFAULT_BODIES.get(kind, "Уведомление."), "HTML"


async def resolve_photo_urls(
    session: AsyncSession, tenant_id: UUID, kind: str, ctx: BookingMessageContext
) -> list[str]:
    tpl = await session.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.tenant_id == tenant_id, NotificationTemplate.kind == kind
        )
    )
    slots: list[Any] = list(tpl.photo_slots) if tpl and tpl.photo_slots else []
    urls: list[str] = []
    for slot in slots[:10]:
        if slot == "staff" or (isinstance(slot, dict) and slot.get("type") == "staff"):
            u = abs_media_url(ctx.staff_photo_url)
            if u:
                urls.append(u)
        elif slot == "venue_cover" or (isinstance(slot, dict) and slot.get("type") == "venue_cover"):
            u = abs_media_url(ctx.venue_cover_url)
            if u:
                urls.append(u)
        elif isinstance(slot, dict) and slot.get("type") == "custom" and slot.get("url"):
            u = abs_media_url(str(slot["url"]))
            if u:
                urls.append(u)
        elif isinstance(slot, str) and slot.startswith("/media/"):
            u = abs_media_url(slot)
            if u:
                urls.append(u)
    return urls


async def render_booking_notification(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    kind: str,
    booking_id: UUID,
) -> tuple[str, str, list[str]] | None:
    ctx = await build_booking_context(session, booking_id)
    if ctx is None:
        return None
    body, parse_mode = await get_template_body(session, tenant_id, kind)
    text = render_template(body, ctx)
    photos = await resolve_photo_urls(session, tenant_id, kind, ctx)
    if not ctx.dgis_url:
        import re as _re

        text = _re.sub(r'🗺[^\n]*\n?', "", text)
        text = _re.sub(r"<a href=\"\">[^<]*</a>\n?", "", text)
    return text, parse_mode, photos