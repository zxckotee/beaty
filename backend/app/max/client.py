from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


class MaxApiError(Exception):
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"MAX API {status}: {body[:200]}")


class MaxClient:
    def __init__(self, token: str, *, base_url: str | None = None) -> None:
        settings = get_settings()
        self.token = token
        self.base_url = (base_url or settings.max_api_base_url).rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.token, "Content-Type": "application/json"}

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
            )
        if response.status_code >= 400:
            raise MaxApiError(response.status_code, response.text)
        if response.content:
            return response.json()
        return None

    async def get_me(self) -> dict[str, Any]:
        data = await self.request("GET", "/me")
        return data or {}

    async def send_message(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        format: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = user_id
        if chat_id is not None:
            params["chat_id"] = chat_id
        body: dict[str, Any] = {"text": text[:4000]}
        if attachments:
            body["attachments"] = attachments
        if format:
            body["format"] = format
        data = await self.request("POST", "/messages", params=params, json_body=body)
        return data or {}

    async def answer_callback(self, callback_id: str, *, message: dict[str, Any] | None = None) -> None:
        body: dict[str, Any] = {}
        if message is not None:
            body["message"] = message
        await self.request("POST", "/answers", params={"callback_id": callback_id}, json_body=body)

    async def set_subscription(
        self, *, url: str, secret: str, update_types: list[str] | None = None
    ) -> None:
        types = update_types or [
            "message_created",
            "message_callback",
            "bot_started",
        ]
        await self.request(
            "POST",
            "/subscriptions",
            json_body={"url": url, "secret": secret, "update_types": types},
        )

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/subscriptions")
        if isinstance(data, dict) and "subscriptions" in data:
            subs = data["subscriptions"]
            return subs if isinstance(subs, list) else []
        if isinstance(data, list):
            return data
        return []