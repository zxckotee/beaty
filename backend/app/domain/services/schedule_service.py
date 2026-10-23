from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import log_audit
from app.domain.models import ScheduleException, ScheduleTemplate
from app.domain.services.slot_repository import invalidate_slots_for_staff


async def list_templates(
    session: AsyncSession, *, tenant_id: UUID, staff_member_id: UUID
) -> list[ScheduleTemplate]:
    return list(
        await session.scalars(
            select(ScheduleTemplate).where(
                ScheduleTemplate.tenant_id == tenant_id,
                ScheduleTemplate.staff_member_id == staff_member_id,
            )
        )
    )


async def replace_weekly_template(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    rows: list[dict[str, Any]],
    actor_user_id: UUID | None,
) -> None:
    existing = await list_templates(session, tenant_id=tenant_id, staff_member_id=staff_member_id)
    for tpl in existing:
        await session.delete(tpl)
    await session.flush()
    for spec in rows:
        session.add(
            ScheduleTemplate(
                tenant_id=tenant_id,
                staff_member_id=staff_member_id,
                weekday=int(spec["weekday"]),
                start_time=str(spec["start_time"]),
                end_time=str(spec["end_time"]),
                break_start=spec.get("break_start"),
                break_end=spec.get("break_end"),
            )
        )
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="schedule.template_updated",
        entity_type="staff_member",
        entity_id=staff_member_id,
        actor_user_id=actor_user_id,
    )
    await invalidate_slots_for_staff(tenant_id, staff_member_id)


async def add_exception(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    kind: str,
    start: datetime,
    end: datetime,
    note: str | None,
    actor_user_id: UUID | None,
) -> ScheduleException:
    exc = ScheduleException(
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        kind=kind,
        note=note,
    )
    session.add(exc)
    await session.flush()
    await session.execute(
        text("UPDATE schedule_exception SET during = tstzrange(:s, :e, '[)') WHERE id = :id"),
        {"s": start, "e": end, "id": str(exc.id)},
    )
    await invalidate_slots_for_staff(tenant_id, staff_member_id)
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="schedule.exception_added",
        entity_type="schedule_exception",
        entity_id=exc.id,
        actor_user_id=actor_user_id,
        details={"kind": kind},
    )
    return exc


async def ensure_default_schedule(
    session: AsyncSession, *, tenant_id: UUID, staff_member_id: UUID
) -> None:
    existing = await list_templates(session, tenant_id=tenant_id, staff_member_id=staff_member_id)
    if existing:
        return
    rows = []
    for weekday in range(5):
        rows.append(
            {
                "weekday": weekday,
                "start_time": "09:00",
                "end_time": "18:00",
            }
        )
    await replace_weekly_template(
        session,
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        rows=rows,
        actor_user_id=None,
    )
