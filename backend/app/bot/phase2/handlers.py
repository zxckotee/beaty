from datetime import UTC, datetime
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ClientProfile, Tenant
from app.domain.services.waitlist_service import join_waitlist

phase2_router = Router(name="phase2")


class ReviewState(StatesGroup):
    waiting_text = State()


@phase2_router.callback_query(F.data.startswith("c:wait:"))
async def waitlist_join(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
) -> None:
    if not client_profile:
        await callback.answer("Нужен /start", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    service_id = UUID(parts[2])
    from datetime import date as date_cls

    pref = None
    try:
        pref = datetime.combine(date_cls.fromisoformat(parts[3]), datetime.min.time(), tzinfo=UTC)
    except ValueError:
        pref = None
    try:
        await join_waitlist(
            db_session,
            tenant_id=tenant.id,
            client_profile_id=client_profile.id,
            service_id=service_id,
            staff_member_id=None,
            preferred_date=pref,
        )
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text("Вы в листе ожидания. Напишем, когда освободится слот.")
    await callback.answer("Готово")


@phase2_router.callback_query(F.data.startswith("c:rv:"))
async def review_score(
    callback: CallbackQuery,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    booking_id = parts[2]
    score = int(parts[3])
    await state.update_data(review_booking_id=booking_id, review_score=score)
    await state.set_state(ReviewState.waiting_text)
    if callback.message:
        await callback.message.edit_text(f"Оценка {score}/5. Комментарий (или «-» чтобы пропустить):")
    await callback.answer()


@phase2_router.message(ReviewState.waiting_text)
async def review_text(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
) -> None:
    from app.domain.services.review_service import create_review

    data = await state.get_data()
    await state.clear()
    if not client_profile:
        return
    text = (message.text or "").strip()
    if text == "-":
        text = ""
    try:
        score = int(data["review_score"])
        await create_review(
            db_session,
            tenant_id=tenant.id,
            booking_id=UUID(data["review_booking_id"]),
            client_profile_id=client_profile.id,
            staff_rating=score,
            salon_rating=score,
            text=text or None,
        )
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Не удалось: {exc}")
        return
    await message.answer("Спасибо за отзыв!")


@phase2_router.message(Command("courses"))
async def cmd_courses(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
) -> None:
    from sqlalchemy import select

    from app.domain.models import CourseTemplate

    if not client_profile:
        await message.answer("/start сначала")
        return
    rows = (
        await db_session.scalars(
            select(CourseTemplate).where(CourseTemplate.tenant_id == tenant.id)
        )
    ).all()
    if not rows:
        await message.answer("Курсов пока нет.")
        return
    kb = InlineKeyboardBuilder()
    for c in rows:
        kb.button(text=c.name[:40], callback_data=f"c:crs:{c.id}")
    kb.adjust(1)
    await message.answer("Курсы:", reply_markup=kb.as_markup())


@phase2_router.callback_query(F.data.startswith("c:crs:"))
async def enroll_course(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    client_profile: ClientProfile | None,
) -> None:
    from app.domain.services.course_service import enroll_client

    if not client_profile:
        await callback.answer("Нужен /start", show_alert=True)
        return
    tpl_id = UUID((callback.data or "").split(":")[2])
    try:
        await enroll_client(
            db_session,
            tenant_id=tenant.id,
            template_id=tpl_id,
            client_profile_id=client_profile.id,
        )
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Записаны на курс")
