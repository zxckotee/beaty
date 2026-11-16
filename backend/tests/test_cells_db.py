"""Integration tests for time cells and booking inside a cell (need Postgres with migrations)."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.domain.exceptions import CellInUseError, CellOverlapError, DoesNotFitError, ValidationError
from app.domain.models import BookingItem, ClientProfile, Service, StaffMember, Tenant, UserAccount
from app.domain.services.booking_service import book_services_in_cell
from app.domain.services.card_service import ServiceLink, create_service, create_specialist
from app.domain.services.cell_service import create_cell, delete_cell, find_offers, update_cell
from app.domain.services.client_service import upsert_client_profile
from app.domain.services.provisioning import create_tenant_for_owner
from tests.conftest import random_telegram_id, tomorrow_at


async def make_salon(session: AsyncSession) -> tuple[Tenant, StaffMember, Service, Service]:
    tenant = await create_tenant_for_owner(
        session,
        owner_telegram_id=random_telegram_id(),
        business_name="Test salon",
        owner_display_name="Owner",
    )
    cut = await create_service(session, tenant=tenant, name="Cut", price_cents=100000, duration_minutes=45)
    beard = await create_service(session, tenant=tenant, name="Beard", price_cents=60000, duration_minutes=30)
    staff = await create_specialist(
        session,
        tenant=tenant,
        display_name="Max",
        service_links=[ServiceLink(service_id=cut.id), ServiceLink(service_id=beard.id)],
    )
    await session.commit()
    return tenant, staff, cut, beard


async def make_client(session: AsyncSession, tenant: Tenant) -> ClientProfile:
    user = UserAccount(telegram_user_id=random_telegram_id())
    session.add(user)
    await session.flush()
    profile = await upsert_client_profile(
        session, tenant_id=tenant.id, user_account_id=user.id, name="Anna", phone="+79001112233"
    )
    await session.commit()
    return profile


async def test_cell_overlap_rejected(session: AsyncSession) -> None:
    tenant, staff, _, _ = await make_salon(session)
    await create_cell(
        session, tenant=tenant, staff_member_id=staff.id, starts_at=tomorrow_at("10:00"), ends_at=tomorrow_at("13:00")
    )
    await session.commit()
    tenant_id, staff_id = tenant.id, staff.id
    with pytest.raises(CellOverlapError):
        await create_cell(
            session,
            tenant=tenant,
            staff_member_id=staff.id,
            starts_at=tomorrow_at("12:00"),
            ends_at=tomorrow_at("14:00"),
        )
    await session.rollback()
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    await create_cell(
        session, tenant=tenant, staff_member_id=staff_id, starts_at=tomorrow_at("13:00"), ends_at=tomorrow_at("14:00")
    )
    await session.commit()


async def test_cell_validation(session: AsyncSession) -> None:
    tenant, staff, _, _ = await make_salon(session)
    with pytest.raises(ValidationError):
        await create_cell(
            session,
            tenant=tenant,
            staff_member_id=staff.id,
            starts_at=tomorrow_at("13:00"),
            ends_at=tomorrow_at("10:00"),
        )
    with pytest.raises(ValidationError):
        await create_cell(
            session,
            tenant=tenant,
            staff_member_id=staff.id,
            starts_at=tomorrow_at("10:00", days=-2),
            ends_at=tomorrow_at("11:00", days=-2),
        )


async def test_booking_chains_services_and_leaves_remainder(session: AsyncSession) -> None:
    tenant, staff, cut, beard = await make_salon(session)
    client = await make_client(session, tenant)
    cell = await create_cell(
        session, tenant=tenant, staff_member_id=staff.id, starts_at=tomorrow_at("10:00"), ends_at=tomorrow_at("12:00")
    )
    await session.commit()

    booking = await book_services_in_cell(
        session, tenant=tenant, cell_id=cell.id, client_profile_id=client.id, service_ids=[cut.id, beard.id]
    )
    await session.commit()
    items = sorted(
        (await session.scalars(select(BookingItem).where(BookingItem.booking_id == booking.id))).all(),
        key=lambda i: i.during.lower,
    )
    assert len(items) == 2
    assert items[0].during.lower == tomorrow_at("10:00")
    assert items[1].during.lower == items[0].during.upper
    assert items[1].during.upper == tomorrow_at("11:15")

    now = tomorrow_at("00:00", days=0)
    offers = await find_offers(
        session,
        tenant=tenant,
        service_ids=[cut.id, beard.id],
        range_start=now,
        range_end=tomorrow_at("23:00", days=3),
        now=now,
    )
    assert offers == []
    offers = await find_offers(
        session, tenant=tenant, service_ids=[beard.id], range_start=now, range_end=tomorrow_at("23:00", days=3), now=now
    )
    assert [o.start_at for o in offers] == [tomorrow_at("11:15")]


async def test_booking_does_not_fit(session: AsyncSession) -> None:
    tenant, staff, cut, beard = await make_salon(session)
    client = await make_client(session, tenant)
    cell = await create_cell(
        session, tenant=tenant, staff_member_id=staff.id, starts_at=tomorrow_at("10:00"), ends_at=tomorrow_at("11:00")
    )
    await session.commit()
    with pytest.raises(DoesNotFitError):
        await book_services_in_cell(
            session, tenant=tenant, cell_id=cell.id, client_profile_id=client.id, service_ids=[cut.id, beard.id]
        )


async def test_booked_cell_cannot_be_deleted_or_shrunk(session: AsyncSession) -> None:
    tenant, staff, cut, _ = await make_salon(session)
    client = await make_client(session, tenant)
    cell = await create_cell(
        session, tenant=tenant, staff_member_id=staff.id, starts_at=tomorrow_at("10:00"), ends_at=tomorrow_at("12:00")
    )
    await session.commit()
    await book_services_in_cell(
        session, tenant=tenant, cell_id=cell.id, client_profile_id=client.id, service_ids=[cut.id]
    )
    await session.commit()
    tenant_id, cell_id = tenant.id, cell.id
    with pytest.raises(CellInUseError):
        await delete_cell(session, tenant=tenant, cell_id=cell_id)
    await session.rollback()
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    with pytest.raises(CellInUseError):
        await update_cell(session, tenant=tenant, cell_id=cell_id, changes={"ends_at": tomorrow_at("10:30")})


async def test_concurrent_bookings_do_not_overbook(session: AsyncSession) -> None:
    tenant, staff, cut, _ = await make_salon(session)
    clients = [await make_client(session, tenant) for _ in range(3)]
    cell = await create_cell(
        session, tenant=tenant, staff_member_id=staff.id, starts_at=tomorrow_at("10:00"), ends_at=tomorrow_at("11:30")
    )
    await session.commit()
    tenant_id, cell_id = tenant.id, cell.id

    engine = create_async_engine(session.bind.url.render_as_string(hide_password=False), poolclass=NullPool)  # type: ignore[union-attr]
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def attempt(client_id: UUID) -> bool:
        async with maker() as s:
            t = await s.get(Tenant, tenant_id)
            assert t is not None
            try:
                await book_services_in_cell(
                    s, tenant=t, cell_id=cell_id, client_profile_id=client_id, service_ids=[cut.id]
                )
                await s.commit()
                return True
            except DoesNotFitError:
                await s.rollback()
                return False

    results = await asyncio.gather(*(attempt(c.id) for c in clients))
    await engine.dispose()
    assert results.count(True) == 2
    assert results.count(False) == 1
