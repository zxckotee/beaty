from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, BookingStatus, Review


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
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.tenant_id != tenant_id:
        raise ValueError("booking not found")
    if booking.status != BookingStatus.COMPLETED.value:
        raise ValueError("review only after completed visit")
    existing = await session.scalar(select(Review).where(Review.booking_id == booking_id))
    if existing:
        raise ValueError("review already exists")
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
