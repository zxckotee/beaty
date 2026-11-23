"""One-time codes to merge UserAccount across Telegram and MAX."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass

from app.core.redis_client import get_redis
from app.messenger.types import Channel

LINK_PREFIX = "link_"
_TTL = 600
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@dataclass(frozen=True)
class AccountLinkResult:
    ok: bool
    reason: str
    primary_user_id: str | None = None


def parse_link_code(start_param: str | None) -> str | None:
    if not start_param or not start_param.startswith(LINK_PREFIX):
        return None
    code = start_param[len(LINK_PREFIX) :]
    return code if _CODE_RE.match(code) else None


def start_param_for_link(code: str) -> str:
    return f"{LINK_PREFIX}{code}"


def _key(code: str) -> str:
    return f"accountlink:{code}"


async def create_account_link_code(*, tenant_public_id: str, user_account_id: str, channel: Channel) -> str:
    code = secrets.token_urlsafe(10)
    redis = await get_redis()
    await redis.set(
        _key(code),
        json.dumps(
            {
                "tenant": tenant_public_id,
                "user_account_id": user_account_id,
                "channel": channel.value,
                "status": "pending",
            }
        ),
        ex=_TTL,
    )
    return code


async def confirm_account_link(
    code: str,
    *,
    tenant_public_id: str,
    channel: Channel,
    messenger_user_id: int,
    user_account_id: str,
) -> AccountLinkResult:
    redis = await get_redis()
    raw = await redis.get(_key(code))
    if raw is None:
        return AccountLinkResult(False, "missing")
    data = json.loads(raw)
    if data.get("tenant") != tenant_public_id:
        return AccountLinkResult(False, "wrong_tenant")
    if data.get("status") != "pending":
        return AccountLinkResult(False, "used")
    if data.get("channel") == channel.value:
        return AccountLinkResult(False, "same_channel")
    data["status"] = "confirmed"
    data["target_channel"] = channel.value
    data["target_messenger_user_id"] = messenger_user_id
    data["target_user_account_id"] = user_account_id
    await redis.set(_key(code), json.dumps(data), ex=120)
    return AccountLinkResult(True, "ok", primary_user_id=data.get("user_account_id"))