from __future__ import annotations

from datetime import date as Date
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.exceptions import ValidationError
from app.domain.models import Service, ServiceCategory, StaffMember
from app.domain.services.card_service import (
    ServiceLink,
    create_service,
    create_specialist,
    get_service,
    get_specialist,
    list_specialist_links,
    set_specialist_services,
    update_service,
    update_specialist,
)
from app.domain.services.cell_service import (
    create_cell,
    delete_cell,
    get_cell,
    get_default_branch,
    list_cells,
    update_cell,
)
from app.web.deps import WebContext, require_manager, writable
from app.web.serializers import cell_dict, parse_local, service_card, staff_card
from app.web.uploads import save_image

router = APIRouter(prefix="/api/t/{tenant_public_id}/manager", tags=["manager"])

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$"


class CellCreate(BaseModel):
    staff_member_id: UUID
    date: Date
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    price_cents: int | None = Field(default=None, ge=-10_000_000, le=10_000_000)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    allowed_service_ids: list[UUID] = Field(default_factory=list)


class CellPatch(BaseModel):
    staff_member_id: UUID | None = None
    date: Date | None = None
    start: str | None = Field(default=None, pattern=HHMM)
    end: str | None = Field(default=None, pattern=HHMM)
    price_cents: int | None = Field(default=None, ge=-10_000_000, le=10_000_000)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    allowed_service_ids: list[UUID] | None = None


async def _tz(session: AsyncSession, ctx: WebContext) -> ZoneInfo:
    return ZoneInfo((await get_default_branch(session, ctx.tenant)).timezone)


async def _cell_response(session: AsyncSession, ctx: WebContext, cell_id: UUID) -> dict[str, object]:
    cell = await get_cell(session, ctx.tenant.id, cell_id)
    tz = await _tz(session, ctx)
    start, end = cell.starts_at, cell.ends_at
    views = await list_cells(session, tenant_id=ctx.tenant.id, range_start=start, range_end=end)
    view = next(v for v in views if v.cell.id == cell.id)
    return cell_dict(view, tz, ctx.tenant.public_id)


