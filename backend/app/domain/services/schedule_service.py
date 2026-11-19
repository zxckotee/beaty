import json
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import log_audit
from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.models import ScheduleException, ScheduleRule, ScheduleTemplate, StaffMember, Tenant
from app.domain.services.slot_repository import WORK_OVERRIDE_KIND, invalidate_slots_for_staff

HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")
WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _parse_hhmm(value: str, field: str) -> time:
    text = (value or "").strip()
    if not HHMM_RE.match(text):
        raise ValidationError(f"{field}: invalid time")
    if text == "24:00":
        return time(23, 59, 59)
    return time.fromisoformat(text)


def validate_weekly_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen_weekdays: set[int] = set()
    for spec in rows:
        weekday = int(spec["weekday"])
        if not 0 <= weekday <= 6:
            raise ValidationError("weekday must be 0..6")
        if weekday in seen_weekdays:
            raise ValidationError("duplicate weekday in schedule")
        seen_weekdays.add(weekday)
        start = _parse_hhmm(str(spec["start_time"]), "start_time")
        end = _parse_hhmm(str(spec["end_time"]), "end_time")
        if end <= start:
            raise ValidationError("end_time must be after start_time")
        br_s = br_e = None
        if spec.get("break_start") or spec.get("break_end"):
            if not spec.get("break_start") or not spec.get("break_end"):
                raise ValidationError("break requires both break_start and break_end")
            br_s = _parse_hhmm(str(spec["break_start"]), "break_start")
            br_e = _parse_hhmm(str(spec["break_end"]), "break_end")
            if not (start <= br_s < br_e <= end):
                raise ValidationError("break must be inside work hours")
        cleaned.append(
            {
                "weekday": weekday,
                "start_time": start.strftime("%H:%M"),
                "end_time": "24:00" if end.hour == 23 and end.minute == 59 else end.strftime("%H:%M"),
                "break_start": br_s.strftime("%H:%M") if br_s else None,
                "break_end": br_e.strftime("%H:%M") if br_e else None,
            }
        )
    return cleaned


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


def weekly_template_payload(templates: list[ScheduleTemplate]) -> list[dict[str, object]]:
    by_day = {t.weekday: t for t in templates}
    out: list[dict[str, object]] = []
    for wd in range(7):
        tpl = by_day.get(wd)
        if tpl is None:
            out.append({"weekday": wd, "label": WEEKDAY_LABELS[wd], "enabled": False})
        else:
            out.append(
                {
                    "weekday": wd,
                    "label": WEEKDAY_LABELS[wd],
                    "enabled": True,
                    "start_time": tpl.start_time,
                    "end_time": tpl.end_time,
                    "break_start": tpl.break_start,
                    "break_end": tpl.break_end,
                }
            )
    return out


def rule_days_payload(days_spec: list[dict[str, Any]] | None) -> list[dict[str, object]]:
    """Seven weekday slots for API (enabled days carry hours)."""
    by_day: dict[int, dict[str, Any]] = {}
    for raw in days_spec or []:
        by_day[int(raw["weekday"])] = raw
    out: list[dict[str, object]] = []
    for wd in range(7):
        raw = by_day.get(wd)
        if not raw or not raw.get("enabled", True):
            out.append({"weekday": wd, "label": WEEKDAY_LABELS[wd], "enabled": False})
        else:
            out.append(
                {
                    "weekday": wd,
                    "label": WEEKDAY_LABELS[wd],
                    "enabled": True,
                    "start_time": raw.get("start_time", "09:00"),
                    "end_time": raw.get("end_time", "18:00"),
                    "break_start": raw.get("break_start"),
                    "break_end": raw.get("break_end"),
                }
            )
    return out


