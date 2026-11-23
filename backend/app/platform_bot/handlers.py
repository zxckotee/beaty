from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.utils.token import TokenValidationError
from sqlalchemy import select

from app.bot.common.max_owner_guide import (
    max_owner_guide_tail,
    platform_bot_help_text,
    send_max_onboarding_full,
    send_max_onboarding_short,
)
from app.bot.factory import create_bot
from app.bot.telegram_format import bot_mention_html
from app.bot.telegram_ui_sync import sync_tenant_bot_telegram_ui
from app.core.db import SessionLocal
from app.domain.exceptions import BotAlreadyLinkedError
from app.domain.services.provisioning import (
    attach_bot_token,
    attach_max_bot_token,
    create_tenant_for_owner,
    find_owned_tenant_for_telegram_user,
    find_tenant_by_bot_id,
    find_tenant_by_max_bot_id,
)
from app.max.client import MaxClient

platform_router = Router(name="platform")


class OnboardStates(StatesGroup):
    waiting_business_name = State()
    waiting_token = State()


@platform_router.message(Command("help"), StateFilter("*"))
async def platform_help(message: Message) -> None:
    await message.answer(platform_bot_help_text())


@platform_router.message(Command("maxhelp"), StateFilter("*"))
async def platform_maxhelp(message: Message) -> None:
    await send_max_onboarding_full(message)


@platform_router.message(Command("maxquick"), StateFilter("*"))
async def platform_maxquick(message: Message) -> None:
    await send_max_onboarding_short(message)


@platform_router.message(CommandStart())
async def platform_start(message: Message, state: FSMContext) -> None:
    async with SessionLocal() as session:
        owned = await find_owned_tenant_for_telegram_user(
            session, message.from_user.id  # type: ignore[union-attr]
        )
    if owned:
        await state.update_data(owned_tenant_id=str(owned.id), business_name=owned.name)
        await state.set_state(OnboardStates.waiting_token)
        status_note = ""
        if owned.bot_status == "revoked":
            status_note = "\n\n⚠️ Токен бота салона недействителен (Revoke в BotFather?)."
        await message.answer(
            f"Салон «{owned.name}» уже подключён.{status_note}\n"
            "Пришлите актуальный токен из @BotFather одним сообщением."
        )
        return
    await state.set_state(OnboardStates.waiting_business_name)
    await message.answer(
        "Beaty — платформа брендированных ботов для записи.\n"
        "Шаг 1: пришлите название вашего бизнеса."
    )


@platform_router.message(OnboardStates.waiting_business_name)
async def platform_business_name(message: Message, state: FSMContext) -> None:
    await state.update_data(business_name=message.text or "Мой салон")
    await state.set_state(OnboardStates.waiting_token)
    await message.answer(
        "Шаг 2: создайте бота в @BotFather и пришлите токен одним сообщением.\n"
        "Сообщение с токеном будет удалено после обработки."
    )


def _looks_like_telegram_token(token: str) -> bool:
    return ":" in token


async def _parse_max_token(token: str) -> tuple[int, str] | None:
    try:
        me = await MaxClient(token).get_me()
    except Exception:
        return None
    return int(me.get("user_id") or me.get("id") or 0), str(me.get("username") or me.get("name") or "")


