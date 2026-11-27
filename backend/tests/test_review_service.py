from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, BookingItem, BookingStatus, Branch, StaffMember
from app.domain.services.card_service import create_service
from app.domain.services.client_onboarding_service import ensure_user_account
from app.domain.services.client_service import register_client
from app.domain.services.provisioning import create_tenant_for_owner
from app.domain.services.review_service import create_review_for_client, list_reviewable_bookings
from tests.conftest import random_telegram_id


async def _add_visit_slot(
    session: AsyncSession,
    *,
    booking: Booking,
    staff_id,
    service_id,
    start: datetime,
    end: datetime,
) -> None:
    session.add(
        BookingItem(
            tenant_id=booking.tenant_id,
            booking_id=booking.id,
            staff_member_id=staff_id,
            service_id=service_id,
            during=Range(start, end, bounds="[)"),
            blocked_during=Range(start, end, bounds="[)"),
            price_cents=1000,
            duration_minutes=max(1, int((end - start).total_seconds() // 60)),
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_review_only_after_completed(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="R", owner_display_name="O"
    )
    branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
    assert branch is not None
    user = await ensure_user_account(session, random_telegram_id())
    profile = await register_client(
        session, tenant_id=tenant.id, user_account_id=user.id, name="C", phone="79001234567"
    )
    booking = Booking(
        tenant_id=tenant.id,
        branch_id=branch.id,
        client_profile_id=profile.id,
        status=BookingStatus.BOOKED.value,
    )
    session.add(booking)
    await session.flush()
    with pytest.raises(ValueError, match="completed"):
        await create_review_for_client(
            session,
            tenant_id=tenant.id,
            booking_id=booking.id,
            client_profile_id=profile.id,
            salon_rating=5,
            staff_rating=5,
            text=None,
        )


@pytest.mark.asyncio
async def test_review_duplicate(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="R2", owner_display_name="O"
    )
    branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
    assert branch is not None
    user = await ensure_user_account(session, random_telegram_id())
    profile = await register_client(
        session, tenant_id=tenant.id, user_account_id=user.id, name="C", phone="79007654321"
    )
    booking = Booking(
        tenant_id=tenant.id,
        branch_id=branch.id,
        client_profile_id=profile.id,
        status=BookingStatus.COMPLETED.value,
    )
    session.add(booking)
    await session.flush()
    await create_review_for_client(
        session,
        tenant_id=tenant.id,
        booking_id=booking.id,
        client_profile_id=profile.id,
        salon_rating=4,
        staff_rating=5,
        text="ok",
    )
    with pytest.raises(ValueError, match="already exists"):
        await create_review_for_client(
            session,
            tenant_id=tenant.id,
            booking_id=booking.id,
            client_profile_id=profile.id,
            salon_rating=3,
            staff_rating=3,
            text=None,
        )


@pytest.mark.asyncio
async def test_review_wrong_client(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="R3", owner_display_name="O"
    )
    branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
    user = await ensure_user_account(session, random_telegram_id())
    profile = await register_client(
        session, tenant_id=tenant.id, user_account_id=user.id, name="C", phone="79001112233"
    )
    other = await register_client(
        session, tenant_id=tenant.id, user_account_id=(await ensure_user_account(session, random_telegram_id())).id,
        name="D", phone="79004445566",
    )
    booking = Booking(
        tenant_id=tenant.id,
        branch_id=branch.id,  # type: ignore[union-attr]
        client_profile_id=profile.id,
        status=BookingStatus.COMPLETED.value,
    )
    session.add(booking)
    await session.flush()
    with pytest.raises(ValueError, match="not found"):
        await create_review_for_client(
            session,
            tenant_id=tenant.id,
            booking_id=booking.id,
            client_profile_id=other.id,
            salon_rating=5,
            staff_rating=5,
            text=None,
        )


@pytest.mark.asyncio
async def test_reviewable_past_completed(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="R4", owner_display_name="O"
    )
    branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
    staff = await session.scalar(select(StaffMember).where(StaffMember.tenant_id == tenant.id))
    assert branch is not None and staff is not None
    service = await create_service(session, tenant=tenant, name="Cut", price_cents=100000, duration_minutes=45)
    user = await ensure_user_account(session, random_telegram_id())
    profile = await register_client(
        session, tenant_id=tenant.id, user_account_id=user.id, name="C", phone="79009998877"
    )
    booking = Booking(
        tenant_id=tenant.id,
        branch_id=branch.id,
        client_profile_id=profile.id,
        status=BookingStatus.COMPLETED.value,
    )
    session.add(booking)
    await session.flush()
    past_end = datetime.now(UTC) - timedelta(hours=1)
    past_start = past_end - timedelta(minutes=45)
    await _add_visit_slot(
        session, booking=booking, staff_id=staff.id, service_id=service.id, start=past_start, end=past_end
    )
    reviewable = await list_reviewable_bookings(
        session, tenant_id=tenant.id, client_profile_id=profile.id
    )
    assert len(reviewable) == 1
    assert reviewable[0]["booking_id"] == booking.id


@pytest.mark.asyncio
async def test_reviewable_future_completed_when_marked_done(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="R5", owner_display_name="O"
    )
    branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
    staff = await session.scalar(select(StaffMember).where(StaffMember.tenant_id == tenant.id))
    assert branch is not None and staff is not None
    service = await create_service(session, tenant=tenant, name="Cut", price_cents=100000, duration_minutes=45)
    user = await ensure_user_account(session, random_telegram_id())
    profile = await register_client(
        session, tenant_id=tenant.id, user_account_id=user.id, name="C", phone="79008887766"
    )
    booking = Booking(
        tenant_id=tenant.id,
        branch_id=branch.id,
        client_profile_id=profile.id,
        status=BookingStatus.COMPLETED.value,
    )
    session.add(booking)
    await session.flush()
    future_start = datetime.now(UTC) + timedelta(days=1)
    future_end = future_start + timedelta(minutes=45)
    await _add_visit_slot(
        session, booking=booking, staff_id=staff.id, service_id=service.id, start=future_start, end=future_end
    )
    reviewable = await list_reviewable_bookings(
        session, tenant_id=tenant.id, client_profile_id=profile.id
    )
    assert len(reviewable) == 1
    assert reviewable[0]["booking_id"] == booking.id
    await create_review_for_client(
        session,
        tenant_id=tenant.id,
        booking_id=booking.id,
        client_profile_id=profile.id,
        salon_rating=5,
        staff_rating=5,
        text="early complete",
    )