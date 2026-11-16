"""Manager-defined open time cells and the "which cells fit these services" search.

Shared by the Telegram bot and the web cabinet: neither one knows about the other.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import log_audit
from app.domain.cells import ServiceNeed, first_fit_start, free_segments, price_total, total_block_minutes
from app.domain.exceptions import (
    CellInUseError,
    CellOverlapError,
    NotFoundError,
    ValidationError,
)
from app.domain.models import (
    Booking,
    BookingItem,
    BookingStatus,
    Branch,
    ClientProfile,
    Service,
    SpecialistService,
    StaffMember,
    Tenant,
    TimeCell,
)
from app.domain.slots.types import TimeInterval

ACTIVE_STATUSES = (
    BookingStatus.HELD.value,
    BookingStatus.BOOKED.value,
    BookingStatus.CONFIRMED.value,
    BookingStatus.ARRIVED.value,
)
MIN_CELL_MINUTES = 5
MAX_CELL_MINUTES = 24 * 60
DEFAULT_DAY_START = "09:00"
DEFAULT_DAY_END = "21:00"


@dataclass
class CellBooking:
    booking_id: UUID
    status: str
    client_name: str
    client_phone: str | None
    service_names: list[str]
    start: datetime
    end: datetime
    total_price_cents: int
    comment: str | None


@dataclass
class CellView:
    cell: TimeCell
    staff: StaffMember
    free: list[TimeInterval]
    bookings: list[CellBooking] = field(default_factory=list)

    @property
    def total_minutes(self) -> int:
        return int((self.cell.ends_at - self.cell.starts_at).total_seconds() // 60)

    @property
    def free_minutes(self) -> int:
        return sum(int((seg.end - seg.start).total_seconds() // 60) for seg in self.free)


@dataclass
class CellOffer:
    cell: TimeCell
    staff: StaffMember
    needs: list[ServiceNeed]
    start_at: datetime
    end_at: datetime
    total_price_cents: int
    total_duration_minutes: int
    free_minutes: int


async def get_default_branch(session: AsyncSession, tenant: Tenant) -> Branch:
    raw = (tenant.rules or {}).get("default_branch_id")
    branch: Branch | None = None
    if raw:
        branch = await session.get(Branch, UUID(str(raw)))
    if branch is None:
        branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id).limit(1))
    if branch is None:
        raise NotFoundError("branch not configured")
    return branch


def local_day_bounds(day: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return start, end


def work_day_hours(tenant: Tenant) -> tuple[str, str]:
    rules = tenant.rules or {}
    return str(rules.get("work_day_start", DEFAULT_DAY_START)), str(rules.get("work_day_end", DEFAULT_DAY_END))


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValidationError("datetime must include a timezone")
    return dt.astimezone(UTC)


def _is_cell_overlap(exc: IntegrityError) -> bool:
    return "no_cell_overlap" in str(exc.orig) or "no_cell_overlap" in str(exc)


async def _validated_staff(session: AsyncSession, tenant_id: UUID, staff_member_id: UUID) -> StaffMember:
    staff = await session.get(StaffMember, staff_member_id)
    if staff is None or staff.tenant_id != tenant_id or not staff.is_active:
        raise NotFoundError("specialist not found")
    return staff


async def _validated_service_ids(session: AsyncSession, tenant_id: UUID, ids: Sequence[UUID]) -> list[str]:
    unique = list(dict.fromkeys(ids))
    if not unique:
        return []
    found = set(
        (
            await session.scalars(select(Service.id).where(Service.tenant_id == tenant_id, Service.id.in_(unique)))
        ).all()
    )
    if found != set(unique):
        raise NotFoundError("service not found")
    return [str(i) for i in unique]


def _check_range(starts_at: datetime, ends_at: datetime) -> tuple[datetime, datetime]:
    starts_at, ends_at = _aware(starts_at), _aware(ends_at)
    minutes = (ends_at - starts_at).total_seconds() / 60
    if minutes < MIN_CELL_MINUTES:
        raise ValidationError(f"cell must last at least {MIN_CELL_MINUTES} minutes")
    if minutes > MAX_CELL_MINUTES:
        raise ValidationError("cell cannot be longer than 24 hours")
    return starts_at, ends_at


async def active_cell_items(session: AsyncSession, cell_id: UUID) -> list[BookingItem]:
    rows = await session.scalars(
        select(BookingItem)
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(
            BookingItem.cell_id == cell_id,
            BookingItem.is_active.is_(True),
            Booking.status.in_(ACTIVE_STATUSES),
        )
    )
    return list(rows.all())


async def create_cell(
    session: AsyncSession,
    *,
    tenant: Tenant,
    staff_member_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    price_cents: int | None = None,
    title: str | None = None,
    description: str | None = None,
    allowed_service_ids: Sequence[UUID] = (),
    actor_user_id: UUID | None = None,
) -> TimeCell:
    starts_at, ends_at = _check_range(starts_at, ends_at)
    if ends_at <= datetime.now(UTC):
        raise ValidationError("cell is in the past")
    await _validated_staff(session, tenant.id, staff_member_id)
    branch = await get_default_branch(session, tenant)
    cell = TimeCell(
        tenant_id=tenant.id,
        branch_id=branch.id,
        staff_member_id=staff_member_id,
        starts_at=starts_at,
        ends_at=ends_at,
        price_cents=price_cents,
        title=(title or "").strip() or None,
        description=(description or "").strip() or None,
        allowed_service_ids=await _validated_service_ids(session, tenant.id, allowed_service_ids),
        created_by=actor_user_id,
    )
    session.add(cell)
    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_cell_overlap(exc):
            raise CellOverlapError("specialist already has a cell at this time") from exc
        raise
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="cell.created",
        entity_type="time_cell",
        entity_id=cell.id,
        actor_user_id=actor_user_id,
    )
    return cell


async def get_cell(session: AsyncSession, tenant_id: UUID, cell_id: UUID, *, for_update: bool = False) -> TimeCell:
    stmt = select(TimeCell).where(TimeCell.id == cell_id, TimeCell.tenant_id == tenant_id)
    if for_update:
        stmt = stmt.with_for_update()
    cell = await session.scalar(stmt)
    if cell is None:
        raise NotFoundError("cell not found")
    return cell


async def update_cell(
    session: AsyncSession,
    *,
    tenant: Tenant,
    cell_id: UUID,
    changes: dict[str, Any],
    actor_user_id: UUID | None = None,
) -> TimeCell:
    """Apply a partial update. Keys: staff_member_id, starts_at, ends_at, price_cents, title,
    description, allowed_service_ids. A cell with bookings keeps its specialist and must
    still cover every booked item."""
    cell = await get_cell(session, tenant.id, cell_id, for_update=True)
    starts_at, ends_at = cell.starts_at, cell.ends_at
    if "starts_at" in changes:
        starts_at = changes["starts_at"]
    if "ends_at" in changes:
        ends_at = changes["ends_at"]
    starts_at, ends_at = _check_range(starts_at, ends_at)

    items = await active_cell_items(session, cell.id)
    new_staff = changes.get("staff_member_id", cell.staff_member_id)
    if items:
        if new_staff != cell.staff_member_id:
            raise CellInUseError("cannot change specialist: cell has bookings")
        for item in items:
            rng: Range[datetime] = item.during
            if (rng.lower is not None and rng.lower < starts_at) or (rng.upper is not None and rng.upper > ends_at):
                raise CellInUseError("cell must still cover existing bookings")
    else:
        await _validated_staff(session, tenant.id, new_staff)

    cell.staff_member_id = new_staff
    cell.starts_at, cell.ends_at = starts_at, ends_at
    if "price_cents" in changes:
        cell.price_cents = changes["price_cents"]
    if "title" in changes:
        cell.title = (changes["title"] or "").strip() or None
    if "description" in changes:
        cell.description = (changes["description"] or "").strip() or None
    if "allowed_service_ids" in changes:
        cell.allowed_service_ids = await _validated_service_ids(
            session, tenant.id, changes["allowed_service_ids"] or []
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_cell_overlap(exc):
            raise CellOverlapError("specialist already has a cell at this time") from exc
        raise
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="cell.updated",
        entity_type="time_cell",
        entity_id=cell.id,
        actor_user_id=actor_user_id,
    )
    return cell


async def delete_cell(
    session: AsyncSession,
    *,
    tenant: Tenant,
    cell_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    cell = await get_cell(session, tenant.id, cell_id, for_update=True)
    if await active_cell_items(session, cell.id):
        raise CellInUseError("cell has active bookings")
    await session.delete(cell)
    await log_audit(
        session,
        tenant_id=tenant.id,
        action="cell.deleted",
        entity_type="time_cell",
        entity_id=cell_id,
        actor_user_id=actor_user_id,
    )
    await session.flush()


async def staff_busy(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    staff_ids: Sequence[UUID],
    range_start: datetime,
    range_end: datetime,
) -> dict[UUID, list[tuple[datetime, datetime]]]:
    """Blocked intervals per specialist. Expired unconfirmed holds do not count."""
    busy: dict[UUID, list[tuple[datetime, datetime]]] = {sid: [] for sid in staff_ids}
    if not staff_ids:
        return busy
    rows = await session.execute(
        select(
            BookingItem.staff_member_id,
            func.lower(BookingItem.blocked_during),
            func.upper(BookingItem.blocked_during),
        )
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(
            BookingItem.tenant_id == tenant_id,
            BookingItem.staff_member_id.in_(list(staff_ids)),
            BookingItem.is_active.is_(True),
            Booking.status.in_(ACTIVE_STATUSES),
            or_(
                Booking.status != BookingStatus.HELD.value,
                Booking.hold_expires_at.is_(None),
                Booking.hold_expires_at > func.now(),
            ),
            BookingItem.blocked_during.overlaps(Range(range_start, range_end, bounds="[)")),
        )
    )
    for sid, lo, hi in rows.all():
        if lo is not None and hi is not None:
            busy[sid].append((lo, hi))
    return busy


async def list_cells(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    range_start: datetime,
    range_end: datetime,
    staff_member_id: UUID | None = None,
    with_bookings: bool = True,
) -> list[CellView]:
    stmt = (
        select(TimeCell, StaffMember)
        .join(StaffMember, StaffMember.id == TimeCell.staff_member_id)
        .where(
            TimeCell.tenant_id == tenant_id,
            TimeCell.starts_at < range_end,
            TimeCell.ends_at > range_start,
        )
        .order_by(TimeCell.starts_at, TimeCell.ends_at)
    )
    if staff_member_id is not None:
        stmt = stmt.where(TimeCell.staff_member_id == staff_member_id)
    pairs = (await session.execute(stmt)).all()
    if not pairs:
        return []

    staff_ids = list({cell.staff_member_id for cell, _ in pairs})
    lo = min(cell.starts_at for cell, _ in pairs)
    hi = max(cell.ends_at for cell, _ in pairs)
    busy = await staff_busy(session, tenant_id=tenant_id, staff_ids=staff_ids, range_start=lo, range_end=hi)

    bookings_by_cell: dict[UUID, list[CellBooking]] = {}
    if with_bookings:
        bookings_by_cell = await _bookings_by_cell(session, [cell.id for cell, _ in pairs])

    return [
        CellView(
            cell=cell,
            staff=staff,
            free=free_segments(cell.starts_at, cell.ends_at, busy.get(cell.staff_member_id, [])),
            bookings=bookings_by_cell.get(cell.id, []),
        )
        for cell, staff in pairs
    ]


async def _bookings_by_cell(session: AsyncSession, cell_ids: Sequence[UUID]) -> dict[UUID, list[CellBooking]]:
    rows = (
        await session.execute(
            select(BookingItem, Booking, ClientProfile, Service)
            .join(Booking, Booking.id == BookingItem.booking_id)
            .join(ClientProfile, ClientProfile.id == Booking.client_profile_id)
            .join(Service, Service.id == BookingItem.service_id)
            .where(
                BookingItem.cell_id.in_(list(cell_ids)),
                BookingItem.is_active.is_(True),
                Booking.status.in_(ACTIVE_STATUSES),
            )
            .order_by(func.lower(BookingItem.during))
        )
    ).all()
    grouped: dict[tuple[UUID, UUID], CellBooking] = {}
    for item, booking, client, service in rows:
        if item.cell_id is None:
            continue
        key = (item.cell_id, booking.id)
        rng: Range[datetime] = item.during
        assert rng.lower is not None and rng.upper is not None
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = CellBooking(
                booking_id=booking.id,
                status=booking.status,
                client_name=client.name,
                client_phone=client.phone,
                service_names=[service.name],
                start=rng.lower,
                end=rng.upper,
                total_price_cents=booking.total_price_cents,
                comment=booking.comment,
            )
        else:
            existing.service_names.append(service.name)
            existing.end = max(existing.end, rng.upper)
    result: dict[UUID, list[CellBooking]] = {}
    for (cell_id, _), cb in grouped.items():
        result.setdefault(cell_id, []).append(cb)
    for lst in result.values():
        lst.sort(key=lambda b: b.start)
    return result


async def load_services(session: AsyncSession, tenant_id: UUID, service_ids: Sequence[UUID]) -> list[Service]:
    """Active services in the order requested; raises if any is missing."""
    ordered = list(dict.fromkeys(service_ids))
    if not ordered:
        raise ValidationError("select at least one service")
    rows = (
        await session.scalars(
            select(Service).where(
                Service.tenant_id == tenant_id,
                Service.id.in_(ordered),
                Service.is_active.is_(True),
            )
        )
    ).all()
    by_id = {s.id: s for s in rows}
    if len(by_id) != len(ordered):
        raise NotFoundError("service not found")
    return [by_id[i] for i in ordered]


async def eligible_staff_needs(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    services: Sequence[Service],
    staff_member_id: UUID | None = None,
) -> dict[UUID, list[ServiceNeed]]:
    """Specialists able to do ALL given services, with per-specialist price/duration overrides.

    A service nobody is linked to is treated as doable by every active specialist.
    """
    stmt = select(StaffMember).where(StaffMember.tenant_id == tenant_id, StaffMember.is_active.is_(True))
    if staff_member_id is not None:
        stmt = stmt.where(StaffMember.id == staff_member_id)
    staff_list = list((await session.scalars(stmt)).all())
    links = (
        await session.scalars(
            select(SpecialistService).where(
                SpecialistService.tenant_id == tenant_id,
                SpecialistService.service_id.in_([s.id for s in services]),
            )
        )
    ).all()
    link_map: dict[tuple[UUID, UUID], SpecialistService] = {(lk.staff_member_id, lk.service_id): lk for lk in links}
    linked_services = {lk.service_id for lk in links}

    result: dict[UUID, list[ServiceNeed]] = {}
    for staff in staff_list:
        needs: list[ServiceNeed] = []
        for svc in services:
            link = link_map.get((staff.id, svc.id))
            if link is None and svc.id in linked_services:
                break
            needs.append(
                ServiceNeed(
                    service_id=svc.id,
                    name=svc.name,
                    duration_minutes=(
                        link.duration_minutes if link and link.duration_minutes else svc.duration_minutes
                    ),
                    buffer_minutes=svc.buffer_minutes or 0,
                    price_cents=(link.price_cents if link and link.price_cents is not None else svc.price_cents),
                )
            )
        else:
            result[staff.id] = needs
    return result


def cell_allows(cell: TimeCell, service_ids: Sequence[UUID]) -> bool:
    allowed = {str(i) for i in (cell.allowed_service_ids or [])}
    return not allowed or all(str(i) in allowed for i in service_ids)


def lead_time_earliest(tenant: Tenant, now: datetime) -> datetime:
    hours = float((tenant.rules or {}).get("min_lead_time_hours", 2))
    return now + timedelta(hours=hours)


async def find_offers(
    session: AsyncSession,
    *,
    tenant: Tenant,
    service_ids: Sequence[UUID],
    range_start: datetime,
    range_end: datetime,
    staff_member_id: UUID | None = None,
    now: datetime | None = None,
) -> list[CellOffer]:
    """Cells (within the range) where every selected service fits for one specialist."""
    now = now or datetime.now(UTC)
    horizon = int((tenant.rules or {}).get("booking_horizon_days", 30))
    range_start = max(range_start, now)
    range_end = min(range_end, now + timedelta(days=horizon))
    if range_end <= range_start:
        return []

    services = await load_services(session, tenant.id, service_ids)
    needs_by_staff = await eligible_staff_needs(
        session, tenant_id=tenant.id, services=services, staff_member_id=staff_member_id
    )
    if not needs_by_staff:
        return []

    views = [
        v
        for v in await list_cells(
            session,
            tenant_id=tenant.id,
            range_start=range_start,
            range_end=range_end,
            with_bookings=False,
        )
        if v.cell.staff_member_id in needs_by_staff
    ]
    earliest = lead_time_earliest(tenant, now)
    ids = [s.id for s in services]
    offers: list[CellOffer] = []
    for view in views:
        cell = view.cell
        if not cell_allows(cell, ids):
            continue
        needs = needs_by_staff[cell.staff_member_id]
        block = total_block_minutes(needs)
        start = first_fit_start(view.free, block, earliest)
        if start is None:
            continue
        duration = sum(n.duration_minutes for n in needs)
        offers.append(
            CellOffer(
                cell=cell,
                staff=view.staff,
                needs=needs,
                start_at=start,
                end_at=start + timedelta(minutes=duration),
                total_price_cents=price_total(needs, cell.price_cents),
                total_duration_minutes=duration,
                free_minutes=view.free_minutes,
            )
        )
    offers.sort(key=lambda o: (o.start_at, o.staff.display_name))
    return offers
