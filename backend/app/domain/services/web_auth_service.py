"""One-time login codes that let a Telegram user sign in to the web cabinet via the tenant bot.

Flow: the site creates a code -> the user opens ``t.me/<bot>?start=web_<code>`` -> the bot
calls :func:`confirm_login` -> the site polls :func:`poll_login` and gets the confirmed user.
Both the bot and the web service call this same module.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from typing import Literal

from app.core.redis_client import get_redis

LOGIN_PREFIX = "web_"
PENDING_TTL_SECONDS = 300
CONFIRMED_TTL_SECONDS = 120
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

LoginState = Literal["pending", "confirmed", "expired"]
ConfirmReason = Literal["ok", "already_ok", "missing", "wrong_tenant", "used", "bad_state"]


@dataclass(frozen=True)
class LoginPoll:
    state: LoginState
    telegram_user_id: int | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class ConfirmLoginResult:
    ok: bool
    reason: ConfirmReason


def _key(code: str) -> str:
    return f"weblogin:{code}"


def parse_login_code(start_param: str | None) -> str | None:
    """Extract the code from a ``/start web_<code>`` parameter."""
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
    telegram_user_id: int,
    display_name: str | None = None,
) -> ConfirmLoginResult:
    """Called by the bot when the user opens the deep link from the web cabinet."""
    redis = await get_redis()
    raw = await redis.get(_key(code))
    if raw is None:
        return ConfirmLoginResult(False, "missing")
    data = json.loads(raw)
    if data.get("tenant") != tenant_public_id:
        return ConfirmLoginResult(False, "wrong_tenant")
    status = data.get("status")
    if status == "confirmed":
        if int(data.get("telegram_user_id", 0)) == telegram_user_id:
            return ConfirmLoginResult(True, "already_ok")
        return ConfirmLoginResult(False, "used")
    if status != "pending":
        return ConfirmLoginResult(False, "bad_state")
    data.update({"status": "confirmed", "telegram_user_id": telegram_user_id, "name": display_name})
    await redis.set(_key(code), json.dumps(data), ex=CONFIRMED_TTL_SECONDS)
    return ConfirmLoginResult(True, "ok")


def bot_message_for_confirm(result: ConfirmLoginResult, *, bot_username: str | None) -> str:
    if result.ok and result.reason == "ok":
        return "Готово! Вы вошли на сайт. Вернитесь в браузер — страница обновится сама."
    if result.ok and result.reason == "already_ok":
        return "Вход уже подтверждён. Вернитесь на сайт в браузере — если не пускает, нажмите «Войти» и Start ещё раз."
    if result.reason == "wrong_tenant":
        salon = f"@{bot_username}" if bot_username else "бота этого салона"
        return (
            f"Эта ссылка от другого салона. На сайте нажмите «Войти через Telegram» и откройте {salon}."
        )
    if result.reason == "used":
        return (
            "Эту ссылку уже использовали с другого Telegram. "
            "На сайте нажмите «Войти через Telegram» и получите новую."
        )
    return (
        "Не удалось подтвердить вход: код не найден или истёк. На сайте нажмите «Войти через Telegram» ещё раз "
        "и в открывшемся чате кнопку Start (не вводите /start вручную из меню команд)."
    )


async def poll_login(code: str, *, tenant_public_id: str) -> LoginPoll:
    """Called by the site. A confirmed code is consumed (single use)."""
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
    return LoginPoll("confirmed", int(data["telegram_user_id"]), data.get("name"))