@platform_router.message(OnboardStates.waiting_token)
async def platform_token(message: Message, state: FSMContext) -> None:
    token = (message.text or "").strip()
    if not _looks_like_telegram_token(token):
        max_info = await _parse_max_token(token)
        if max_info is None:
            await message.answer("Похоже, это не токен Telegram или MAX. Попробуйте ещё раз.")
            return
        bot_id, bot_username = max_info
        data = await state.get_data()
        async with SessionLocal() as session:
            from uuid import UUID

            from app.domain.models import Tenant

            owned_tenant_id = data.get("owned_tenant_id")
            if not owned_tenant_id:
                await message.answer("Сначала подключите Telegram-бота или начните с /start.")
                return
            tenant = await session.get(Tenant, UUID(owned_tenant_id))
            if tenant is None:
                await message.answer("Салон не найден.")
                return
            linked = await find_tenant_by_max_bot_id(session, bot_id)
            if linked is not None and linked.id != tenant.id:
                await message.answer("Этот MAX-бот уже привязан к другому бизнесу.")
                return
            try:
                await attach_max_bot_token(session, tenant, bot_token=token, bot_id=bot_id, bot_username=bot_username)
                await session.commit()
            except BotAlreadyLinkedError:
                await session.rollback()
                await message.answer("Этот MAX-бот уже подключён к другому бизнесу.")
                return
        await state.clear()
        await message.answer(
            f"MAX-бот подключён к салону «{tenant.name}».{max_owner_guide_tail()}"
        )
        return
    if ":" not in token:
        await message.answer("Похоже, это не токен. Попробуйте ещё раз.")
        return
    data = await state.get_data()
    try:
        candidate = create_bot(token)
    except TokenValidationError:
        await message.answer("Похоже, это не токен. Попробуйте ещё раз.")
        return
    try:
        me = await candidate.get_me()
    except TelegramAPIError:
        await message.answer("Telegram не принял токен. Проверьте и отправьте снова.")
        return
    finally:
        await candidate.session.close()
    bot_info = {"id": me.id, "username": me.username or ""}
    try:
        await message.delete()
    except Exception:
        pass
    async with SessionLocal() as session:
        try:
            owned_tenant_id = data.get("owned_tenant_id")
            if owned_tenant_id:
                from uuid import UUID

                from app.domain.models import Tenant

                tenant = await session.get(Tenant, UUID(owned_tenant_id))
                if tenant is None:
                    await message.answer("Салон не найден. Начните с /start.")
                    return
            else:
                tenant = await create_tenant_for_owner(
                    session,
                    owner_telegram_id=message.from_user.id,  # type: ignore[union-attr]
                    business_name=data.get("business_name", "Мой салон"),
                    owner_display_name=message.from_user.full_name,  # type: ignore[union-attr]
                )
            linked = await find_tenant_by_bot_id(session, bot_info["id"])
            if linked is not None and linked.id != tenant.id:
                await message.answer(
                    "Этот бот уже подключён к другому бизнесу. "
                    "Пришлите токен другого бота из @BotFather."
                )
                return
            await attach_bot_token(
                session,
                tenant,
                bot_token=token,
                bot_id=bot_info["id"],
                bot_username=bot_info["username"],
            )
            await session.commit()
            public_id = tenant.public_id
            tenant_snapshot = tenant
        except BotAlreadyLinkedError:
            await session.rollback()
            await message.answer(
                "Этот бот уже подключён к другому бизнесу. "
                "Пришлите токен другого бота из @BotFather."
            )
            return
    await state.update_data(owned_tenant_id=str(tenant_snapshot.id))
    await state.set_state(OnboardStates.waiting_token)
    setup_bot = create_bot(token)
    try:
        await sync_tenant_bot_telegram_ui(setup_bot, tenant_snapshot)
    except TelegramAPIError:
        pass
    finally:
        await setup_bot.session.close()
    bot_line = bot_mention_html(bot_info.get("username") or None)
    from app.bot.miniapp import miniapp_enabled

    if miniapp_enabled():
        after_connect = (
            f"Откройте {bot_line} — в чате и в списке диалогов появится кнопка «Открыть» "
            "для записи и кабинета."
        )
    else:
        after_connect = (
            f"Откройте {bot_line} и нажмите /start — запись идёт через чат и кнопки, "
            "отдельный сайт не нужен."
        )
    await message.answer(
        f"Бизнес подключён.\nPublic ID: <code>{public_id}</code>\n\n{after_connect}\n\n"
        "Чтобы добавить MAX: инструкция /maxhelp (кратко /maxquick), затем пришлите токен MAX-бота сюда.",
        parse_mode="HTML",
    )


@platform_router.message(Command("status"))
async def platform_status(message: Message) -> None:
    async with SessionLocal() as session:
        from app.domain.models import Tenant

        count = len((await session.scalars(select(Tenant))).all())
    await message.answer(f"Активных бизнесов в базе: {count}")
