import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, BookingStatus, Branch
from app.domain.services.client_onboarding_service import ensure_user_account
from app.domain.services.client_service import register_client
from app.domain.services.provisioning import create_tenant_for_owner
from app.domain.services.review_service import create_review_for_client
from tests.conftest import random_telegram_id


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