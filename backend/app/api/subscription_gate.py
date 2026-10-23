from fastapi import HTTPException, status

from app.domain.models import Tenant

READ_ONLY_STATUSES = frozenset({"expired", "suspended", "cancelled"})


def assert_tenant_can_write(tenant: Tenant) -> None:
    """Soft degradation: expired subscription blocks mutations, reads still work."""
    if tenant.subscription_status in READ_ONLY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="subscription inactive; renew to change data",
        )
