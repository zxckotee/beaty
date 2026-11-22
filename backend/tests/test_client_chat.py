"""Client messenger: inbound classification and manager chat API."""

from collections.abc import AsyncIterator

import httpx
import pytest
from aiogram.types import Chat, PhotoSize, User, Voice
from aiogram.types import Message as TgMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ClientProfile, Tenant, UserAccount
from app.domain.services.client_chat_log import inbound_from_telegram_message, record_outbound
from app.domain.services.provisioning import create_tenant_for_owner
from app.web.main import app
from tests.conftest import random_telegram_id


def _msg(**kwargs) -> TgMessage:
    user = User(id=100, is_bot=False, first_name="A")
    chat = Chat(id=100, type="private")
    data = {"message_id": 1, "date": 1, "chat": chat, "from_user": user}
    data.update(kwargs)
    return TgMessage.model_validate(data)


def test_inbound_skips_commands() -> None:
    assert inbound_from_telegram_message(_msg(text="/start")) is None
    assert inbound_from_telegram_message(_msg(text="/book")) is None


def test_inbound_text_photo_voice() -> None:
    text = inbound_from_telegram_message(_msg(text="Привет"))
    assert text and text.kind == "text" and text.body == "Привет"

    photo = inbound_from_telegram_message(
        _msg(
            photo=[PhotoSize(file_id="s", file_unique_id="su", width=1, height=1, file_size=1)],
            caption="Фото",
        )
    )
    assert photo and photo.kind == "photo" and photo.body == "Фото"

    voice = inbound_from_telegram_message(
        _msg(voice=Voice(file_id="v", file_unique_id="vu", duration=3))
    )
    assert voice and voice.kind == "voice" and voice.meta.get("duration") == 3


@pytest.fixture
async def chat_salon(session: AsyncSession) -> dict[str, object]:
    owner_tg = random_telegram_id()
    client_tg = random_telegram_id()
    tenant = await create_tenant_for_owner(
        session, owner_telegram_id=owner_tg, business_name="Chat salon", owner_display_name="Owner"
    )
    user = UserAccount(telegram_user_id=client_tg)
    session.add(user)
    await session.flush()
    profile = ClientProfile(
        tenant_id=tenant.id,
        user_account_id=user.id,
        name="Client",
        phone="+79001112233",
    )
    session.add(profile)
    await session.commit()
    return {
        "public_id": tenant.public_id,
        "owner_tg": owner_tg,
        "client_id": profile.id,
        "tenant_id": tenant.id,
    }


@pytest.fixture
async def web_client() -> AsyncIterator[httpx.AsyncClient]:
    from app.core.db import engine

    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        yield c
    finally:
        await c.aclose()
        await engine.dispose()


async def test_chat_api_list_and_thread(
    session: AsyncSession,
    chat_salon: dict[str, object],
    web_client: httpx.AsyncClient,
) -> None:
    pid = str(chat_salon["public_id"])
    owner_tg = int(chat_salon["owner_tg"])  # type: ignore[arg-type]
    client_id = chat_salon["client_id"]

    login = await web_client.post(f"/api/t/{pid}/auth/dev", json={"telegram_user_id": owner_tg, "name": "Owner"})
    assert login.status_code == 200, login.text

    await record_outbound(
        session,
        tenant_id=chat_salon["tenant_id"],  # type: ignore[arg-type]
        client_profile_id=client_id,  # type: ignore[arg-type]
        kind="text",
        author="bot",
        body="Здравствуйте",
        telegram_file_id=None,
        telegram_file_unique_id=None,
        telegram_message_id=10,
    )
    await session.commit()

    listed = await web_client.get(f"/api/t/{pid}/manager/chat/clients")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert any(i["id"] == str(client_id) for i in items)

    thread = await web_client.get(f"/api/t/{pid}/manager/chat/clients/{client_id}/messages")
    assert thread.status_code == 200, thread.text
    messages = thread.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["body"] == "Здравствуйте"


async def test_send_requires_telegram(
    session: AsyncSession,
    chat_salon: dict[str, object],
) -> None:
    from app.domain.exceptions import ValidationError
    from app.domain.models import StaffMember
    from app.domain.services.client_chat_service import send_manager_message

    tenant = await session.get(Tenant, chat_salon["tenant_id"])  # type: ignore[arg-type]
    assert tenant is not None
    manual = ClientProfile(tenant_id=tenant.id, name="Manual", phone="+79990001122")
    session.add(manual)
    await session.flush()
    staff = await session.scalar(
        select(StaffMember).where(StaffMember.tenant_id == tenant.id).limit(1)
    )
    assert staff is not None
    await session.commit()

    with pytest.raises(ValidationError, match="Telegram"):
        await send_manager_message(
            session,
            tenant,
            manual.id,
            staff_member_id=staff.id,
            text="hi",
        )