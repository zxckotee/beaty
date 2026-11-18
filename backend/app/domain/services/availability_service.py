"""Client availability: free time = schedule minus bookings (not manager-published cells)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cells import ServiceNeed, price_total, total_block_minutes
from app.domain.models import (
    Booking,
    BookingItem,
    Branch,
    ClientProfile,
    ScheduleTemplate,
    Service,
    StaffMember,
    Tenant,
)
from app.domain.services.cell_service import (
    ACTIVE_STATUSES,
    CellBooking,
    eligible_staff_needs,
    lead_time_earliest,
    load_services,
)
from app.domain.services.schedule_service import ensure_default_schedule
from app.domain.services.slot_repository import (
    _busy_intervals,
    _exception_busy,
    _slot_rules_from_tenant,
    _work_intervals_for_day,
)
from app.domain.slots import SlotRules, TimeInterval, compute_slots, subtract_busy

ACTIVE_BOOKING_STATUSES = ACTIVE_STATUSES


@dataclass
class ScheduleOffer:
  """A bookable start time inside a computed free window on the specialist's schedule."""

  staff: StaffMember
  needs: list[ServiceNeed]
  start_at: datetime
  end_at: datetime
  free_window_start: datetime
  free_window_end: datetime
  total_price_cents: int
  total_duration_minutes: int