@router.post("/cells", status_code=201)
async def post_cell(
    body: CellCreate,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    tz = await _tz(session, ctx)
    assert ctx.user is not None
    cell = await create_cell(
        session,
        tenant=tenant,
        staff_member_id=body.staff_member_id,
        starts_at=parse_local(body.date, body.start, tz),
        ends_at=parse_local(body.date, body.end, tz),
        price_cents=body.price_cents,
        title=body.title,
        description=body.description,
        allowed_service_ids=body.allowed_service_ids,
        actor_user_id=ctx.user.id,
    )
    await session.commit()
    return await _cell_response(session, ctx, cell.id)


@router.patch("/cells/{cell_id}")
async def patch_cell(
    cell_id: UUID,
    body: CellPatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    tz = await _tz(session, ctx)
    assert ctx.user is not None
    fields = body.model_fields_set
    changes: dict[str, object] = {}
    if "staff_member_id" in fields and body.staff_member_id is not None:
        changes["staff_member_id"] = body.staff_member_id
    if {"date", "start", "end"} & fields:
        current = await get_cell(session, tenant.id, cell_id)
        day = body.date or current.starts_at.astimezone(tz).date()
        start = body.start or current.starts_at.astimezone(tz).strftime("%H:%M")
        end = body.end or current.ends_at.astimezone(tz).strftime("%H:%M")
        changes["starts_at"] = parse_local(day, start, tz)
        changes["ends_at"] = parse_local(day, end, tz)
    for name in ("price_cents", "title", "description"):
        if name in fields:
            changes[name] = getattr(body, name)
    if "allowed_service_ids" in fields:
        changes["allowed_service_ids"] = body.allowed_service_ids or []
    await update_cell(session, tenant=tenant, cell_id=cell_id, changes=changes, actor_user_id=ctx.user.id)
    await session.commit()
    return await _cell_response(session, ctx, cell_id)


@router.delete("/cells/{cell_id}")
async def remove_cell(
    cell_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    assert ctx.user is not None
    await delete_cell(session, tenant=tenant, cell_id=cell_id, actor_user_id=ctx.user.id)
    await session.commit()
    return {"status": "deleted"}


class ServiceLinkBody(BaseModel):
    service_id: UUID
    price_cents: int | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=5, le=720)


class StaffCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    specialization: str | None = Field(default=None, max_length=512)
    bio: str | None = Field(default=None, max_length=4000)
    photo_url: str | None = Field(default=None, max_length=512)
    services: list[ServiceLinkBody] = Field(default_factory=list)


class StaffPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    specialization: str | None = Field(default=None, max_length=512)
    bio: str | None = Field(default=None, max_length=4000)
    photo_url: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None
    services: list[ServiceLinkBody] | None = None


def _links(items: list[ServiceLinkBody]) -> list[ServiceLink]:
    return [ServiceLink(i.service_id, i.price_cents, i.duration_minutes) for i in items]


async def _staff_with_services(
    session: AsyncSession, ctx: WebContext, staff_list: list[StaffMember]
) -> list[dict[str, object]]:
    links = await list_specialist_links(session, tenant_id=ctx.tenant.id, staff_ids=[s.id for s in staff_list])
    result: list[dict[str, object]] = []
    for staff in staff_list:
        card = staff_card(staff, ctx.tenant.public_id)
        card["roles"] = list(staff.roles or [])
        card["services"] = [
            {
                "service_id": str(lk.service_id),
                "price_cents": lk.price_cents,
                "duration_minutes": lk.duration_minutes,
            }
            for lk in links.get(staff.id, [])
        ]
        result.append(card)
    return result


@router.get("/staff")
async def list_staff(
    ctx: WebContext = Depends(require_manager), session: AsyncSession = Depends(get_session)
) -> list[dict[str, object]]:
    rows = list(
        (
            await session.scalars(
                select(StaffMember)
                .where(StaffMember.tenant_id == ctx.tenant.id)
                .order_by(StaffMember.is_active.desc(), StaffMember.display_name)
            )
        ).all()
    )
    return await _staff_with_services(session, ctx, rows)


@router.post("/staff", status_code=201)
async def post_staff(
    body: StaffCreate,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    assert ctx.user is not None
    staff = await create_specialist(
        session,
        tenant=tenant,
        display_name=body.display_name,
        specialization=body.specialization,
        bio=body.bio,
        photo_url=body.photo_url,
        service_links=_links(body.services),
        actor_user_id=ctx.user.id,
    )
    await session.commit()
    return (await _staff_with_services(session, ctx, [staff]))[0]


@router.patch("/staff/{staff_member_id}")
async def patch_staff(
    staff_member_id: UUID,
    body: StaffPatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    assert ctx.user is not None
    fields = body.model_fields_set
    keys = ("display_name", "specialization", "bio", "photo_url", "is_active")
    changes = {k: getattr(body, k) for k in keys if k in fields}
    staff = await update_specialist(
        session, tenant=tenant, staff_member_id=staff_member_id, changes=changes, actor_user_id=ctx.user.id
    )
    if "services" in fields and body.services is not None:
        await set_specialist_services(
            session, tenant=tenant, staff_member_id=staff_member_id, links=_links(body.services)
        )
    await session.commit()
    return (await _staff_with_services(session, ctx, [staff]))[0]


@router.post("/staff/{staff_member_id}/photo")
async def upload_staff_photo(
    staff_member_id: UUID,
    file: UploadFile = File(...),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    await get_specialist(session, tenant.id, staff_member_id)
    url = await save_image(file, tenant.id)
    staff = await update_specialist(
        session, tenant=tenant, staff_member_id=staff_member_id, changes={"photo_url": url}
    )
    await session.commit()
    return (await _staff_with_services(session, ctx, [staff]))[0]


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price_cents: int = Field(ge=0, le=100_000_000)
    duration_minutes: int = Field(ge=5, le=720)
    buffer_minutes: int = Field(default=0, ge=0, le=240)
    description: str | None = Field(default=None, max_length=4000)
    photo_url: str | None = Field(default=None, max_length=512)
    category_id: UUID | None = None


class ServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    price_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    description: str | None = Field(default=None, max_length=4000)
    photo_url: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None


async def _category_names(session: AsyncSession, tenant_id: UUID) -> dict[UUID, str]:
    rows = (await session.scalars(select(ServiceCategory).where(ServiceCategory.tenant_id == tenant_id))).all()
    return {c.id: c.name for c in rows}


@router.get("/services")
async def list_services(
    ctx: WebContext = Depends(require_manager), session: AsyncSession = Depends(get_session)
) -> list[dict[str, object]]:
    categories = await _category_names(session, ctx.tenant.id)
    rows = (
        await session.scalars(
            select(Service)
            .where(Service.tenant_id == ctx.tenant.id)
            .order_by(Service.is_active.desc(), Service.name)
        )
    ).all()
    return [service_card(s, categories.get(s.category_id) if s.category_id else None) for s in rows]


@router.post("/services", status_code=201)
async def post_service(
    body: ServiceCreate,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    assert ctx.user is not None
    service = await create_service(
        session,
        tenant=tenant,
        name=body.name,
        price_cents=body.price_cents,
        duration_minutes=body.duration_minutes,
        buffer_minutes=body.buffer_minutes,
        description=body.description,
        photo_url=body.photo_url,
        category_id=body.category_id,
        actor_user_id=ctx.user.id,
    )
    await session.commit()
    return service_card(service)


@router.patch("/services/{service_id}")
async def patch_service(
    service_id: UUID,
    body: ServicePatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    assert ctx.user is not None
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    if not changes:
        raise ValidationError("nothing to update")
    service = await update_service(
        session, tenant=tenant, service_id=service_id, changes=changes, actor_user_id=ctx.user.id
    )
    await session.commit()
    return service_card(service)


@router.post("/services/{service_id}/photo")
async def upload_service_photo(
    service_id: UUID,
    file: UploadFile = File(...),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    await get_service(session, tenant.id, service_id)
    url = await save_image(file, tenant.id)
    service = await update_service(session, tenant=tenant, service_id=service_id, changes={"photo_url": url})
    await session.commit()
    return service_card(service)
