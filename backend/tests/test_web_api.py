"""HTTP-level checks of the web cabinet: role permissions and the client booking flow."""

from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import StaffMember, UserAccount
from app.domain.services.card_service import ServiceLink, create_service, set_specialist_services
from app.domain.services.provisioning import create_tenant_for_owner
from app.domain.services.schedule_service import ensure_default_schedule
from app.web.main import app
from tests.conftest import random_telegram_id, tomorrow_at

TZ = ZoneInfo("Europe/Moscow")


class Salon:
    def __init__(self) -> None:
        self.public_id = ""
        self.owner_tg = random_telegram_id()
        self.specialist_tg = random_telegram_id()
        self.client_tg = random_telegram_id()
        self.specialist_id = ""
        self.service_id = ""


@pytest.fixture
async def salon(session: AsyncSession) -> Salon:
    s = Salon()
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=s.owner_tg, business_name="Web salon", owner_display_name="Owner"
    )
    svc = await create_service(session, tenant=tenant, name="Cut", price_cents=100000, duration_minutes=45)
    user = UserAccount(telegram_user_id=s.specialist_tg)
    session.add(user)
    await session.flush()
    spec = StaffMember(tenant_id=tenant.id, user_account_id=user.id, display_name="Max", roles=["specialist"])
    session.add(spec)
    await session.flush()
    await set_specialist_services(
        session, tenant=tenant, staff_member_id=spec.id, links=[ServiceLink(service_id=svc.id)]
    )
    await ensure_default_schedule(session, tenant_id=tenant.id, staff_member_id=spec.id)
    await session.commit()
    s.public_id = tenant.public_id
    s.specialist_id = str(spec.id)
    s.service_id = str(svc.id)
    return s


@pytest.fixture
async def client_factory(session: AsyncSession) -> AsyncIterator[type]:
    from app.core.db import engine

    created: list[httpx.AsyncClient] = []

    def make() -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        created.append(c)
        return c

    yield make  # type: ignore[misc]
    for c in created:
        await c.aclose()
    await engine.dispose()


async def login(c: httpx.AsyncClient, salon: Salon, tg: int) -> None:
    r = await c.post(f"/api/t/{salon.public_id}/auth/dev", json={"telegram_user_id": tg, "name": "Tester"})
    assert r.status_code == 200, r.text


def cell_body(salon: Salon, start: str = "10:00", end: str = "13:00") -> dict[str, object]:
    day = (tomorrow_at("12:00").astimezone(TZ)).date()
    return {"staff_member_id": salon.specialist_id, "date": day.isoformat(), "start": start, "end": end}


async def test_permissions_by_role(salon: Salon, client_factory) -> None:  # type: ignore[no-untyped-def]
    base = f"/api/t/{salon.public_id}"
    anon = client_factory()
    assert (await anon.get(f"{base}/me")).json()["authenticated"] is False
    assert (await anon.post(f"{base}/manager/cells", json=cell_body(salon))).status_code == 401

    client = client_factory()
    await login(client, salon, salon.client_tg)
    assert (await client.post(f"{base}/manager/cells", json=cell_body(salon))).status_code == 403

    specialist = client_factory()
    await login(specialist, salon, salon.specialist_tg)
    assert (await specialist.post(f"{base}/manager/cells", json=cell_body(salon))).status_code == 403

    owner = client_factory()
    await login(owner, salon, salon.owner_tg)
    created = await owner.post(f"{base}/manager/cells", json=cell_body(salon))
    assert created.status_code == 201, created.text
    cell_id = created.json()["id"]
    overlap = await owner.post(f"{base}/manager/cells", json=cell_body(salon, "12:00", "14:00"))
    assert overlap.status_code == 409

    assert (await specialist.delete(f"{base}/manager/cells/{cell_id}")).status_code == 403
    assert (await owner.delete(f"{base}/manager/cells/{cell_id}")).status_code == 200


