import json
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Service, ServiceCategory


async def apply_catalog_template(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    template_name: str,
) -> None:
    path = Path(__file__).resolve().parent.parent / "catalog" / "templates" / f"{template_name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    categories: list[ServiceCategory] = []
    for idx, cat in enumerate(data.get("categories", [])):
        c = ServiceCategory(tenant_id=tenant_id, name=cat["name"], sort_order=idx)
        session.add(c)
        categories.append(c)
    await session.flush()
    for svc in data.get("services", []):
        cat_idx = svc.get("category", 0)
        session.add(
            Service(
                tenant_id=tenant_id,
                category_id=categories[cat_idx].id if categories else None,
                name=svc["name"],
                price_cents=svc.get("price_cents", 0),
                duration_minutes=svc.get("duration_minutes", 30),
                revisit_days=svc.get("revisit_days"),
            )
        )