def _days_spec_to_rows(days_spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in days_spec:
        if not raw.get("enabled", True):
            continue
        rows.append(
            {
                "weekday": int(raw["weekday"]),
                "start_time": raw["start_time"],
                "end_time": raw["end_time"],
                "break_start": raw.get("break_start"),
                "break_end": raw.get("break_end"),
            }
        )
    return validate_weekly_rows(rows)


def _rows_to_days_spec(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enabled = {int(r["weekday"]): r for r in rows}
    out: list[dict[str, Any]] = []
    for wd in range(7):
        if wd in enabled:
            r = enabled[wd]
            out.append(
                {
                    "weekday": wd,
                    "enabled": True,
                    "start_time": r["start_time"],
                    "end_time": r["end_time"],
                    "break_start": r.get("break_start"),
                    "break_end": r.get("break_end"),
                }
            )
        else:
            out.append({"weekday": wd, "enabled": False})
    return out


async def _get_tenant(session: AsyncSession, tenant_id: UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("tenant not found")
    return tenant


def effective_rule_id(*, staff: StaffMember, tenant: Tenant) -> UUID | None:
    return staff.schedule_rule_id or tenant.default_schedule_rule_id


async def list_rules(session: AsyncSession, *, tenant_id: UUID) -> list[ScheduleRule]:
    rows = await session.scalars(
        select(ScheduleRule)
        .where(ScheduleRule.tenant_id == tenant_id)
        .order_by(ScheduleRule.sort_order, ScheduleRule.name)
    )
    return list(rows)


async def get_rule(session: AsyncSession, *, tenant_id: UUID, rule_id: UUID) -> ScheduleRule:
    rule = await session.get(ScheduleRule, rule_id)
    if rule is None or rule.tenant_id != tenant_id:
        raise NotFoundError("schedule rule not found")
    return rule


def _validate_rule_name(name: str) -> str:
    name_clean = (name or "").strip()
    if not name_clean:
        raise ValidationError("name required")
    if len(name_clean) > 120:
        raise ValidationError("name too long")
    return name_clean


async def create_rule(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    name: str,
    days: list[dict[str, Any]],
    sort_order: int = 0,
    actor_user_id: UUID | None,
) -> ScheduleRule:
    rows = _days_spec_to_rows(days)
    rule = ScheduleRule(
        tenant_id=tenant_id,
        name=_validate_rule_name(name),
        days=_rows_to_days_spec(rows),
        sort_order=sort_order,
    )
    session.add(rule)
    await session.flush()
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="schedule.rule_created",
        entity_type="schedule_rule",
        entity_id=rule.id,
        actor_user_id=actor_user_id,
    )
    return rule


async def update_rule(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    rule_id: UUID,
    name: str | None,
    days: list[dict[str, Any]] | None,
    sort_order: int | None = None,
    actor_user_id: UUID | None,
) -> ScheduleRule:
    rule = await get_rule(session, tenant_id=tenant_id, rule_id=rule_id)
    if name is not None:
        rule.name = _validate_rule_name(name)
    if days is not None:
        rule.days = _rows_to_days_spec(_days_spec_to_rows(days))
    if sort_order is not None:
        rule.sort_order = sort_order
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="schedule.rule_updated",
        entity_type="schedule_rule",
        entity_id=rule.id,
        actor_user_id=actor_user_id,
    )
    await resync_staff_for_rule(session, tenant_id=tenant_id, rule_id=rule.id, actor_user_id=actor_user_id)
    return rule


async def delete_rule(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    rule_id: UUID,
    actor_user_id: UUID | None,
) -> None:
    tenant = await _get_tenant(session, tenant_id)
    if tenant.default_schedule_rule_id == rule_id:
        tenant.default_schedule_rule_id = None
    rule = await get_rule(session, tenant_id=tenant_id, rule_id=rule_id)
    await session.delete(rule)
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="schedule.rule_deleted",
        entity_type="schedule_rule",
        entity_id=rule_id,
        actor_user_id=actor_user_id,
    )


async def materialize_rule_for_staff(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    rule_id: UUID,
    actor_user_id: UUID | None,
) -> None:
    rule = await get_rule(session, tenant_id=tenant_id, rule_id=rule_id)
    rows = _days_spec_to_rows(rule.days or [])
    await replace_weekly_template(
        session,
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        rows=rows,
        actor_user_id=actor_user_id,
    )


