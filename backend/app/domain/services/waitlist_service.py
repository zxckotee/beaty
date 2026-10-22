from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import WaitlistEntry


async def join_waitlist(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    client_profile_id: UUID,
    service_id: UUID,
    staff_member_id: UUID | None,
    preferred_date: datetime | None,
) -> WaitlistEntry:
    entry = WaitlistEntry(
        tenant_id=tenant_id,
        client_profile_id=client_profile_id,
        service_id=service_id,
        staff_member_id=staff_member_id,
        preferred_date=preferred_date,
    )
    session.add(entry)
    await session.flush()
    return entry


async def pop_matching_waitlist(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    service_id: UUID,
    staff_member_id: UUID | None,
) -> WaitlistEntry | None:
    q = select(WaitlistEntry).where(
        WaitlistEntry.tenant_id == tenant_id,
        WaitlistEntry.service_id == service_id,
        WaitlistEntry.status == "active",
    )
    if staff_member_id:
        q = q.where(
            (WaitlistEntry.staff_member_id == staff_member_id)
            | (WaitlistEntry.staff_member_id.is_(None))
        )
    entry = await session.scalar(q.order_by(WaitlistEntry.created_at).limit(1))
    if entry:
        entry.status = "offered"
    return entry
