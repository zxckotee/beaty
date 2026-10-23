from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PlatformInvoice, Tenant


async def create_subscription_invoice(
    session: AsyncSession,
    *,
    tenant: Tenant,
    amount_cents: int,
    days_until_due: int = 7,
) -> PlatformInvoice:
    invoice = PlatformInvoice(
        tenant_id=tenant.id,
        amount_cents=amount_cents,
        due_at=datetime.now(UTC) + timedelta(days=days_until_due),
    )
    session.add(invoice)
    await session.flush()
    return invoice


async def mark_invoice_paid(session: AsyncSession, *, invoice_id: UUID) -> None:
    invoice = await session.get(PlatformInvoice, invoice_id)
    if invoice is None:
        return
    invoice.status = "paid"
    tenant = await session.get(Tenant, invoice.tenant_id)
    if tenant:
        tenant.subscription_status = "active"
