from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_HTTP_URL = re.compile(r"^https?://", re.IGNORECASE)

WIDGET_TEMPLATES = frozenset(
    {"story", "visual", "gallery", "split", "highlight", "social_row", "cta_card"}
)


class BlockStyle(BaseModel):
    font: Literal["sans", "serif", "display"] = "sans"
    size: Literal["sm", "md", "lg", "xl"] = "md"
    color: str | None = None
    bg: str | None = None

    @field_validator("color", "bg")
    @classmethod
    def color_hex(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _HEX.match(v):
            raise ValueError("invalid color")
        return v


class ContentBlock(BaseModel):
    kind: Literal["heading", "text"]
    content: str = Field(default="", max_length=4000)
    style: BlockStyle = Field(default_factory=BlockStyle)


class ActionStyle(BaseModel):
    variant: Literal["filled", "outline", "ghost"] = "filled"
    color: str | None = None
    textColor: str | None = None

    @field_validator("color", "textColor")
    @classmethod
    def color_hex(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _HEX.match(v):
            raise ValueError("invalid color")
        return v


class WidgetAction(BaseModel):
    kind: Literal["book", "link"]
    label: str = Field(default="", max_length=120)
    href: str | None = Field(default=None, max_length=2000)
    preset: Literal["vk", "telegram", "max", "custom"] | None = None
    icon: Literal["calendar", "scissors", "phone", "none"] = "none"
    style: ActionStyle = Field(default_factory=ActionStyle)

    @model_validator(mode="after")
    def link_requires_href(self) -> WidgetAction:
        if self.kind == "link":
            href = (self.href or "").strip()
            if not href or not _HTTP_URL.match(href):
                raise ValueError("link requires http(s) href")
            if "javascript:" in href.lower():
                raise ValueError("invalid href")
        return self


class WidgetPayload(BaseModel):
    blocks: list[ContentBlock] = Field(default_factory=list, max_length=12)
    photos: list[str] = Field(default_factory=list, max_length=5)
    actions: list[WidgetAction] = Field(default_factory=list, max_length=8)


def normalize_widget_payload(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return WidgetPayload().model_dump()
    return WidgetPayload.model_validate(raw).model_dump()