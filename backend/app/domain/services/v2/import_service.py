"""Phase 3: import from YCLIENTS, DIKIDI, Excel."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def import_from_csv(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    source: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"imported": 0, "source": source, "tenant_id": str(tenant_id), "rows": len(rows)}
