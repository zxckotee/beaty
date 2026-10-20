"""Demo tenant for local development."""

import asyncio

from sqlalchemy import select

from app.core.db import SessionLocal
from app.domain.models import StaffMember
from app.domain.services.catalog_service import apply_catalog_template
from app.domain.services.provisioning import attach_bot_token, create_tenant_for_owner


async def main() -> None:
    async with SessionLocal() as session:
        existing = await session.scalar(select(StaffMember).limit(1))
        if existing:
            print("Seed skipped: data already present")
            return
        tenant = await create_tenant_for_owner(
            session,
            owner_telegram_id=100001,
            business_name="Demo Barber",
            owner_display_name="Иван",
        )
        await attach_bot_token(
            session,
            tenant,
            bot_token="0000000000:DEV_TOKEN_REPLACE_ME",
            bot_id=1,
            bot_username="demo_barber_bot",
        )
        await apply_catalog_template(session, tenant_id=tenant.id, template_name="barber")
        await session.commit()
        print(f"Seeded tenant public_id={tenant.public_id}")


if __name__ == "__main__":
    asyncio.run(main())
