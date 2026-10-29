from aiogram.fsm.state import State, StatesGroup


class ClientOnboarding(StatesGroup):
    waiting_contact = State()
    waiting_name_confirm = State()
    waiting_name_edit = State()
    waiting_marketing = State()


class BookFlow(StatesGroup):
    pick_service = State()
    pick_specialist = State()
    pick_day = State()
    pick_slot = State()
    confirm_hold = State()


class RescheduleFlow(StatesGroup):
    pick_day = State()
    pick_slot = State()
