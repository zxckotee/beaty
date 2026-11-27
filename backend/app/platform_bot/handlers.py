from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.utils.token import TokenValidationError
from sqlalchemy import select

from app.bot.factory import create_bot
from app.bot.telegram_format import bot_mention_html
from app.bot.telegram_ui_sync import sync_tenant_bot_telegram_ui
from app.core.db import SessionLocal
from app.domain.exceptions import BotAlreadyLinkedError
from app.domain.services.provisioning import (
    attach_bot_token,
    create_tenant_for_owner,
    find_owned_tenant_for_telegram_user,
    find_tenant_by_bot_id,
)

platform_router = Router(name="platform")

PLATFORM_START_WELCOME = (
    "💇‍♀️ Добро пожаловать в Beaty-Welcome!\n\n"
    "Вы подключаете свой Telegram-бот для записи под брендом салона — "
    "без агрегаторов и без «позвоните администратору».\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📋 ЧТО НУЖНО ОТ ВАС\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "1️⃣ Создать бота в @BotFather\n"
    "   • Имя и username — от вашего салона\n"
    "   • Аватар — ваш логотип\n\n"
    "2️⃣ Прислать сюда токен бота (одним сообщением)\n"
    "   🔒 Сообщение с токеном удалим после подключения\n\n"
    "3️⃣ Заполнить основу в боте салона (~5–15 минут):\n"
    "   • 💅 Услуги, цены и длительность\n"
    "   • 📅 График работы (салон и мастера)\n"
    "   • 📍 Адрес и контакты\n"
    "   • 👥 Команда — пригласить мастеров по ссылке\n\n"
    "4️⃣ Запустить запись для клиентов:\n"
    "   • Ссылку / QR — в Instagram, VK, на ресепшене\n"
    "   • Кнопку «Записаться» — в Яндекс.Картах и 2ГИС\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🎁 ЧТО ВЫ ПОЛУЧАЕТЕ\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "✅ Свой бот с вашим именем — клиент общается с вами, а не с чужим каталогом\n\n"
    "📲 Запись 24/7 в Telegram — услуга → мастер → время, без звонков в нерабочее время\n\n"
    "🔔 Напоминания и подтверждение визита — меньше неявок и пустых слотов\n\n"
    "🔁 «Пора снова» — напоминания о повторном визите по вашим услугам\n\n"
    "📊 Веб-кабинет: расписание, записи, клиенты, аналитика\n\n"
    "👥 Роли для владельца, администратора и мастеров — каждый видит своё\n\n"
    "⭐ Отзывы и рейтинг — доверие в каталоге и ответы от салона\n\n"
    "🔗 Готовые материалы: ссылка для соцсетей, QR для печати, тексты для клиентов\n\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "🚀 Начнём?\n"
    "Шаг 1: напишите название вашего салона или барбершопа одним сообщением.\n\n"
    "💬 Вопросы — пишите сюда, мы на связи.\n\n"
    "Удачного запуска! ✨"
)


class OnboardStates(StatesGroup):
    waiting_business_name = State()
    waiting_token = State()


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
    await message.answer(PLATFORM_START_WELCOME)


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
    await state.clear()
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
        f"Бизнес подключён.\nPublic ID: <code>{public_id}</code>\n\n{after_connect}",
        parse_mode="HTML",
    )


@platform_router.message(Command("status"))
async def platform_status(message: Message) -> None:
    async with SessionLocal() as session:
        from app.domain.models import Tenant

        count = len((await session.scalars(select(Tenant))).all())
    await message.answer(f"Активных бизнесов в базе: {count}")