async def assign_staff_schedule_rule(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    schedule_rule_id: UUID | None,
    actor_user_id: UUID | None,
) -> None:
    staff = await session.get(StaffMember, staff_member_id)
    if staff is None or staff.tenant_id != tenant_id:
        raise NotFoundError("staff not found")
    tenant = await _get_tenant(session, tenant_id)
    staff.schedule_rule_id = schedule_rule_id
    effective = effective_rule_id(staff=staff, tenant=tenant)
    if effective:
        await materialize_rule_for_staff(
            session,
            tenant_id=tenant_id,
            staff_member_id=staff_member_id,
            rule_id=effective,
            actor_user_id=actor_user_id,
        )
    else:
        await replace_weekly_template(
            session,
            tenant_id=tenant_id,
            staff_member_id=staff_member_id,
            rows=[],
            actor_user_id=actor_user_id,
        )


async def set_tenant_default_schedule_rule(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    rule_id: UUID,
    actor_user_id: UUID | None,
) -> int:
    await get_rule(session, tenant_id=tenant_id, rule_id=rule_id)
    tenant = await _get_tenant(session, tenant_id)
    tenant.default_schedule_rule_id = rule_id
    count = await sync_staff_without_individual_rule(session, tenant_id=tenant_id, actor_user_id=actor_user_id)
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="schedule.rule_default_set",
        entity_type="schedule_rule",
        entity_id=rule_id,
        actor_user_id=actor_user_id,
        details={"staff_resynced": count},
    )
    return count


async def sync_staff_without_individual_rule(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None,
) -> int:
    tenant = await _get_tenant(session, tenant_id)
    if not tenant.default_schedule_rule_id:
        return 0
    staff_ids = list(
        await session.scalars(
            select(StaffMember.id).where(
                StaffMember.tenant_id == tenant_id,
                StaffMember.is_active.is_(True),
                StaffMember.schedule_rule_id.is_(None),
            )
        )
    )
    for staff_id in staff_ids:
        await materialize_rule_for_staff(
            session,
            tenant_id=tenant_id,
            staff_member_id=staff_id,
            rule_id=tenant.default_schedule_rule_id,
            actor_user_id=actor_user_id,
        )
    return len(staff_ids)


async def resync_staff_for_rule(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    rule_id: UUID,
    actor_user_id: UUID | None,
) -> None:
    tenant = await _get_tenant(session, tenant_id)
    staff_rows = (
        await session.scalars(
            select(StaffMember).where(
                StaffMember.tenant_id == tenant_id,
                StaffMember.is_active.is_(True),
            )
        )
    ).all()
    for staff in staff_rows:
        eff = effective_rule_id(staff=staff, tenant=tenant)
        if eff == rule_id:
            await materialize_rule_for_staff(
                session,
                tenant_id=tenant_id,
                staff_member_id=staff.id,
                rule_id=rule_id,
                actor_user_id=actor_user_id,
            )


async def assign_rule_to_staff_members(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    rule_id: UUID,
    staff_member_ids: list[UUID],
    actor_user_id: UUID | None,
) -> int:
    await get_rule(session, tenant_id=tenant_id, rule_id=rule_id)
    if not staff_member_ids:
        raise ValidationError("staff_member_ids required")
    count = 0
    for staff_id in staff_member_ids:
        await assign_staff_schedule_rule(
            session,
            tenant_id=tenant_id,
            staff_member_id=staff_id,
            schedule_rule_id=rule_id,
            actor_user_id=actor_user_id,
        )
        count += 1
    return count


async def replace_weekly_template(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    rows: list[dict[str, Any]],
    actor_user_id: UUID | None,
) -> None:
    rows = validate_weekly_rows(
        [
            {
                "weekday": r["weekday"],
                "start_time": r["start_time"],
                "end_time": r["end_time"],
                "break_start": r.get("break_start"),
                "break_end": r.get("break_end"),
            }
            for r in rows
        ]
    )
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


async def list_exceptions(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    range_start: datetime,
    range_end: datetime,
) -> list[ScheduleException]:
    rows = (
        await session.scalars(
            select(ScheduleException).where(
                ScheduleException.tenant_id == tenant_id,
                ScheduleException.staff_member_id == staff_member_id,
            )
        )
    ).all()
    result: list[ScheduleException] = []
    for exc in rows:
        during = exc.during
        if during is None or during.lower is None or during.upper is None:
            continue
        if during.lower < range_end and during.upper > range_start:
            result.append(exc)
    result.sort(key=lambda e: e.during.lower if e.during and e.during.lower else datetime.min.replace(tzinfo=UTC))
    return result


