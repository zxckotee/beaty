from __future__ import annotations

import enum
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID


class OutboundLogKind(enum.StrEnum):
    INTERACTIVE = "interactive"
    NOTIFICATION = "notification"
    MANAGER = "manager"


_kind_var: ContextVar[OutboundLogKind] = ContextVar("outbound_log_kind", default=OutboundLogKind.INTERACTIVE)
_staff_var: ContextVar[UUID | None] = ContextVar("outbound_staff_id", default=None)


def current_kind() -> OutboundLogKind:
    return _kind_var.get()


def current_staff_id() -> UUID | None:
    return _staff_var.get()


@contextmanager
def outbound_log_context(
    kind: OutboundLogKind,
    *,
    staff_member_id: UUID | None = None,
) -> Iterator[None]:
    t_kind: Token = _kind_var.set(kind)
    t_staff: Token | None = None
    if staff_member_id is not None:
        t_staff = _staff_var.set(staff_member_id)
    try:
        yield
    finally:
        _kind_var.reset(t_kind)
        if t_staff is not None:
            _staff_var.reset(t_staff)