"""Specialist and service cards (profile, photo, which services a specialist performs)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import log_audit
from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.models import Service, SpecialistService, StaffMember, StaffRole, Tenant


@dataclass(frozen=True)
class ServiceLink:
    service_id: UUID
    price_cents: int | None = None
    duration_minutes: int | None = None


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _check_service_values(price_cents: int | None, duration_minutes: int | None, buffer_minutes: int | None) -> None:
    if price_cents is not None and price_cents < 0:
        raise ValidationError("price cannot be negative")
    if duration_minutes is not None and not 5 <= duration_minutes <= 720:
        raise ValidationError("duration must be between 5 and 720 minutes")
    if buffer_minutes is not None and not 0 <= buffer_minutes <= 240:
        raise ValidationError("buffer must be between 0 and 240 minutes")


async def get_service(session: AsyncSession, tenant_id: UUID, service_id: UUID) -> Service:
    service = await session.get(Service, service_id)
    if service is None or service.tenant_id != tenant_id:
        raise NotFoundError("service not found")
    return service


async def get_specialist(session: AsyncSession, tenant_id: UUID, staff_member_id: UUID) -> StaffMember:
    staff = await session.get(StaffMember, staff_member_id)
    if staff is None or staff.tenant_id != tenant_id:
        raise NotFoundError("specialist not found")
    return staff


async def create_service(
    session: AsyncSession,
    *,
    tenant: Tenant,
    name: str,
    price_cents: int,
    duration_minutes: int,
    buffer_minutes: int = 0,
    description: str | None = None,
    photo_url: str | None = None,
    category_id: UUID | None = None,
    actor_user_id: UUID | None = None,
) -> Service:
    if not name.strip():
        raise ValidationError("name is required")
    _check_service_values(price_cents, duration_minutes, buffer_minutes)
    service = Service(
        tenant_id=tenant.id,
        category_id=category_id,
        name=name.strip(),
        price_cents=price_cents,
        duration_minutes=duration_minutes,
        buffer_minutes=buffer_minutes,
        description=_clean(description),
        photo_url=_clean(photo_url),
    )
    session.add(service)
    await session.flush()
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="service.created",
        entity_type="service",
        entity_id=service.id,
        actor_user_id=actor_user_id,
    )
    return service


async def update_service(
    session: AsyncSession,
    *,
    tenant: Tenant,
    service_id: UUID,
    changes: dict[str, Any],
    actor_user_id: UUID | None = None,
) -> Service:
    service = await get_service(session, tenant.id, service_id)
    _check_service_values(changes.get("price_cents"), changes.get("duration_minutes"), changes.get("buffer_minutes"))
    if "name" in changes:
        if not str(changes["name"]).strip():
            raise ValidationError("name is required")
        service.name = str(changes["name"]).strip()
    for field_name in ("price_cents", "duration_minutes", "buffer_minutes", "is_active", "category_id"):
        if field_name in changes and changes[field_name] is not None:
            setattr(service, field_name, changes[field_name])
    for field_name in ("description", "photo_url"):
        if field_name in changes:
            setattr(service, field_name, _clean(changes[field_name]))
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="service.updated",
        entity_type="service",
        entity_id=service.id,
        actor_user_id=actor_user_id,
    )
    await session.flush()
    return service


async def create_specialist(
    session: AsyncSession,
    *,
    tenant: Tenant,
    display_name: str,
    specialization: str | None = None,
    bio: str | None = None,
    photo_url: str | None = None,
    service_links: Sequence[ServiceLink] = (),
    actor_user_id: UUID | None = None,
) -> StaffMember:
    if not display_name.strip():
        raise ValidationError("name is required")
    staff = StaffMember(
        tenant_id=tenant.id,
        display_name=display_name.strip(),
        roles=[StaffRole.SPECIALIST.value],
        specialization=_clean(specialization),
        bio=_clean(bio),
        photo_url=_clean(photo_url),
    )
    session.add(staff)
    await session.flush()
    if service_links:
        await set_specialist_services(session, tenant=tenant, staff_member_id=staff.id, links=service_links)
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="specialist.created",
        entity_type="staff_member",
        entity_id=staff.id,
        actor_user_id=actor_user_id,
    )
    return staff


async def update_specialist(
    session: AsyncSession,
    *,
    tenant: Tenant,
    staff_member_id: UUID,
    changes: dict[str, Any],
    actor_user_id: UUID | None = None,
) -> StaffMember:
    staff = await get_specialist(session, tenant.id, staff_member_id)
    if "display_name" in changes:
        if not str(changes["display_name"]).strip():
            raise ValidationError("name is required")
        staff.display_name = str(changes["display_name"]).strip()
    for field_name in ("specialization", "bio", "photo_url"):
        if field_name in changes:
            setattr(staff, field_name, _clean(changes[field_name]))
            if field_name == "photo_url":
                staff.photo_file_id = None
    if "is_active" in changes and changes["is_active"] is not None:
        staff.is_active = bool(changes["is_active"])
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="specialist.updated",
        entity_type="staff_member",
        entity_id=staff.id,
        actor_user_id=actor_user_id,
    )
    await session.flush()
    return staff


async def set_specialist_services(
    session: AsyncSession,
    *,
    tenant: Tenant,
    staff_member_id: UUID,
    links: Sequence[ServiceLink],
) -> None:
    """Replace the set of services a specialist performs (with optional price/duration overrides)."""
    await get_specialist(session, tenant.id, staff_member_id)
    wanted = {lk.service_id: lk for lk in links}
    if wanted:
        found = set(
            (
                await session.scalars(
                    select(Service.id).where(Service.tenant_id == tenant.id, Service.id.in_(list(wanted)))
                )
            ).all()
        )
        if found != set(wanted):
            raise NotFoundError("service not found")
    for lk in wanted.values():
        _check_service_values(lk.price_cents, lk.duration_minutes, None)

    existing = (
        await session.scalars(
            select(SpecialistService).where(
                SpecialistService.tenant_id == tenant.id,
                SpecialistService.staff_member_id == staff_member_id,
            )
        )
    ).all()
    seen: set[UUID] = set()
    for row in existing:
        if row.service_id in wanted:
            lk = wanted[row.service_id]
            row.price_cents = lk.price_cents
            row.duration_minutes = lk.duration_minutes
            seen.add(row.service_id)
        else:
            await session.delete(row)
    for service_id, lk in wanted.items():
        if service_id not in seen:
            session.add(
                SpecialistService(
                    tenant_id=tenant.id,
                    staff_member_id=staff_member_id,
                    service_id=service_id,
                    price_cents=lk.price_cents,
                    duration_minutes=lk.duration_minutes,
                )
            )
    await session.flush()


async def list_specialist_links(
    session: AsyncSession, *, tenant_id: UUID, staff_ids: Sequence[UUID] | None = None
) -> dict[UUID, list[SpecialistService]]:
    stmt = select(SpecialistService).where(SpecialistService.tenant_id == tenant_id)
    if staff_ids is not None:
        stmt = stmt.where(SpecialistService.staff_member_id.in_(list(staff_ids)))
    result: dict[UUID, list[SpecialistService]] = {}
    for row in (await session.scalars(stmt)).all():
        result.setdefault(row.staff_member_id, []).append(row)
    return result
