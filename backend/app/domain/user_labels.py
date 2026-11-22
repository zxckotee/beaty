"""Human-readable labels for values stored as technical codes in DB and APIs."""

from __future__ import annotations

STAFF_ROLE_LABELS: dict[str, str] = {
    "owner": "Владелец",
    "manager": "Управляющий",
    "specialist": "Мастер",
    "reception": "Администратор",
}

BOOKING_STATUS_LABELS: dict[str, str] = {
    "held": "Ожидает",
    "booked": "Записан",
    "confirmed": "Подтверждён",
    "arrived": "Пришёл",
    "completed": "Завершён",
    "cancelled": "Отменён",
    "no_show": "Не пришёл",
}

MESSAGE_TOKEN_LABELS: dict[str, str] = {
    "service": "Услуга",
    "date": "Дата",
    "time": "Время",
    "datetime": "Дата и время",
    "staff": "Мастер",
    "address": "Адрес",
    "price": "Цена",
    "tenant_name": "Салон",
    "dgis_url": "Ссылка 2ГИС",
}

MESSAGE_TOKEN_ORDER: tuple[str, ...] = tuple(MESSAGE_TOKEN_LABELS.keys())


def staff_roles_display(roles: list[str] | None) -> str:
    if not roles:
        return "—"
    seen: set[str] = set()
    labels: list[str] = []
    for role in roles:
        label = STAFF_ROLE_LABELS.get(role)
        if label is None:
            continue
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return ", ".join(labels) if labels else "—"


def booking_status_display(status: str | None) -> str:
    if not status:
        return "—"
    return BOOKING_STATUS_LABELS.get(status, status)


def message_token_choices() -> list[tuple[str, str]]:
    return [(key, MESSAGE_TOKEN_LABELS[key]) for key in MESSAGE_TOKEN_ORDER]