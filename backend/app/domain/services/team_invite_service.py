"""Staff invite links for binding Telegram accounts to staff profiles."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import log_audit
from app.domain.exceptions import DomainError
from app.domain.models import StaffInvite, StaffMember, UserAccount

INVITE_TTL_DAYS = 7
INVITE_PREFIX = "inv_"


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def invite_start_param(raw_token: str) -> str:
    return f"{INVITE_PREFIX}{raw_token}"


def parse_invite_token(start_param: str | None) -> str | None:
    if not start_param or not start_param.startswith(INVITE_PREFIX):
        return None
    token = start_param[len(INVITE_PREFIX) :].strip()
    return token or None


async def create_invite(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    created_by_user_account_id: UUID | None,
    intended_roles: list[str] | None = None,
) -> tuple[StaffInvite, str]:
    staff = await session.get(StaffMember, staff_member_id)
    if staff is None or staff.tenant_id != tenant_id:
        raise DomainError("staff not found")
    if staff.user_account_id is not None:
        raise DomainError("staff already linked")

    raw = secrets.token_urlsafe(24)
    invite = StaffInvite(
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        token_hash=_hash_token(raw),
        intended_roles=intended_roles or ["specialist"],
        created_by_user_account_id=created_by_user_account_id,
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invite)
    await session.flush()
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="staff_invite_created",
        entity_type="staff_invite",
        entity_id=invite.id,
        actor_user_id=created_by_user_account_id,
        details={"staff_member_id": str(staff_member_id)},
    )
    return invite, raw


async def revoke_active_invites(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
) -> None:
    now = datetime.now(UTC)
    rows = (
        await session.scalars(
            select(StaffInvite).where(
                StaffInvite.tenant_id == tenant_id,
                StaffInvite.staff_member_id == staff_member_id,
                StaffInvite.used_at.is_(None),
                StaffInvite.revoked_at.is_(None),
            )
        )
    ).all()
    for inv in rows:
        inv.revoked_at = now


async def regenerate_invite(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    created_by_user_account_id: UUID | None,
    intended_roles: list[str] | None = None,
) -> tuple[StaffInvite, str]:
    await revoke_active_invites(session, tenant_id=tenant_id, staff_member_id=staff_member_id)
    return await create_invite(
        session,
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        created_by_user_account_id=created_by_user_account_id,
        intended_roles=intended_roles,
    )


async def accept_invite(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    telegram_user_id: int,
    raw_token: str,
) -> StaffMember:
    token_hash = _hash_token(raw_token)
    invite = await session.scalar(
        select(StaffInvite).where(
            StaffInvite.tenant_id == tenant_id,
            StaffInvite.token_hash == token_hash,
        )
    )
    if invite is None:
        raise DomainError("invalid invite")
    if invite.revoked_at is not None:
        raise DomainError("invite revoked")
    if invite.used_at is not None:
        raise DomainError("invite already used")
    if invite.expires_at < datetime.now(UTC):
        raise DomainError("invite expired")

    staff = await session.get(StaffMember, invite.staff_member_id)
    if staff is None or staff.tenant_id != tenant_id:
        raise DomainError("staff not found")
    if staff.user_account_id is not None:
        raise DomainError("staff already linked")

    user = await session.scalar(select(UserAccount).where(UserAccount.telegram_user_id == telegram_user_id))
    if user is None:
        user = UserAccount(telegram_user_id=telegram_user_id)
        session.add(user)
        await session.flush()

    existing = await session.scalar(
        select(StaffMember).where(
            StaffMember.tenant_id == tenant_id,
            StaffMember.user_account_id == user.id,
        )
    )
    if existing is not None and existing.id != staff.id:
        raise DomainError("telegram account already linked to another staff profile")

    staff.user_account_id = user.id
    roles = set(staff.roles or [])
    roles.update(invite.intended_roles or ["specialist"])
    if "specialist" not in roles and "manager" not in roles and "owner" not in roles:
        roles.add("specialist")
    staff.roles = sorted(roles)
    invite.used_at = datetime.now(UTC)
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="staff_invite_accepted",
        entity_type="staff_member",
        entity_id=staff.id,
        actor_user_id=user.id,
        details={"invite_id": str(invite.id)},
    )
    return staff
