"""Phase 3: import from YCLIENTS, DIKIDI, Excel."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def import_from_csv(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    source: str,
    rows: list[dict],
) -> dict:
    return {"imported": 0, "source": source, "tenant_id": str(tenant_id), "rows": len(rows)}
