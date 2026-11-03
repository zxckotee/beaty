from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.active_role import (
    UI_ROLE_CLIENT,
    UI_ROLE_LABELS,
    UiRole,
    write_stored_ui_role,
)
from app.bot.client.states import ClientOnboarding
from app.bot.keyboards.builders import contact_request_keyboard, main_menu_reply, role_switch_inline
from app.domain.models import ClientProfile, StaffMember
from app.domain.services.client_onboarding_service import client_has_phone

role_switch_router = Router(name="role_switch")


def _menu(active_ui_role: UiRole, can_switch_ui_role: bool):
    return main_menu_reply(active_ui_role=active_ui_role, can_switch_ui_role=can_switch_ui_role)


@role_switch_router.message(F.text == "Сменить режим")
async def ask_switch(
    message: Message,
    active_ui_role: str,
    available_ui_roles: list[str],
) -> None:
    if len(available_ui_roles) < 2:
        await message.answer("Доступен только один режим.")
        return
    await message.answer(
        "Выберите, от чьего имени работаете сейчас:",
        reply_markup=role_switch_inline(available_ui_roles, active=active_ui_role),  # type: ignore[arg-type]
    )


@role_switch_router.callback_query(F.data.startswith("ui:role:"))
async def apply_switch(
    callback: CallbackQuery,
    state: FSMContext,
    db_session: AsyncSession,
    staff_member: StaffMember | None,
    client_profile: ClientProfile | None,
    available_ui_roles: list[str],
    can_switch_ui_role: bool,
) -> None:
    if not can_switch_ui_role or staff_member is None:
        await callback.answer("Переключение недоступно", show_alert=True)
        return
    role = (callback.data or "").removeprefix("ui:role:")
    if role not in available_ui_roles:
        await callback.answer("Недоступный режим", show_alert=True)
        return

    write_stored_ui_role(staff_member, role)  # type: ignore[arg-type]
    await db_session.commit()

    label = UI_ROLE_LABELS[role]  # type: ignore[index]
    if role == UI_ROLE_CLIENT and not (client_profile and client_has_phone(client_profile)):
        await state.set_state(ClientOnboarding.waiting_contact)
        if callback.message:
            await callback.message.edit_text(
                f"Режим «{label}». Для записи нужен номер телефона — нажмите кнопку ниже."
            )
            await callback.message.answer(
                "Поделиться телефоном:",
                reply_markup=contact_request_keyboard(),
            )
        await callback.answer()
        return

    if callback.message:
        await callback.message.edit_text(f"Сейчас вы в режиме: {label}.")
        await callback.message.answer(
            "Меню обновлено.",
            reply_markup=_menu(role, can_switch_ui_role),  # type: ignore[arg-type]
        )
    await callback.answer()
