from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PromoCode, Promotion


async def create_promotion(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    title: str,
    body: str | None,
    discount_percent: int | None,
    segment: str | None,
) -> Promotion:
    promo = Promotion(
        tenant_id=tenant_id,
        title=title,
        body=body,
        discount_percent=discount_percent,
        segment=segment,
        starts_at=datetime.now(UTC),
    )
    session.add(promo)
    await session.flush()
    return promo


async def validate_promo_code(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    code: str,
) -> PromoCode | None:
    row = await session.scalar(
        select(PromoCode).where(
            PromoCode.tenant_id == tenant_id,
            PromoCode.code == code.upper(),
        )
    )
    if row is None:
        return None
    if row.expires_at and row.expires_at < datetime.now(UTC):
        return None
    if row.max_uses is not None and row.uses >= row.max_uses:
        return None
    row.uses += 1
    return row
