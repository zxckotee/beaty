from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.utils.token import TokenValidationError
from sqlalchemy import select

from app.bot.factory import create_bot
from app.core.db import SessionLocal
from app.domain.services.provisioning import attach_bot_token, create_tenant_for_owner

platform_router = Router(name="platform")


class OnboardStates(StatesGroup):
    waiting_business_name = State()
    waiting_token = State()


@platform_router.message(CommandStart())
async def platform_start(message: Message, state: FSMContext) -> None:
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


@platform_router.message(OnboardStates.waiting_token)
async def platform_token(message: Message, state: FSMContext) -> None:
    token = (message.text or "").strip()
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
    bot_info = {"id": me.id, "username": me.username}
    async with SessionLocal() as session:
        tenant = await create_tenant_for_owner(
            session,
            owner_telegram_id=message.from_user.id,  # type: ignore[union-attr]
            business_name=data.get("business_name", "Мой салон"),
            owner_display_name=message.from_user.full_name,  # type: ignore[union-attr]
        )
        await attach_bot_token(
            session,
            tenant,
            bot_token=token,
            bot_id=bot_info["id"],
            bot_username=bot_info.get("username", ""),
        )
        await session.commit()
        public_id = tenant.public_id
    try:
        await message.delete()
    except Exception:
        pass
    await state.clear()
    await message.answer(
        f"Бизнес подключён. Public ID: `{public_id}`\n"
        "Дальше: вебхук выставит деплой. Откройте бот салона и настройте каталог, "
        "график и тон общения прямо в чате (меню команд).",
        parse_mode="Markdown",
    )


@platform_router.message(Command("status"))
async def platform_status(message: Message) -> None:
    async with SessionLocal() as session:
        from app.domain.models import Tenant

        count = len((await session.scalars(select(Tenant))).all())
    await message.answer(f"Активных бизнесов в базе: {count}")
