from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.subscription_gate import assert_tenant_can_write
from app.bot.filters.roles import HasManagerRole, is_owner
from app.bot.manager.states import ManagerTeamStates
from app.bot.shared import assert_can_write
from app.domain.models import StaffMember, StaffRole, Tenant, UserAccount
from app.domain.services.schedule_service import ensure_default_schedule
from app.domain.services.team_invite_service import create_invite, invite_start_param, regenerate_invite

team_router = Router(name="manager_team")
team_router.message.filter(HasManagerRole())
team_router.callback_query.filter(HasManagerRole())


def _staff_card(st: StaffMember) -> str:
    linked = "✅ в Telegram" if st.user_account_id else "⏳ без привязки"
    lines = [f"*{st.display_name}* ({linked})", f"Роли: {', '.join(st.roles or [])}"]
    if st.specialization:
        lines.append(f"Специализация: {st.specialization}")
    if st.bio:
        lines.append(st.bio[:400])
    return "\n".join(lines)


async def _invite_link(message: Message, tenant: Tenant, raw: str) -> str:
    username = tenant.bot_username
    if not username and message.bot:
        me = await message.bot.get_me()
        username = me.username
    uname = username or "bot"
    return f"https://t.me/{uname}?start={invite_start_param(raw)}"


@team_router.message(Command("staff"))
@team_router.message(F.text == "Команда")
async def cmd_team_list(
    message: Message,
    tenant: Tenant,
    db_session: AsyncSession,
) -> None:
    rows = (
        await db_session.scalars(
            select(StaffMember).where(
                StaffMember.tenant_id == tenant.id,
                StaffMember.is_active.is_(True),
            )
        )
    ).all()
    if not rows:
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Добавить специалиста", callback_data="m:team:add")
        await message.answer("Команда пуста.", reply_markup=kb.as_markup())
        return
    kb = InlineKeyboardBuilder()
    for st in rows:
        kb.button(text=st.display_name[:40], callback_data=f"m:team:view:{st.id}")
    kb.adjust(1)
    kb.button(text="➕ Добавить специалиста", callback_data="m:team:add")
    await message.answer("Команда:", reply_markup=kb.as_markup())


@team_router.callback_query(F.data == "m:team:add")
async def team_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManagerTeamStates.waiting_name)
    if callback.message:
        await callback.message.answer("Имя специалиста (как увидят клиенты):")
    await callback.answer()


@team_router.message(ManagerTeamStates.waiting_name)
async def team_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()[:120]
    if not name:
        await message.answer("Введите имя.")
        return
    await state.update_data(team_name=name)
    await state.set_state(ManagerTeamStates.waiting_photo)
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустить фото", callback_data="m:team:skip_photo")
    await message.answer("Отправьте фото специалиста или нажмите «Пропустить».", reply_markup=kb.as_markup())


@team_router.callback_query(F.data == "m:team:skip_photo")
async def team_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(team_photo_file_id=None)
    await state.set_state(ManagerTeamStates.waiting_bio)
    if callback.message:
        await callback.message.answer("Краткое описание: для кого этот мастер, стиль работы:")
    await callback.answer()


