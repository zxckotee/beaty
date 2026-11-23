"""One-time login codes for signing in to the web cabinet via tenant bots (Telegram or MAX)."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from typing import Literal

from app.core.redis_client import get_redis
from app.messenger.types import Channel

LOGIN_PREFIX = "web_"
PENDING_TTL_SECONDS = 300
CONFIRMED_TTL_SECONDS = 120
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

LoginState = Literal["pending", "confirmed", "expired"]
ConfirmReason = Literal["ok", "already_ok", "missing", "wrong_tenant", "used", "bad_state"]


@dataclass(frozen=True)
class LoginPoll:
    state: LoginState
    messenger_user_id: int | None = None
    channel: Channel | None = None
    display_name: str | None = None

    @property
    def telegram_user_id(self) -> int | None:
        if self.channel is Channel.TELEGRAM or self.channel is None:
            return self.messenger_user_id
        return None


@dataclass(frozen=True)
class ConfirmLoginResult:
    ok: bool
    reason: ConfirmReason


def _key(code: str) -> str:
    return f"weblogin:{code}"


def parse_login_code(start_param: str | None) -> str | None:
    if not start_param or not start_param.startswith(LOGIN_PREFIX):
        return None
    code = start_param[len(LOGIN_PREFIX) :]
    return code if _CODE_RE.match(code) else None


def start_param_for(code: str) -> str:
    return f"{LOGIN_PREFIX}{code}"


async def create_login_request(tenant_public_id: str) -> str:
    code = secrets.token_urlsafe(12)
    redis = await get_redis()
    await redis.set(_key(code), json.dumps({"tenant": tenant_public_id, "status": "pending"}), ex=PENDING_TTL_SECONDS)
    return code


async def confirm_login(
    code: str,
    *,
    tenant_public_id: str,
    channel: Channel,
    messenger_user_id: int,
    display_name: str | None = None,
) -> ConfirmLoginResult:
    redis = await get_redis()
    raw = await redis.get(_key(code))
    if raw is None:
        return ConfirmLoginResult(False, "missing")
    data = json.loads(raw)
    if data.get("tenant") != tenant_public_id:
        return ConfirmLoginResult(False, "wrong_tenant")
    status = data.get("status")
    if status == "confirmed":
        if (
            data.get("channel") == channel.value
            and int(data.get("messenger_user_id", 0)) == messenger_user_id
        ):
            return ConfirmLoginResult(True, "already_ok")
        return ConfirmLoginResult(False, "used")
    if status != "pending":
        return ConfirmLoginResult(False, "bad_state")
    data.update(
        {
            "status": "confirmed",
            "channel": channel.value,
            "messenger_user_id": messenger_user_id,
            "name": display_name,
        }
    )
    await redis.set(_key(code), json.dumps(data), ex=CONFIRMED_TTL_SECONDS)
    return ConfirmLoginResult(True, "ok")


def bot_message_for_confirm(
    result: ConfirmLoginResult, *, bot_username: str | None, channel: Channel = Channel.TELEGRAM
) -> str:
    label = "Telegram" if channel is Channel.TELEGRAM else "MAX"
    if result.ok and result.reason == "ok":
        return "Готово! Вы вошли на сайт. Вернитесь в браузер — страница обновится сама."
    if result.ok and result.reason == "already_ok":
        return "Вход уже подтверждён. Вернитесь на сайт в браузере."
    if result.reason == "wrong_tenant":
        salon = f"@{bot_username}" if bot_username else "бота этого салона"
        return f"Эта ссылка от другого салона. На сайте нажмите «Войти через {label}» и откройте {salon}."
    if result.reason == "used":
        return f"Эту ссылку уже использовали. На сайте получите новую ссылку для {label}."
    return (
        f"Не удалось подтвердить вход. На сайте нажмите «Войти через {label}» ещё раз "
        "и откройте чат с ботом из ссылки."
    )


async def poll_login(code: str, *, tenant_public_id: str) -> LoginPoll:
    if not _CODE_RE.match(code):
        return LoginPoll("expired")
    redis = await get_redis()
    raw = await redis.get(_key(code))
    if raw is None:
        return LoginPoll("expired")
    data = json.loads(raw)
    if data.get("tenant") != tenant_public_id:
        return LoginPoll("expired")
    if data.get("status") != "confirmed":
        return LoginPoll("pending")
    if not await redis.delete(_key(code)):
        return LoginPoll("expired")
    channel_raw = data.get("channel") or Channel.TELEGRAM.value
    channel = Channel.MAX if channel_raw == Channel.MAX.value else Channel.TELEGRAM
    messenger_user_id = data.get("messenger_user_id")
    if messenger_user_id is None and data.get("telegram_user_id") is not None:
        messenger_user_id = data["telegram_user_id"]
        channel = Channel.TELEGRAM
    return LoginPoll(
        "confirmed",
        int(messenger_user_id) if messenger_user_id is not None else None,
        channel,
        data.get("name"),
    )