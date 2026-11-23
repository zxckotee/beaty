from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Channel(enum.StrEnum):
    TELEGRAM = "telegram"
    MAX = "max"

    @property
    def user_id_field(self) -> str:
        return "telegram_user_id" if self is Channel.TELEGRAM else "max_user_id"


@dataclass
class MessengerUser:
    id: int
    full_name: str | None = None
    username: str | None = None


@dataclass
class IncomingText:
    channel: Channel
    tenant_public_id: str
    user: MessengerUser
    text: str
    start_payload: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class IncomingCallback:
    channel: Channel
    tenant_public_id: str
    user: MessengerUser
    data: str
    callback_id: str
    raw: dict[str, Any] = field(default_factory=dict)