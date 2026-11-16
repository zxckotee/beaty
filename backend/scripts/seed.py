"""Demo tenant for local development."""

import asyncio
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db import SessionLocal
from app.domain.models import Branch, Service, SpecialistService, StaffMember, Tenant, TimeCell
from app.domain.services.catalog_service import apply_catalog_template
from app.domain.services.provisioning import attach_bot_token, create_tenant_for_owner
from app.domain.services.schedule_service import ensure_default_schedule

DEMO_SERVICES = [
    ("Стрижка + борода", 200000, 90, "Классическая стрижка и оформление бороды за один визит."),
    ("Укладка", 60000, 20, "Укладка стайлингом после стрижки или на событие."),
    ("Королевское бритьё", 120000, 40, "Бритьё опасной бритвой с горячим полотенцем."),
]
DEMO_STAFF = [
    ("Максим", "Барбер, стаж 6 лет", "Любит чёткие фейды и классические стрижки."),
    ("Алексей", "Топ-барбер", "Специалист по бородам и королевскому бритью."),
]
DEMO_CELLS = {
    "Иван": [("10:00", "13:00", None), ("14:00", "18:00", None)],
    "Максим": [("11:00", "15:30", 0), ("16:30", "20:00", 20000)],
    "Алексей": [("12:00", "14:00", None), ("15:00", "19:30", None)],
}


async def seed_web_demo(session, tenant: Tenant) -> None:  # type: ignore[no-untyped-def]
    """Extra demo data for the web cabinet; runs once per tenant."""
    if (tenant.rules or {}).get("web_demo_seeded"):
        return
    owner = await session.scalar(
        select(StaffMember).where(StaffMember.tenant_id == tenant.id).order_by(StaffMember.id).limit(1)
    )
    for name, price, minutes, description in DEMO_SERVICES:
        session.add(
            Service(
                tenant_id=tenant.id,
                name=name,
                price_cents=price,
                duration_minutes=minutes,
                description=description,
            )
        )
    for svc in (await session.scalars(select(Service).where(Service.tenant_id == tenant.id))).all():
        if svc.description is None:
            svc.description = "Аккуратно, быстро и с вниманием к деталям."
    staff_by_name: dict[str, StaffMember] = {}
    if owner:
        owner.specialization = owner.specialization or "Мастер-основатель"
        owner.bio = owner.bio or "Основатель студии, более 10 лет в профессии."
        staff_by_name[owner.display_name] = owner
    for name, spec, bio in DEMO_STAFF:
        member = StaffMember(
            tenant_id=tenant.id, display_name=name, roles=["specialist"], specialization=spec, bio=bio
        )
        session.add(member)
        staff_by_name[name] = member
    await session.flush()
    services = (await session.scalars(select(Service).where(Service.tenant_id == tenant.id))).all()
    linked = {
        (lk.staff_member_id, lk.service_id)
        for lk in (
            await session.scalars(select(SpecialistService).where(SpecialistService.tenant_id == tenant.id))
        ).all()
    }
    for member in staff_by_name.values():
        for svc in services:
            if (member.id, svc.id) not in linked:
                session.add(SpecialistService(tenant_id=tenant.id, staff_member_id=member.id, service_id=svc.id))

    branch = await session.scalar(select(Branch).where(Branch.tenant_id == tenant.id).limit(1))
    tz = ZoneInfo(branch.timezone if branch else "Europe/Moscow")
    today = datetime.now(tz).date()
    for offset in range(0, 5):
        day = today + timedelta(days=offset)
        for name, windows in DEMO_CELLS.items():
            member = staff_by_name.get(name)
            if member is None or branch is None:
                continue
            for start, end, adjust in windows:
                s_dt = datetime.combine(day, time.fromisoformat(start), tzinfo=tz).astimezone(UTC)
                e_dt = datetime.combine(day, time.fromisoformat(end), tzinfo=tz).astimezone(UTC)
                if e_dt <= datetime.now(UTC):
                    continue
                session.add(
                    TimeCell(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        staff_member_id=member.id,
                        starts_at=s_dt,
                        ends_at=e_dt,
                        price_cents=adjust,
                        description="Окно для записи" if adjust is None else "Вечернее окно, небольшая доплата",
                    )
                )
    tenant.rules = {**tenant.rules, "web_demo_seeded": True}
    await session.commit()


async def main() -> None:
    async with SessionLocal() as session:
        existing = await session.scalar(select(StaffMember).limit(1))
        if existing:
            print("Seed skipped: data already present")
            demo = await session.scalar(select(Tenant).where(Tenant.public_id == "demo"))
            if demo is not None:
                await seed_web_demo(session, demo)
            return
        tenant = await create_tenant_for_owner(
            session,
            owner_telegram_id=100001,
            business_name="Demo Barber",
            owner_display_name="Иван",
            public_id="demo",
        )
        await attach_bot_token(
            session,
            tenant,
            bot_token="0000000000:DEV_TOKEN_REPLACE_ME",
            bot_id=1,
            bot_username="demo_barber_bot",
        )
        await apply_catalog_template(session, tenant_id=tenant.id, template_name="barber")
        staff = await session.scalar(
            select(StaffMember).where(StaffMember.tenant_id == tenant.id)
        )
        if staff:
            await ensure_default_schedule(session, tenant_id=tenant.id, staff_member_id=staff.id)
            services = (
                await session.scalars(select(Service).where(Service.tenant_id == tenant.id))
            ).all()
            for svc in services:
                session.add(
                    SpecialistService(
                        tenant_id=tenant.id,
                        staff_member_id=staff.id,
                        service_id=svc.id,
                    )
                )
        await session.commit()
        await seed_web_demo(session, tenant)
        print(f"Seeded tenant public_id={tenant.public_id}")


if __name__ == "__main__":
    asyncio.run(main())
