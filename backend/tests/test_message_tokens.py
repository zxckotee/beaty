from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Booking,
    BookingItem,
    BookingStatus,
    Branch,
    Notification,
    NotificationStatus,
    NotificationType,
    StaffMember,
)
from app.domain.services.card_service import create_service
from app.domain.services.client_onboarding_service import ensure_user_account
from app.domain.services.client_service import register_client
from app.domain.services.message_tokens import (
    DEFAULT_BODIES,
    TOKEN_PREVIEW_CONTEXT,
    build_booking_context,
    render_template,
    staff_media_path,
)
from app.domain.services.notification_planner import cancel_booking_notifications, plan_booking_notifications
from app.domain.services.provisioning import create_tenant_for_owner
from tests.conftest import random_telegram_id


def test_render_template_substitutes_tokens():
    body = "Привет {staff}, {datetime}, {address}"
    text = render_template(body, TOKEN_PREVIEW_CONTEXT)
    assert "Анна" in text
    assert "15.03.2026" in text
    assert "Примерная" in text


def test_render_unknown_token_left_intact():
    text = render_template("{unknown}", TOKEN_PREVIEW_CONTEXT)
    assert text == "{unknown}"


def test_staff_media_path_prefers_url():
    assert staff_media_path(
        photo_url="https://cdn.example/a.jpg",
        photo_file_id="tg123",
        tenant_public_id="salon",
        staff_member_id=UUID("00000000-0000-4000-8000-000000000001"),
    ) == "https://cdn.example/a.jpg"


def test_staff_media_path_falls_back_to_telegram_cache():
    sid = UUID("00000000-0000-4000-8000-0000000000ab")
    assert staff_media_path(
        photo_url=None,
        photo_file_id="AgACAgIAAxk",
        tenant_public_id="demo-salon",
        staff_member_id=sid,
    ) == f"/media/tg/demo-salon/{sid}"


def test_default_cancelled_template_includes_visit():
    from app.domain.services.message_tokens import DEFAULT_BODIES

    text = render_template(DEFAULT_BODIES["booking_cancelled"], TOKEN_PREVIEW_CONTEXT)
    assert "15.03.2026 в 14:30" in text
    assert "Стрижка" in text
    assert "Анна" in text


def test_cancel_message_block():
    from dataclasses import replace

    ctx = replace(TOKEN_PREVIEW_CONTEXT, cancel_message="")
    assert render_template("{cancel_message_block}", ctx) == ""
    ctx2 = replace(TOKEN_PREVIEW_CONTEXT, cancel_message="Перенесём на завтра")
    assert "Перенесём" in render_template("{cancel_message_block}", ctx2)


@pytest.mark.asyncio
async def test_inactive_items_still_fill_cancel_message(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="N", owner_display_name="Мастер Анна"
    )
    branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
    staff = await session.scalar(select(StaffMember).where(StaffMember.tenant_id == tenant.id))
    assert branch is not None and staff is not None
    service = await create_service(session, tenant=tenant, name="Стрижка", price_cents=150000, duration_minutes=60)
    user = await ensure_user_account(session, random_telegram_id())
    profile = await register_client(
        session, tenant_id=tenant.id, user_account_id=user.id, name="Клиент", phone="79005554433"
    )
    booking = Booking(
        tenant_id=tenant.id,
        branch_id=branch.id,
        client_profile_id=profile.id,
        status=BookingStatus.CANCELLED.value,
    )
    session.add(booking)
    await session.flush()
    start = datetime(2026, 12, 1, 11, 0, tzinfo=UTC)
    session.add(
        BookingItem(
            tenant_id=tenant.id,
            booking_id=booking.id,
            staff_member_id=staff.id,
            service_id=service.id,
            during=Range(start, start + timedelta(hours=1), bounds="[)"),
            blocked_during=Range(start, start + timedelta(hours=1), bounds="[)"),
            price_cents=150000,
            duration_minutes=60,
            is_active=False,
        )
    )
    await session.flush()
    ctx = await build_booking_context(session, booking.id)
    assert ctx is not None
    text = render_template(DEFAULT_BODIES["booking_cancelled"], ctx)
    assert "Стрижка" in text
    assert "Мастер Анна" in text
    assert "01.12.2026" in text


@pytest.mark.asyncio
async def test_fast_cancel_keeps_unsent_confirmation(session: AsyncSession) -> None:
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=random_telegram_id(), business_name="N2", owner_display_name="O"
    )
    branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id))
    staff = await session.scalar(select(StaffMember).where(StaffMember.tenant_id == tenant.id))
    assert branch is not None and staff is not None
    user = await ensure_user_account(session, random_telegram_id())
    profile = await register_client(
        session, tenant_id=tenant.id, user_account_id=user.id, name="Клиент", phone="79006667788"
    )
    booking = Booking(
        tenant_id=tenant.id,
        branch_id=branch.id,
        client_profile_id=profile.id,
        status=BookingStatus.CANCELLED.value,
    )
    session.add(booking)
    await session.flush()
    await plan_booking_notifications(
        session,
        booking,
        start_at=datetime.now(UTC) + timedelta(days=2),
        tenant_rules={},
    )
    await cancel_booking_notifications(session, booking.id, keep_confirmation=True)
    rows = (
        await session.scalars(select(Notification).where(Notification.booking_id == booking.id))
    ).all()
    by_type = {row.notification_type: row.status for row in rows}
    assert by_type[NotificationType.BOOKING_CONFIRMED.value] == NotificationStatus.PENDING.value
    assert by_type[NotificationType.REMINDER_24H.value] == NotificationStatus.CANCELLED.value
    assert by_type[NotificationType.REMINDER_2H.value] == NotificationStatus.CANCELLED.value