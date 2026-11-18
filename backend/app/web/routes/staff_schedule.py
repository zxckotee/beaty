from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.exceptions import ValidationError
from app.domain.models import StaffMember
from app.domain.services.card_service import get_specialist
from app.domain.services.cell_service import get_default_branch
from app.domain.services.schedule_service import (
    WEEKDAY_LABELS,
    add_day_off,
    add_work_override,
    delete_exception,
    list_exceptions,
    list_templates,
    replace_weekly_template,
    weekly_template_payload,
)
from app.web.deps import WebContext, require_manager, require_staff, writable
from app.web.serializers import hhmm, local_date

router = APIRouter(prefix="/api/t/{tenant_public_id}", tags=["staff-schedule"])

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$"


class ScheduleDayIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    enabled: bool = True
    start_time: str = Field(default="09:00", pattern=HHMM)
    end_time: str = Field(default="18:00", pattern=HHMM)
    break_start: str | None = Field(default=None, pattern=HHMM)
    break_end: str | None = Field(default=None, pattern=HHMM)


class SchedulePutBody(BaseModel):
    days: list[ScheduleDayIn] = Field(min_length=1, max_length=7)


class DayOffBody(BaseModel):
    date: date
    note: str | None = Field(default=None, max_length=500)


class WorkOverrideBody(BaseModel):
    date: date
    start_time: str = Field(pattern=HHMM)
    end_time: str = Field(pattern=HHMM)
    break_start: str | None = Field(default=None, pattern=HHMM)
    break_end: str | None = Field(default=None, pattern=HHMM)
    note: str | None = Field(default=None, max_length=500)


def _exception_dict(exc, tz: ZoneInfo) -> dict[str, object]:
    during = exc.during
    assert during and during.lower and during.upper
    start_local = during.lower.astimezone(tz)
    end_local = during.upper.astimezone(tz)
    return {
        "id": str(exc.id),
        "kind": exc.kind,
        "date": local_date(during.lower, tz).isoformat(),
        "start_at": during.lower.isoformat(),
        "end_at": during.upper.isoformat(),
        "start": hhmm(start_local),
        "end": hhmm(end_local) if exc.kind == "work_override" else None,
        "note": exc.note,
    }


async def _ensure_staff(session: AsyncSession, ctx: WebContext, staff_id: UUID) -> StaffMember:
    return await get_specialist(session, ctx.tenant.id, staff_id)


@router.get("/manager/staff/{staff_member_id}/schedule")
async def get_staff_schedule(
    staff_member_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    await _ensure_staff(session, ctx, staff_member_id)
    templates = await list_templates(session, tenant_id=ctx.tenant.id, staff_member_id=staff_member_id)
    return {
        "staff_member_id": str(staff_member_id),
        "days": weekly_template_payload(templates),
        "weekday_labels": list(WEEKDAY_LABELS),
    }


@router.put("/manager/staff/{staff_member_id}/schedule")
async def put_staff_schedule(
    staff_member_id: UUID,
    body: SchedulePutBody,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    writable(ctx)
    await _ensure_staff(session, ctx, staff_member_id)
    rows = []
    for day in body.days:
        if not day.enabled:
            continue
        rows.append(
            {
                "weekday": day.weekday,
                "start_time": day.start_time,
                "end_time": day.end_time,
                "break_start": day.break_start,
                "break_end": day.break_end,
            }
        )
    await replace_weekly_template(
        session,
        tenant_id=ctx.tenant.id,
        staff_member_id=staff_member_id,
        rows=rows,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    templates = await list_templates(session, tenant_id=ctx.tenant.id, staff_member_id=staff_member_id)
    return {"staff_member_id": str(staff_member_id), "days": weekly_template_payload(templates)}


@router.get("/manager/staff/{staff_member_id}/exceptions")
async def get_staff_exceptions(
    staff_member_id: UUID,
    from_date: date = Query(alias="from"),
    days: int = Query(default=60, ge=1, le=180),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    branch = await get_default_branch(session, ctx.tenant)
    tz = ZoneInfo(branch.timezone or "Europe/Moscow")
    await _ensure_staff(session, ctx, staff_member_id)
    start = datetime.combine(from_date, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(from_date + timedelta(days=days), time.min, tzinfo=tz).astimezone(UTC)
    items = await list_exceptions(
        session,
        tenant_id=ctx.tenant.id,
        staff_member_id=staff_member_id,
        range_start=start,
        range_end=end,
    )
    return {"items": [_exception_dict(e, tz) for e in items]}


@router.post("/manager/staff/{staff_member_id}/exceptions/day-off", status_code=201)
async def post_day_off(
    staff_member_id: UUID,
    body: DayOffBody,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    writable(ctx)
    branch = await get_default_branch(session, ctx.tenant)
    tz = ZoneInfo(branch.timezone or "Europe/Moscow")
    await _ensure_staff(session, ctx, staff_member_id)
    exc = await add_day_off(
        session,
        tenant_id=ctx.tenant.id,
        staff_member_id=staff_member_id,
        day=body.date,
        tz=tz,
        note=body.note,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    return _exception_dict(exc, tz)


@router.post("/manager/staff/{staff_member_id}/exceptions/work-override", status_code=201)
async def post_work_override(
    staff_member_id: UUID,
    body: WorkOverrideBody,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    writable(ctx)
    branch = await get_default_branch(session, ctx.tenant)
    tz = ZoneInfo(branch.timezone or "Europe/Moscow")
    await _ensure_staff(session, ctx, staff_member_id)
    exc = await add_work_override(
        session,
        tenant_id=ctx.tenant.id,
        staff_member_id=staff_member_id,
        day=body.date,
        tz=tz,
        start_time=body.start_time,
        end_time=body.end_time,
        break_start=body.break_start,
        break_end=body.break_end,
        note=body.note,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    return _exception_dict(exc, tz)


@router.delete("/manager/staff/{staff_member_id}/exceptions/{exception_id}")
async def remove_exception(
    staff_member_id: UUID,
    exception_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    writable(ctx)
    await _ensure_staff(session, ctx, staff_member_id)
    await delete_exception(
        session,
        tenant_id=ctx.tenant.id,
        staff_member_id=staff_member_id,
        exception_id=exception_id,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    return {"status": "deleted"}


@router.get("/specialist/me/schedule")
async def get_my_schedule(
    ctx: WebContext = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    if ctx.staff is None:
        raise ValidationError("staff profile required")
    templates = await list_templates(session, tenant_id=ctx.tenant.id, staff_member_id=ctx.staff.id)
    return {"staff_member_id": str(ctx.staff.id), "days": weekly_template_payload(templates)}