async def test_client_books_on_schedule(salon: Salon, client_factory) -> None:  # type: ignore[no-untyped-def]
    base = f"/api/t/{salon.public_id}"
    client = client_factory()
    avail = await client.post(f"{base}/client/availability", json={"service_ids": [salon.service_id]})
    assert avail.status_code == 200, avail.text
    offers = [o for d in avail.json()["days"] for o in d["offers"]]
    assert offers, "expected schedule-based slots"
    offer = offers[0]

    body = {
        "staff_member_id": offer["staff_member_id"],
        "start_at": offer["start_at"],
        "service_ids": [salon.service_id],
        "name": "Anna",
        "phone": "+79001112233",
    }
    assert (await client.post(f"{base}/client/bookings", json=body)).status_code == 401

    await login(client, salon, salon.client_tg)
    booked = await client.post(f"{base}/client/bookings", json=body)
    assert booked.status_code == 201, booked.text
    mine = await client.get(f"{base}/client/bookings")
    assert len(mine.json()) == 1

    avail2 = await client.post(f"{base}/client/availability", json={"service_ids": [salon.service_id]})
    offers2 = [o for d in avail2.json()["days"] for o in d["offers"]]
    assert all(o["start_at"] != offer["start_at"] for o in offers2)


async def test_schedule_rules_flow(salon: Salon, client_factory) -> None:  # type: ignore[no-untyped-def]
    base = f"/api/t/{salon.public_id}"
    owner = client_factory()
    await login(owner, salon, salon.owner_tg)
    created = await owner.post(
        f"{base}/manager/schedule-rules",
        json={"name": "Дневная", "start_time": "10:00", "end_time": "19:00"},
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    applied = await owner.post(
        f"{base}/manager/schedule-rules/{rule_id}/apply",
        json={"weekdays": [0, 1, 2, 3, 4]},
    )
    assert applied.status_code == 200
    assert applied.json()["staff_updated"] >= 1
    sched = await owner.get(f"{base}/manager/staff/{salon.specialist_id}/schedule")
    mon = next(d for d in sched.json()["days"] if d["weekday"] == 0)
    assert mon["enabled"]
    assert mon["rule_id"] == rule_id
    assert mon["start_time"] == "10:00"


async def test_schedule_and_manual_booking(salon: Salon, client_factory) -> None:  # type: ignore[no-untyped-def]
    base = f"/api/t/{salon.public_id}"
    owner = client_factory()
    await login(owner, salon, salon.owner_tg)
    sched = await owner.get(f"{base}/manager/staff/{salon.specialist_id}/schedule")
    assert sched.status_code == 200
    days = sched.json()["days"]
    updated = [
        {
            "weekday": d["weekday"],
            "enabled": d["weekday"] < 5,
            "start_time": "10:00",
            "end_time": "17:00",
        }
        for d in days
    ]
    put_sched = await owner.put(
        f"{base}/manager/staff/{salon.specialist_id}/schedule",
        json={"days": updated},
    )
    assert put_sched.status_code == 200

    day = (tomorrow_at("12:00").astimezone(TZ)).date().isoformat()
    phone = "+79001234567"
    manual = await owner.post(
        f"{base}/manager/bookings/manual",
        json={
            "staff_member_id": salon.specialist_id,
            "date": day,
            "start_time": "11:00",
            "service_ids": [salon.service_id],
            "client_name": "Иван Тест",
            "client_phone": phone,
        },
    )
    assert manual.status_code == 201, manual.text
    pid1 = manual.json()["client_profile_id"]
    manual2 = await owner.post(
        f"{base}/manager/bookings/manual",
        json={
            "staff_member_id": salon.specialist_id,
            "date": day,
            "start_time": "12:00",
            "service_ids": [salon.service_id],
            "client_name": "Иван Другое",
            "client_phone": phone,
        },
    )
    assert manual2.status_code == 201, manual2.text
    assert manual2.json()["client_profile_id"] == pid1

    manual3 = await owner.post(
        f"{base}/manager/bookings/manual",
        json={
            "staff_member_id": salon.specialist_id,
            "date": day,
            "start_time": "14:00",
            "end_time": "15:30",
            "service_ids": [salon.service_id],
            "client_name": "Длинный слот",
            "client_phone": "+79009999999",
        },
    )
    assert manual3.status_code == 201, manual3.text

    bad = await owner.post(
        f"{base}/manager/bookings/manual",
        json={
            "staff_member_id": salon.specialist_id,
            "date": day,
            "start_time": "15:00",
            "end_time": "15:10",
            "service_ids": [salon.service_id],
            "client_name": "Слишком коротко",
            "client_phone": "+79008888888",
        },
    )
    assert bad.status_code == 409


async def test_staff_options(salon: Salon, client_factory) -> None:  # type: ignore[no-untyped-def]
    base = f"/api/t/{salon.public_id}"
    anon = client_factory()
    res = await anon.post(f"{base}/client/staff-options", json={"service_ids": [salon.service_id]})
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["staff_member_id"] == salon.specialist_id
    assert items[0]["timeline"]
