"""Subject rights under 152-FZ: export and erasure for salon clients."""

from __future__ import annotations

from typing import Any
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Booking, ClientProfile, Review


async def export_client_data(
    session: AsyncSession, *, tenant_id: UUID, client_profile_id: UUID
) -> dict[str, Any]:
    profile = await session.get(ClientProfile, client_profile_id)
    if profile is None or profile.tenant_id != tenant_id:
        raise ValueError("client not found")
    bookings = (
        await session.scalars(
            select(Booking).where(Booking.tenant_id == tenant_id, Booking.client_profile_id == client_profile_id)
        )
    ).all()
    reviews = (
        await session.scalars(
            select(Review).where(Review.tenant_id == tenant_id, Review.client_profile_id == client_profile_id)
        )
    ).all()
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "name": profile.name,
            "phone": profile.phone,
            "consents": profile.consents or {},
            "photo_url": profile.photo_url,
        },
        "bookings_count": len(bookings),
        "booking_ids": [str(b.id) for b in bookings],
        "reviews_count": len(reviews),
    }


async def erase_client_personal_data(
    session: AsyncSession, *, tenant_id: UUID, client_profile_id: UUID
) -> None:
    profile = await session.get(ClientProfile, client_profile_id)
    if profile is None or profile.tenant_id != tenant_id:
        raise ValueError("client not found")
    profile.name = "Клиент"
    profile.phone = ""
    profile.photo_url = None
    profile.consents = {
        **(profile.consents or {}),
        "pd_consent": False,
        "marketing": False,
        "erased_at": datetime.now(UTC).isoformat(),
    }
    await session.flush()