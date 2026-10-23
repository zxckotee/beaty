from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Payment


async def record_payment(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    booking_id: UUID | None,
    amount_cents: int,
    tip_cents: int = 0,
    method: str = "cash",
    external_id: str | None = None,
) -> Payment:
    payment = Payment(
        tenant_id=tenant_id,
        booking_id=booking_id,
        amount_cents=amount_cents,
        tip_cents=tip_cents,
        method=method,
        external_id=external_id,
    )
    session.add(payment)
    await session.flush()
    return payment
