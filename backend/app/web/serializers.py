from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.domain.models import Service, StaffMember, TimeCell
from app.domain.services.cell_service import CellBooking, CellOffer, CellView


def photo_url_for_staff(staff: StaffMember, tenant_public_id: str) -> str | None:
    if staff.photo_url:
        return staff.photo_url
    if staff.photo_file_id:
        return f"/media/tg/{tenant_public_id}/{staff.id}"
    return None


def staff_card(staff: StaffMember, tenant_public_id: str) -> dict[str, object]:
    return {
        "id": str(staff.id),
        "name": staff.display_name,
        "specialization": staff.specialization,
        "bio": staff.bio,
        "photo_url": photo_url_for_staff(staff, tenant_public_id),
        "is_active": staff.is_active,
    }


def service_card(service: Service, category_name: str | None = None) -> dict[str, object]:
    return {
        "id": str(service.id),
        "name": service.name,
        "description": service.description,
        "photo_url": service.photo_url,
        "price_cents": service.price_cents,
        "duration_minutes": service.duration_minutes,
        "buffer_minutes": service.buffer_minutes,
        "category": category_name,
        "is_active": service.is_active,
    }


def hhmm(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%H:%M")


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def parse_local(day: date, value: str, tz: ZoneInfo) -> datetime:
    """Local wall-clock ``HH:MM`` on ``day`` in the branch timezone; ``24:00`` means next midnight."""
    if value == "24:00":
        return datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    hours, minutes = value.split(":")
    return datetime.combine(day, time(int(hours), int(minutes)), tzinfo=tz)


def cell_status(view: CellView) -> str:
    if view.free_minutes <= 0:
        return "full"
    if view.free_minutes < view.total_minutes:
        return "partial"
    return "free"


def booking_dict(b: CellBooking, tz: ZoneInfo, *, reveal: bool) -> dict[str, object]:
    data: dict[str, object] = {
        "booking_id": str(b.booking_id),
        "status": b.status,
        "start": hhmm(b.start, tz),
        "end": hhmm(b.end, tz),
        "service_names": b.service_names,
        "total_price_cents": b.total_price_cents,
    }
    if reveal:
        data.update({"client_name": b.client_name, "client_phone": b.client_phone, "comment": b.comment})
    return data


def cell_dict(view: CellView, tz: ZoneInfo, tenant_public_id: str, *, reveal_clients: bool = True) -> dict[str, object]:
    cell: TimeCell = view.cell
    return {
        "id": str(cell.id),
        "date": local_date(cell.starts_at, tz).isoformat(),
        "start": hhmm(cell.starts_at, tz),
        "end": hhmm(cell.ends_at, tz) if cell.ends_at - cell.starts_at < timedelta(days=1) else "24:00",
        "end_next_day": local_date(cell.ends_at - timedelta(seconds=1), tz) != local_date(cell.starts_at, tz),
        "minutes": view.total_minutes,
        "free_minutes": view.free_minutes,
        "status": cell_status(view),
        "price_cents": cell.price_cents,
        "title": cell.title,
        "description": cell.description,
        "allowed_service_ids": list(cell.allowed_service_ids or []),
        "staff": staff_card(view.staff, tenant_public_id),
        "bookings": [booking_dict(b, tz, reveal=reveal_clients) for b in view.bookings],
    }


def offer_dict(offer: CellOffer, tz: ZoneInfo, tenant_public_id: str) -> dict[str, object]:
    cell = offer.cell
    return {
        "cell_id": str(cell.id),
        "date": local_date(offer.start_at, tz).isoformat(),
        "start": hhmm(offer.start_at, tz),
        "end": hhmm(offer.end_at, tz),
        "cell_start": hhmm(cell.starts_at, tz),
        "cell_end": hhmm(cell.ends_at, tz),
        "title": cell.title,
        "description": cell.description,
        "price_adjust_cents": cell.price_cents,
        "free_minutes": offer.free_minutes,
        "staff": staff_card(offer.staff, tenant_public_id),
        "services": [
            {
                "id": str(n.service_id),
                "name": n.name,
                "duration_minutes": n.duration_minutes,
                "price_cents": n.price_cents,
            }
            for n in offer.needs
        ],
        "total_price_cents": offer.total_price_cents,
        "total_minutes": offer.total_duration_minutes,
    }


def uuid_list(raw: list[UUID] | None) -> list[UUID]:
    return list(raw or [])
