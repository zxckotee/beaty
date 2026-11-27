from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.token import TokenValidationError
from sqlalchemy import select

from app.bot.factory import create_bot
from app.bot.help_delivery import open_bot_keyboard
from app.bot.telegram_format import bot_mention_html
from app.bot.telegram_qr import qr_png_bytes
from app.bot.telegram_ui_sync import sync_tenant_bot_telegram_ui
from app.content.user_guide import platform_landing_url, public_web_base, telegram_bot_url
from app.core.db import SessionLocal
from app.domain.exceptions import BotAlreadyLinkedError
from app.domain.models import Tenant
from app.domain.services.provisioning import (
    attach_bot_token,
    create_tenant_for_owner,
    find_owned_tenant_for_telegram_user,
    find_tenant_by_bot_id,
)
from app.platform_bot.keyboards import platform_reply_keyboard

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
    "🔗 Готовые материалы: ссылка для соцсетей и QR для печати\n\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "🚀 Начнём?\n"
    "Шаг 1: напишите название вашего салона или барбершопа одним сообщением.\n\n"
    "💬 Вопросы — пишите сюда, мы на связи.\n\n"
    "Удачного запуска! ✨"
)


class OnboardStates(StatesGroup):
    waiting_offer_accept = State()
    waiting_business_name = State()
    waiting_token = State()


@platform_router.message(CommandStart())
async def platform_start(message: Message, state: FSMContext) -> None:
    await state.clear()
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
            f"🏢 Салон «{owned.name}» уже подключён.{status_note}\n\n"
            "🔑 Пришлите актуальный токен из @BotFather одним сообщением.",
            reply_markup=platform_reply_keyboard(),
        )
        return
    await state.set_state(OnboardStates.waiting_offer_accept)
    base = public_web_base() or platform_landing_url()
    offer = f"{base.rstrip('/')}/legal/offer"
    pd = f"{base.rstrip('/')}/legal/pd-processing"
    kb = InlineKeyboardBuilder()
    kb.button(text="Принимаю оферту и поручение", callback_data="platform:offer:yes")
    kb.adjust(1)
    await message.answer(
        "Подключение Beaty-Welcome — SaaS для салонов. Оплата подписки вносит владелец бизнеса.\n\n"
        f"📄 <a href=\"{offer}\">Оферта</a> · <a href=\"{pd}\">Поручение на обработку ПДн</a>\n\n"
        "Нажмите кнопку ниже, чтобы продолжить настройку.",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
        reply_to_message_id=None,
    )
    await message.answer("Справка — кнопка внизу.", reply_markup=platform_reply_keyboard())


@platform_router.callback_query(F.data == "platform:offer:yes")
async def platform_offer_accepted(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(offer_accepted=True)
    await state.set_state(OnboardStates.waiting_business_name)
    if callback.message:
        await callback.message.edit_text(PLATFORM_START_WELCOME)
    await callback.answer()


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
            tenant: Tenant | None = None
            if owned_tenant_id:
                from uuid import UUID

                tenant = await session.get(Tenant, UUID(owned_tenant_id))
            if tenant is None:
                tenant = await find_owned_tenant_for_telegram_user(
                    session, message.from_user.id  # type: ignore[union-attr]
                )
            if tenant is None:
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
            if data.get("offer_accepted"):
                tenant.rules = {
                    **(tenant.rules or {}),
                    "b2b_offer_accepted_at": datetime.now(UTC).isoformat(),
                }
            await session.commit()
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

    business_name = tenant_snapshot.name or data.get("business_name", "салон")
    bot_open_url = telegram_bot_url(bot_info.get("username"), start="book")
    if miniapp_enabled():
        next_steps = (
            f"✨ В {bot_line} появится кнопка «Открыть» — запись и кабинет в мини-приложении."
        )
    else:
        next_steps = f"✨ Откройте {bot_line} и нажмите /start — запись через чат."
    caption = (
        f"🎉 <b>Готово!</b> Бизнес «{business_name}» подключён.\n\n"
        f"🤖 Ваш бот: {bot_line}\n\n"
        f"📋 <b>Что дальше</b>\n"
        f"• Заполните услуги и график в боте\n"
        f"• Покажите QR на ресепшене и в соцсетях\n\n"
        f"{next_steps}"
    )
    qr_bytes = qr_png_bytes(bot_open_url)
    photo = BufferedInputFile(qr_bytes, filename="beaty-bot-qr.png")
    markup = open_bot_keyboard(bot_open_url)
    try:
        await message.answer_photo(
            photo,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except TelegramAPIError:
        await message.answer(
            caption + "\n\n📎 Отсканируйте ссылку по кнопке ниже.",
            parse_mode="HTML",
            reply_markup=markup,
        )
    await message.answer("💡 Справка — внизу чата.", reply_markup=platform_reply_keyboard())


@platform_router.message(Command("status"))
async def platform_status(message: Message) -> None:
    async with SessionLocal() as session:
        from app.domain.models import Tenant

        count = len((await session.scalars(select(Tenant))).all())
    await message.answer(f"Активных бизнесов в базе: {count}")
