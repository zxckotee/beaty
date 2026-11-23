from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
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
    assign_rule_to_staff_members,
    assign_staff_schedule_rule,
    create_rule,
    delete_exception,
    delete_rule,
    effective_rule_id,
    get_rule,
    list_exceptions,
    list_rules,
    list_templates,
    rule_days_payload,
    set_tenant_default_schedule_rule,
    update_rule,
    weekly_template_payload,
)
from app.web.deps import WebContext, require_manager, require_staff, writable
from app.web.serializers import hhmm, local_date

router = APIRouter(prefix="/api/t/{tenant_public_id}", tags=["staff-schedule"])

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$"


class RuleDayIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    enabled: bool = True
    start_time: str = Field(default="09:00", pattern=HHMM)
    end_time: str = Field(default="18:00", pattern=HHMM)
    break_start: str | None = Field(default=None, pattern=HHMM)
    break_end: str | None = Field(default=None, pattern=HHMM)


class ScheduleRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    days: list[RuleDayIn] = Field(min_length=1, max_length=7)
    sort_order: int = 0


class ScheduleRulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    days: list[RuleDayIn] | None = Field(default=None, min_length=1, max_length=7)
    sort_order: int | None = None


class ApplyRuleBody(BaseModel):
    scope: Literal["enterprise_default", "staff"] = "staff"
    staff_member_ids: list[UUID] | None = None


class StaffScheduleAssignBody(BaseModel):
    """null = снять индивидуальное правило, действует правило салона по умолчанию."""
    schedule_rule_id: UUID | None = None


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
    start_d = local_date(during.lower, tz)
    end_d = local_date(during.upper, tz)
    return {
        "id": str(exc.id),
        "kind": exc.kind,
        "date": start_d.isoformat(),
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "start_at": during.lower.isoformat(),
        "end_at": during.upper.isoformat(),
        "start": hhmm(start_local, tz),
        "end": hhmm(end_local, tz) if exc.kind == "work_override" else None,
        "note": exc.note,
    }


async def _ensure_staff(session: AsyncSession, ctx: WebContext, staff_id: UUID) -> StaffMember:
    return await get_specialist(session, ctx.tenant.id, staff_id)


def _rule_dict(rule, *, is_default: bool = False) -> dict[str, object]:
    days = rule_days_payload(rule.days)
    summary = ", ".join(
        f"{d['label']} {d['start_time']}–{d['end_time']}"
        for d in days
        if d.get("enabled")
    )
    return {
        "id": str(rule.id),
        "name": rule.name,
        "days": days,
        "sort_order": rule.sort_order,
        "summary": summary or "Нет рабочих дней",
        "is_default": is_default,
    }


def _staff_schedule_meta(staff: StaffMember, ctx: WebContext) -> dict[str, object]:
    eff = effective_rule_id(staff=staff, tenant=ctx.tenant)
    return {
        "schedule_rule_id": str(staff.schedule_rule_id) if staff.schedule_rule_id else None,
        "uses_enterprise_default": staff.schedule_rule_id is None and bool(ctx.tenant.default_schedule_rule_id),
        "default_schedule_rule_id": (
            str(ctx.tenant.default_schedule_rule_id) if ctx.tenant.default_schedule_rule_id else None
        ),
        "effective_schedule_rule_id": str(eff) if eff else None,
    }


@router.get("/manager/schedule-rules")
async def get_schedule_rules(
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rules = await list_rules(session, tenant_id=ctx.tenant.id)
    default_id = ctx.tenant.default_schedule_rule_id
    return {
        "items": [_rule_dict(r, is_default=default_id == r.id) for r in rules],
        "default_schedule_rule_id": str(default_id) if default_id else None,
        "weekday_labels": list(WEEKDAY_LABELS),
    }


@router.post("/manager/schedule-rules", status_code=201)
async def post_schedule_rule(
    body: ScheduleRuleIn,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    writable(ctx)
    rule = await create_rule(
        session,
        tenant_id=ctx.tenant.id,
        name=body.name,
        days=[d.model_dump() for d in body.days],
        sort_order=body.sort_order,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    return _rule_dict(rule)


@router.patch("/manager/schedule-rules/{rule_id}")
async def patch_schedule_rule(
    rule_id: UUID,
    body: ScheduleRulePatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    writable(ctx)
    rule = await update_rule(
        session,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
        name=body.name,
        days=[d.model_dump() for d in body.days] if body.days else None,
        sort_order=body.sort_order,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    return _rule_dict(rule, is_default=ctx.tenant.default_schedule_rule_id == rule.id)


@router.delete("/manager/schedule-rules/{rule_id}")
async def remove_schedule_rule(
    rule_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    writable(ctx)
    await delete_rule(
        session,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    return {"status": "deleted"}


@router.post("/manager/schedule-rules/{rule_id}/apply")
async def apply_schedule_rule(
    rule_id: UUID,
    body: ApplyRuleBody,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    writable(ctx)
    await get_rule(session, tenant_id=ctx.tenant.id, rule_id=rule_id)
    if body.scope == "enterprise_default":
        count = await set_tenant_default_schedule_rule(
            session,
            tenant_id=ctx.tenant.id,
            rule_id=rule_id,
            actor_user_id=ctx.user.id if ctx.user else None,
        )
        await session.commit()
        return {"scope": "enterprise_default", "staff_updated": count}
    if not body.staff_member_ids:
        raise ValidationError("staff_member_ids required for scope=staff")
    count = await assign_rule_to_staff_members(
        session,
        tenant_id=ctx.tenant.id,
        rule_id=rule_id,
        staff_member_ids=body.staff_member_ids,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    return {"scope": "staff", "staff_updated": count}


@router.get("/manager/staff/{staff_member_id}/schedule")
async def get_staff_schedule(
    staff_member_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    staff = await _ensure_staff(session, ctx, staff_member_id)
    templates = await list_templates(session, tenant_id=ctx.tenant.id, staff_member_id=staff_member_id)
    rules = await list_rules(session, tenant_id=ctx.tenant.id)
    return {
        "staff_member_id": str(staff_member_id),
        **_staff_schedule_meta(staff, ctx),
        "days": weekly_template_payload(templates),
        "weekday_labels": list(WEEKDAY_LABELS),
        "rules": [
            _rule_dict(r, is_default=ctx.tenant.default_schedule_rule_id == r.id) for r in rules
        ],
    }


@router.put("/manager/staff/{staff_member_id}/schedule")
async def put_staff_schedule(
    staff_member_id: UUID,
    body: StaffScheduleAssignBody,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    writable(ctx)
    staff = await _ensure_staff(session, ctx, staff_member_id)
    if body.schedule_rule_id:
        await get_rule(session, tenant_id=ctx.tenant.id, rule_id=body.schedule_rule_id)
    await assign_staff_schedule_rule(
        session,
        tenant_id=ctx.tenant.id,
        staff_member_id=staff_member_id,
        schedule_rule_id=body.schedule_rule_id,
        actor_user_id=ctx.user.id if ctx.user else None,
    )
    await session.commit()
    await session.refresh(staff)
    templates = await list_templates(session, tenant_id=ctx.tenant.id, staff_member_id=staff_member_id)
    return {
        "staff_member_id": str(staff_member_id),
        **_staff_schedule_meta(staff, ctx),
        "days": weekly_template_payload(templates),
    }


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