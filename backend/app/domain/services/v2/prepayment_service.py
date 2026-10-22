"""Phase 3: Telegram Payments + YooKassa integration (stub)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def create_deposit_invoice(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    booking_id: UUID,
    amount_cents: int,
) -> dict:
    return {
        "status": "not_implemented",
        "tenant_id": str(tenant_id),
        "booking_id": str(booking_id),
        "amount_cents": amount_cents,
        "provider": "yookassa",
    }
