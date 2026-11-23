from aiogram import Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select

from app.bot.common.max_owner_guide import (
    max_owner_guide_tail,
    platform_bot_help_text,
    send_max_onboarding_full,
    send_max_onboarding_short,
)
from app.bot.miniapp import miniapp_enabled, miniapp_url_for_tenant
from app.core.db import SessionLocal
from app.domain.exceptions import BotAlreadyLinkedError
from app.domain.services.provisioning import (
    attach_max_bot_token,
    attach_telegram_bot_token,
    create_tenant_for_owner,
    find_owned_tenant_for_max_user,
    find_tenant_by_channel_bot_id,
)
from app.max.client import MaxClient
from app.messenger.types import Channel

platform_max_router = Router(name="platform_max")


class OnboardStates(StatesGroup):
    waiting_other_platform = State()
    waiting_business_name = State()
    waiting_token = State()
    waiting_second_token = State()


@platform_max_router.message(Command("help"), StateFilter("*"))
async def platform_max_help(message: Message) -> None:
    await message.answer(platform_bot_help_text())


@platform_max_router.message(Command("maxhelp"), StateFilter("*"))
async def platform_max_maxhelp(message: Message) -> None:
    await send_max_onboarding_full(message)


@platform_max_router.message(Command("maxquick"), StateFilter("*"))
async def platform_max_maxquick(message: Message) -> None:
    await send_max_onboarding_short(message)


async def _validate_max_token(token: str) -> tuple[int, str] | None:
    try:
        me = await MaxClient(token).get_me()
    except Exception:
        return None
    user_id = int(me.get("user_id") or me.get("id") or 0)
    username = str(me.get("username") or me.get("name") or "")
    return user_id, username


@platform_max_router.message(CommandStart())
async def platform_max_start(message: Message, state: FSMContext) -> None:
    async with SessionLocal() as session:
        owned = await find_owned_tenant_for_max_user(session, message.from_user.id)  # type: ignore[union-attr]
    await state.set_state(OnboardStates.waiting_other_platform)
    if owned:
        await state.update_data(owned_tenant_id=str(owned.id), business_name=owned.name)
        await message.answer(
            f"Салон «{owned.name}» уже подключён.\n"
            "У вас уже есть бот в Telegram на Beaty? Ответьте: да / нет"
        )
        return
    await message.answer(
        "Beaty в MAX — платформа для записи.\n"
        "У вас уже есть подключённый бот в Telegram? Ответьте: да / нет\n\n"
        "Перед токеном MAX: /maxhelp (кратко /maxquick)."
    )