@dataclass
class ScheduleDayWindow:
  """One specialist's working slice on a calendar day (for the manager timeline)."""

  staff: StaffMember
  day: date
  work_start: datetime
  work_end: datetime
  free: list[TimeInterval]
  bookings: list[CellBooking]

  @property
  def total_minutes(self) -> int:
    return int((self.work_end - self.work_start).total_seconds() // 60)

  @property
  def free_minutes(self) -> int:
    return sum(int((seg.end - seg.start).total_seconds() // 60) for seg in self.free)


def _segment_containing(segments: Sequence[TimeInterval], moment: datetime) -> TimeInterval | None:
  for seg in segments:
    if seg.start <= moment and moment < seg.end:
      return seg
  return None


async def _load_templates(session: AsyncSession, tenant_id: UUID, staff_id: UUID) -> list[ScheduleTemplate]:
  return list(
    (
      await session.scalars(
        select(ScheduleTemplate).where(
          ScheduleTemplate.tenant_id == tenant_id,
          ScheduleTemplate.staff_member_id == staff_id,
        )
      )
    ).all()
  )


async def _work_for_staff_range(
  session: AsyncSession,
  *,
  tenant: Tenant,
  branch: Branch,
  staff_id: UUID,
  range_start: datetime,
  range_end: datetime,
) -> list[TimeInterval]:
  templates = await _load_templates(session, tenant.id, staff_id)
  if not templates:
    await ensure_default_schedule(session, tenant_id=tenant.id, staff_member_id=staff_id)
    templates = await _load_templates(session, tenant.id, staff_id)

  tz = ZoneInfo(branch.timezone or "Europe/Moscow")
  start_day = range_start.astimezone(tz).date()
  end_day = range_end.astimezone(tz).date()
  work: list[TimeInterval] = []
  day = start_day
  holidays = branch.holidays or []
  while day <= end_day:
    work.extend(_work_intervals_for_day(day, tz, templates, holidays))
    day += timedelta(days=1)
  return [w for w in work if w.end > range_start and w.start < range_end]


async def _busy_for_staff(
  session: AsyncSession,
  *,
  tenant_id: UUID,
  staff_id: UUID,
  range_start: datetime,
  range_end: datetime,
) -> list[TimeInterval]:
  busy = await _busy_intervals(
    session, tenant_id=tenant_id, staff_member_id=staff_id, range_start=range_start, range_end=range_end
  )
  busy.extend(
    await _exception_busy(
      session, tenant_id=tenant_id, staff_member_id=staff_id, range_start=range_start, range_end=range_end
    )
  )
  return busy


async def find_schedule_offers(
  session: AsyncSession,
  *,
  tenant: Tenant,
  branch: Branch,
  service_ids: Sequence[UUID],
  range_start: datetime,
  range_end: datetime,
  staff_member_id: UUID | None = None,
  now: datetime | None = None,
) -> list[ScheduleOffer]:
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

  rules: SlotRules = _slot_rules_from_tenant(tenant.rules or {})
  earliest = lead_time_earliest(tenant, now)
  offers: list[ScheduleOffer] = []

  for staff_id, needs in needs_by_staff.items():
    staff = await session.get(StaffMember, staff_id)
    if staff is None:
      continue
    block_minutes = total_block_minutes(needs)
    duration_minutes = sum(n.duration_minutes for n in needs)
    work = await _work_for_staff_range(
      session, tenant=tenant, branch=branch, staff_id=staff_id, range_start=range_start, range_end=range_end
    )
    if not work:
      continue
    busy = await _busy_for_staff(
      session, tenant_id=tenant.id, staff_id=staff_id, range_start=range_start, range_end=range_end
    )
    free = subtract_busy(work, busy)
    for slot in compute_slots(free, [], block_minutes, rules, now=now):
      if slot.start < earliest:
        continue
      seg = _segment_containing(free, slot.start)
      if seg is None:
        continue
      offers.append(
        ScheduleOffer(
          staff=staff,
          needs=needs,
          start_at=slot.start,
          end_at=slot.start + timedelta(minutes=duration_minutes),
          free_window_start=seg.start,
          free_window_end=seg.end,
          total_price_cents=price_total(needs),
          total_duration_minutes=duration_minutes,
        )
      )
  offers.sort(key=lambda o: (o.start_at, o.staff.display_name))
  return offers


async def staff_day_bookings(
  session: AsyncSession,
  *,
  tenant_id: UUID,
  staff_member_id: UUID,
  range_start: datetime,
  range_end: datetime,
) -> list[CellBooking]:
  rows = (
    await session.execute(
      select(BookingItem, Booking, ClientProfile, Service)
      .join(Booking, Booking.id == BookingItem.booking_id)
      .join(ClientProfile, ClientProfile.id == Booking.client_profile_id)
      .join(Service, Service.id == BookingItem.service_id)
      .where(
        BookingItem.tenant_id == tenant_id,
        BookingItem.staff_member_id == staff_member_id,
        BookingItem.is_active.is_(True),
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        BookingItem.during.overlaps(Range(range_start, range_end, bounds="[)")),
      )
      .order_by(func.lower(BookingItem.during))
    )
  ).all()
  grouped: dict[UUID, CellBooking] = {}
  for item, booking, client, service in rows:
    rng = item.during
    if rng.lower is None or rng.upper is None:
      continue
    existing = grouped.get(booking.id)
    if existing is None:
      grouped[booking.id] = CellBooking(
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
  result = list(grouped.values())
  result.sort(key=lambda b: b.start)
  return result


async def list_schedule_day_windows(
  session: AsyncSession,
  *,
  tenant: Tenant,
  branch: Branch,
  day: date,
  staff_member_id: UUID | None = None,
) -> list[ScheduleDayWindow]:
  tz = ZoneInfo(branch.timezone or "Europe/Moscow")
  day_start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
  day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)

  stmt = select(StaffMember).where(StaffMember.tenant_id == tenant.id, StaffMember.is_active.is_(True))
  if staff_member_id is not None:
    stmt = stmt.where(StaffMember.id == staff_member_id)
  staff_list = list((await session.scalars(stmt)).all())

  windows: list[ScheduleDayWindow] = []
  for staff in staff_list:
    work = await _work_for_staff_range(
      session, tenant=tenant, branch=branch, staff_id=staff.id, range_start=day_start, range_end=day_end
    )
    if not work:
      continue
    busy = await _busy_for_staff(
      session, tenant_id=tenant.id, staff_id=staff.id, range_start=day_start, range_end=day_end
    )
    free = subtract_busy(work, busy)
    w_start = min(w.start for w in work)
    w_end = max(w.end for w in work)
    bookings = await staff_day_bookings(
      session,
      tenant_id=tenant.id,
      staff_member_id=staff.id,
      range_start=day_start,
      range_end=day_end,
    )
    windows.append(
      ScheduleDayWindow(staff=staff, day=day, work_start=w_start, work_end=w_end, free=free, bookings=bookings)
    )
  windows.sort(key=lambda w: (w.work_start, w.staff.display_name))
  return windows