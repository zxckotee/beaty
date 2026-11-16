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


@dataclass(frozen=True)
class LoginPoll:
    state: LoginState
    telegram_user_id: int | None = None
    display_name: str | None = None


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
) -> bool:
    """Called by the bot. Returns False for unknown, expired, foreign-tenant or reused codes."""
    redis = await get_redis()
    raw = await redis.get(_key(code))
    if raw is None:
        return False
    data = json.loads(raw)
    if data.get("tenant") != tenant_public_id or data.get("status") != "pending":
        return False
    data.update({"status": "confirmed", "telegram_user_id": telegram_user_id, "name": display_name})
    await redis.set(_key(code), json.dumps(data), ex=CONFIRMED_TTL_SECONDS)
    return True


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
