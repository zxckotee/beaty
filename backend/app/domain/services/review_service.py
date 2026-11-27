from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, BookingItem, BookingStatus, ClientProfile, Review, Service


async def _booking_visit_end(session: AsyncSession, booking_id: UUID) -> datetime | None:
    return await session.scalar(
        select(func.max(func.upper(BookingItem.during))).where(BookingItem.booking_id == booking_id)
    )


async def _assert_visit_ended(session: AsyncSession, booking_id: UUID) -> None:
    ends_at = await _booking_visit_end(session, booking_id)
    if ends_at is None:
        return
    if ends_at > datetime.now(UTC):
        raise ValueError("review opens after visit end")


async def _assert_client_booking(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    booking_id: UUID,
    client_profile_id: UUID,
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant_id:
        raise ValueError("booking not found")
    if booking.client_profile_id != client_profile_id:
        raise ValueError("booking not found")
    if booking.status != BookingStatus.COMPLETED.value:
        raise ValueError("review only after completed visit")
    await _assert_visit_ended(session, booking_id)
    return booking


async def list_published_for_tenant(
    session: AsyncSession, *, tenant_id: UUID, limit: int = 50
) -> tuple[list[dict[str, Any]], float | None]:
    q = (
        select(Review, ClientProfile.name)
        .join(ClientProfile, ClientProfile.id == Review.client_profile_id)
        .where(
            Review.tenant_id == tenant_id,
            Review.moderation_status == "published",
        )
        .order_by(Review.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    items = [
        {
            "id": r.id,
            "salon_rating": r.salon_rating,
            "staff_rating": r.staff_rating,
            "text": r.text,
            "business_reply": r.business_reply,
            "client_name": name,
            "created_at": r.created_at,
        }
        for r, name in rows
    ]
    avg = await session.scalar(
        select(func.avg(Review.salon_rating)).where(
            Review.tenant_id == tenant_id,
            Review.moderation_status == "published",
            Review.salon_rating.is_not(None),
        )
    )
    return items, float(avg) if avg is not None else None


async def list_reviewable_bookings(
    session: AsyncSession, *, tenant_id: UUID, client_profile_id: UUID
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    reviewed_ids = select(Review.booking_id).where(Review.tenant_id == tenant_id)
    bookings = (
        await session.scalars(
            select(Booking)
            .where(
                Booking.tenant_id == tenant_id,
                Booking.client_profile_id == client_profile_id,
                Booking.status == BookingStatus.COMPLETED.value,
                Booking.id.not_in(reviewed_ids),
            )
            .order_by(Booking.created_at.desc())
        )
    ).all()
    now = datetime.now(UTC)
    out: list[dict[str, object]] = []
    pending_after: list[dict[str, object]] = []
    for b in bookings:
        starts_at = await session.scalar(
            select(func.min(func.lower(BookingItem.during))).where(BookingItem.booking_id == b.id)
        )
        ends_at = await _booking_visit_end(session, b.id)
        names = (
            await session.scalars(
                select(Service.name)
                .join(BookingItem, BookingItem.service_id == Service.id)
                .where(BookingItem.booking_id == b.id)
            )
        ).all()
        row = {"booking_id": b.id, "starts_at": starts_at, "service_names": list(names)}
        if ends_at is not None and ends_at > now:
            pending_after.append({**row, "review_opens_at": ends_at})
            continue
        out.append(row)
    return out, pending_after


async def create_review_for_client(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    booking_id: UUID,
    client_profile_id: UUID,
    staff_rating: int | None,
    salon_rating: int,
    text: str | None,
) -> Review:
    await _assert_client_booking(
        session, tenant_id=tenant_id, booking_id=booking_id, client_profile_id=client_profile_id
    )
    existing = await session.scalar(select(Review).where(Review.booking_id == booking_id))
    if existing:
        raise ValueError("review already exists")
    return await create_review(
        session,
        tenant_id=tenant_id,
        booking_id=booking_id,
        client_profile_id=client_profile_id,
        staff_rating=staff_rating or salon_rating,
        salon_rating=salon_rating,
        text=text,
    )


async def create_review(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    booking_id: UUID,
    client_profile_id: UUID,
    staff_rating: int,
    salon_rating: int,
    text: str | None,
) -> Review:
    await _assert_client_booking(
        session, tenant_id=tenant_id, booking_id=booking_id, client_profile_id=client_profile_id
    )
    review = Review(
        tenant_id=tenant_id,
        booking_id=booking_id,
        client_profile_id=client_profile_id,
        staff_rating=staff_rating,
        salon_rating=salon_rating,
        text=text,
    )
    session.add(review)
    await session.flush()
    return review


async def reply_to_review(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    review_id: UUID,
    reply: str,
) -> Review:
    review = await session.get(Review, review_id)
    if review is None or review.tenant_id != tenant_id:
        raise ValueError("review not found")
    review.business_reply = reply
    return review