@platform_max_router.message(OnboardStates.waiting_other_platform)
async def platform_max_other_platform(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().lower()
    has_other = text in {"да", "yes", "y", "+", "1"}
    if text not in {"да", "нет", "yes", "no", "y", "n", "+", "-", "1", "0"}:
        await message.answer("Ответьте «да» или «нет».")
        return
    await state.update_data(has_other=has_other)
    data = await state.get_data()
    if data.get("owned_tenant_id"):
        if has_other:
            await state.set_state(OnboardStates.waiting_second_token)
            await message.answer("Пришлите токен вашего Telegram-бота (из @BotFather).")
        else:
            await state.set_state(OnboardStates.waiting_token)
            await message.answer("Пришлите актуальный токен MAX-бота одним сообщением.")
        return
    if has_other:
        await state.set_state(OnboardStates.waiting_second_token)
        await message.answer(
            "Сначала пришлите токен уже подключённого Telegram-бота, "
            "затем мы попросим токен MAX."
        )
    else:
        await state.set_state(OnboardStates.waiting_business_name)
        await message.answer("Шаг 1: пришлите название вашего бизнеса.")


@platform_max_router.message(OnboardStates.waiting_business_name)
async def platform_max_business_name(message: Message, state: FSMContext) -> None:
    await state.update_data(business_name=message.text or "Мой салон")
    await state.set_state(OnboardStates.waiting_token)
    await message.answer(
        "Шаг 2: пришлите токен MAX-бота одним сообщением.\n"
        "Как получить токен: /maxhelp (кратко /maxquick)."
    )


@platform_max_router.message(OnboardStates.waiting_second_token)
async def platform_max_second_token(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    token = (message.text or "").strip()
    from app.bot.factory import create_bot
    from aiogram.exceptions import TelegramAPIError
    from aiogram.utils.token import TokenValidationError

    if not data.get("first_token_stored"):
        if ":" not in token:
            await message.answer("Похоже, это не токен Telegram. Попробуйте ещё раз.")
            return
        try:
            candidate = create_bot(token)
            me = await candidate.get_me()
        except (TokenValidationError, TelegramAPIError):
            await message.answer("Telegram не принял токен. Попробуйте ещё раз.")
            return
        finally:
            try:
                await candidate.session.close()
            except Exception:
                pass
        await state.update_data(
            first_token_stored=True,
            tg_token=token,
            tg_bot_id=me.id,
            tg_bot_username=me.username or "",
        )
        try:
            await message.delete()
        except Exception:
            pass
        await state.set_state(OnboardStates.waiting_token)
        await message.answer("Теперь пришлите токен MAX-бота.")
        return
    await platform_max_token(message, state)


@platform_max_router.message(OnboardStates.waiting_token)
async def platform_max_token(message: Message, state: FSMContext) -> None:
    token = (message.text or "").strip()
    if len(token) < 8:
        await message.answer("Похоже, это не токен MAX. Попробуйте ещё раз.")
        return
    info = await _validate_max_token(token)
    if info is None:
        await message.answer("MAX не принял токен. Проверьте и отправьте снова.")
        return
    bot_id, bot_username = info
    data = await state.get_data()
    try:
        await message.delete()
    except Exception:
        pass
    async with SessionLocal() as session:
        try:
            from uuid import UUID

            from app.domain.models import Tenant

            owned_tenant_id = data.get("owned_tenant_id")
            if owned_tenant_id:
                tenant = await session.get(Tenant, UUID(owned_tenant_id))
                if tenant is None:
                    await message.answer("Салон не найден. Начните с /start.")
                    return
            elif data.get("tg_token"):
                tenant = await create_tenant_for_owner(
                    session,
                    owner_telegram_id=None,
                    owner_max_user_id=message.from_user.id,  # type: ignore[union-attr]
                    business_name=data.get("business_name", "Мой салон"),
                    owner_display_name=message.from_user.full_name,  # type: ignore[union-attr]
                )
                await attach_telegram_bot_token(
                    session,
                    tenant,
                    bot_token=data["tg_token"],
                    bot_id=int(data["tg_bot_id"]),
                    bot_username=str(data.get("tg_bot_username") or ""),
                )
            else:
                tenant = await create_tenant_for_owner(
                    session,
                    owner_max_user_id=message.from_user.id,  # type: ignore[union-attr]
                    business_name=data.get("business_name", "Мой салон"),
                    owner_display_name=message.from_user.full_name,  # type: ignore[union-attr]
                )
            linked = await find_tenant_by_channel_bot_id(session, Channel.MAX, bot_id)
            if linked is not None and linked.id != tenant.id:
                await message.answer("Этот MAX-бот уже подключён к другому бизнесу.")
                return
            await attach_max_bot_token(
                session,
                tenant,
                bot_token=token,
                bot_id=bot_id,
                bot_username=bot_username,
            )
            if data.get("tg_token") and not owned_tenant_id:
                pass
            elif data.get("tg_token") and owned_tenant_id:
                await attach_telegram_bot_token(
                    session,
                    tenant,
                    bot_token=data["tg_token"],
                    bot_id=int(data["tg_bot_id"]),
                    bot_username=str(data.get("tg_bot_username") or ""),
                )
            await session.commit()
            public_id = tenant.public_id
            tenant_snapshot = tenant
        except BotAlreadyLinkedError:
            await session.rollback()
            await message.answer("Этот бот уже подключён к другому бизнесу.")
            return
    await state.clear()
    hint = ""
    url = miniapp_url_for_tenant(tenant_snapshot)
    if miniapp_enabled() and url:
        hint = f"\n\nСсылка для мини-приложения (вставьте в MAX → Чат-боты → Настройки):\n{url}"
    await message.answer(
        f"Бизнес подключён (MAX).\nPublic ID: <code>{public_id}</code>{hint}{max_owner_guide_tail()}",
        parse_mode="HTML",
    )