@team_router.message(ManagerTeamStates.waiting_photo, F.photo)
async def team_photo(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(team_photo_file_id=file_id)
    await state.set_state(ManagerTeamStates.waiting_bio)
    await message.answer("Краткое описание: для кого этот мастер, стиль работы:")


@team_router.message(ManagerTeamStates.waiting_bio)
async def team_bio(message: Message, state: FSMContext) -> None:
    await state.update_data(team_bio=(message.text or "").strip()[:2000])
    await state.set_state(ManagerTeamStates.waiting_specialization)
    await message.answer("Специализация (например: мужские стрижки, окрашивание):")


@team_router.message(ManagerTeamStates.waiting_specialization)
async def team_specialization(
    message: Message,
    state: FSMContext,
    tenant: Tenant,
    db_session: AsyncSession,
    subscription_read_only: bool,
    user_account: UserAccount | None,
) -> None:
    data = await state.get_data()
    try:
        assert_tenant_can_write(tenant)
        assert_can_write(tenant, subscription_read_only)
        staff = StaffMember(
            tenant_id=tenant.id,
            display_name=data["team_name"],
            photo_file_id=data.get("team_photo_file_id"),
            bio=data.get("team_bio"),
            specialization=(message.text or "").strip()[:512],
            roles=[StaffRole.SPECIALIST.value],
        )
        db_session.add(staff)
        await db_session.flush()
        await ensure_default_schedule(session=db_session, tenant_id=tenant.id, staff_member_id=staff.id)
        _, raw = await create_invite(
            db_session,
            tenant_id=tenant.id,
            staff_member_id=staff.id,
            created_by_user_account_id=user_account.id if user_account else None,
        )
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await message.answer(f"Ошибка: {exc}")
        return
    await state.clear()
    link = await _invite_link(message, tenant, raw)
    await message.answer(
        f"Специалист «{staff.display_name}» создан.\n\n"
        f"Ссылка для мастера (действует 7 дней):\n{link}",
    )


@team_router.callback_query(F.data.startswith("m:team:view:"))
async def team_view(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
    user_account: UserAccount | None,
) -> None:
    sid = UUID((callback.data or "").split(":")[3])
    st = await db_session.get(StaffMember, sid)
    if st is None or st.tenant_id != tenant.id:
        await callback.answer("Не найден", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    if st.user_account_id is None:
        kb.button(text="🔗 Ссылка-приглашение", callback_data=f"m:team:inv:{st.id}")
    if is_owner(roles):
        kb.button(text="👔 Сделать менеджером", callback_data=f"m:team:mgr:{st.id}")
    kb.button(text="◀ Список", callback_data="m:team:list")
    kb.adjust(1)
    if callback.message:
        await callback.message.edit_text(_staff_card(st).replace("*", ""), reply_markup=kb.as_markup())
    await callback.answer()


@team_router.callback_query(F.data == "m:team:list")
async def team_list_cb(callback: CallbackQuery, tenant: Tenant, db_session: AsyncSession) -> None:
    if callback.message:
        await callback.message.delete()
        await cmd_team_list(callback.message, tenant, db_session)
    await callback.answer()


@team_router.callback_query(F.data.startswith("m:team:inv:"))
async def team_invite(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    user_account: UserAccount | None,
    subscription_read_only: bool,
) -> None:
    sid = UUID((callback.data or "").split(":")[3])
    try:
        assert_can_write(tenant, subscription_read_only)
        _, raw = await regenerate_invite(
            db_session,
            tenant_id=tenant.id,
            staff_member_id=sid,
            created_by_user_account_id=user_account.id if user_account else None,
        )
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    if callback.message:
        link = await _invite_link(callback.message, tenant, raw)
        await callback.message.answer(f"Новая ссылка:\n{link}")
    await callback.answer("Готово")


@team_router.callback_query(F.data.startswith("m:team:mgr:"))
async def team_make_manager(
    callback: CallbackQuery,
    tenant: Tenant,
    db_session: AsyncSession,
    roles: set[str],
    subscription_read_only: bool,
) -> None:
    if not is_owner(roles):
        await callback.answer("Только владелец", show_alert=True)
        return
    sid = UUID((callback.data or "").split(":")[3])
    st = await db_session.get(StaffMember, sid)
    if st is None or st.tenant_id != tenant.id:
        await callback.answer("Не найден", show_alert=True)
        return
    try:
        assert_can_write(tenant, subscription_read_only)
        r = set(st.roles or [])
        r.add(StaffRole.MANAGER.value)
        st.roles = sorted(r)
        _, raw = await regenerate_invite(
            db_session,
            tenant_id=tenant.id,
            staff_member_id=st.id,
            created_by_user_account_id=None,
            intended_roles=["manager", "specialist"],
        )
        await db_session.commit()
    except Exception as exc:
        await db_session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return
    if callback.message:
        link = await _invite_link(callback.message, tenant, raw)
        await callback.message.answer(f"Роль менеджера назначена. Ссылка:\n{link}")
    await callback.answer("OK")