async def delete_exception(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    exception_id: UUID,
    actor_user_id: UUID | None,
) -> None:
    exc = await session.get(ScheduleException, exception_id)
    if exc is None or exc.tenant_id != tenant_id or exc.staff_member_id != staff_member_id:
        raise NotFoundError("exception not found")
    await session.delete(exc)
    await invalidate_slots_for_staff(tenant_id, staff_member_id)
    await log_audit(
        session,
        tenant_id=tenant_id,
        action="schedule.exception_removed",
        entity_type="schedule_exception",
        entity_id=exception_id,
        actor_user_id=actor_user_id,
    )


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
    if end <= start:
        raise ValidationError("end must be after start")
    exc = ScheduleException(
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        kind=kind,
        note=note,
        during=Range(start, end, bounds="[)"),
    )
    session.add(exc)
    await session.flush()
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


def _local_range_for_day(d: date, tz: ZoneInfo, start_t: time, end_t: time) -> tuple[datetime, datetime]:
    day_start = datetime.combine(d, start_t, tzinfo=tz).astimezone(UTC)
    if end_t.hour == 23 and end_t.minute == 59:
        day_end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    else:
        day_end = datetime.combine(d, end_t, tzinfo=tz).astimezone(UTC)
    return day_start, day_end


async def add_day_off(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    day: date,
    tz: ZoneInfo,
    note: str | None,
    actor_user_id: UUID | None,
) -> ScheduleException:
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return await add_exception(
        session,
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        kind="block",
        start=start,
        end=end,
        note=note or "day_off",
        actor_user_id=actor_user_id,
    )


async def add_work_override(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_member_id: UUID,
    day: date,
    tz: ZoneInfo,
    start_time: str,
    end_time: str,
    break_start: str | None,
    break_end: str | None,
    note: str | None,
    actor_user_id: UUID | None,
) -> ScheduleException:
    start_t = _parse_hhmm(start_time, "start_time")
    end_t = _parse_hhmm(end_time, "end_time")
    if end_t <= start_t:
        raise ValidationError("end_time must be after start_time")
    meta: dict[str, str] = {}
    if break_start or break_end:
        if not break_start or not break_end:
            raise ValidationError("break requires both break_start and break_end")
        br_s = _parse_hhmm(break_start, "break_start")
        br_e = _parse_hhmm(break_end, "break_end")
        if not (start_t <= br_s < br_e <= end_t):
            raise ValidationError("break must be inside work hours")
        meta = {"break_start": br_s.strftime("%H:%M"), "break_end": br_e.strftime("%H:%M")}
    note_text = json.dumps(meta, ensure_ascii=False) if meta else (note or "work_override")
    if note and not meta:
        note_text = note
    elif note and meta:
        meta["note"] = note
        note_text = json.dumps(meta, ensure_ascii=False)
    start, end = _local_range_for_day(day, tz, start_t, end_t)
    return await add_exception(
        session,
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        kind=WORK_OVERRIDE_KIND,
        start=start,
        end=end,
        note=note_text,
        actor_user_id=actor_user_id,
    )


async def ensure_default_schedule(
    session: AsyncSession, *, tenant_id: UUID, staff_member_id: UUID
) -> None:
    existing = await list_templates(session, tenant_id=tenant_id, staff_member_id=staff_member_id)
    if existing:
        return
    tenant = await _get_tenant(session, tenant_id)
    staff = await session.get(StaffMember, staff_member_id)
    if staff and tenant.default_schedule_rule_id:
        staff.schedule_rule_id = None
        await materialize_rule_for_staff(
            session,
            tenant_id=tenant_id,
            staff_member_id=staff_member_id,
            rule_id=tenant.default_schedule_rule_id,
            actor_user_id=None,
        )
        return
    rows = []
    for weekday in range(5):
        rows.append({"weekday": weekday, "start_time": "09:00", "end_time": "18:00"})
    await replace_weekly_template(
        session,
        tenant_id=tenant_id,
        staff_member_id=staff_member_id,
        rows=rows,
        actor_user_id=None,
    )