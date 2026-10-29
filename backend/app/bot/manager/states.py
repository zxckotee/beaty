from aiogram.fsm.state import State, StatesGroup


class ManagerTeamStates(StatesGroup):
    waiting_name = State()
    waiting_photo = State()
    waiting_bio = State()
    waiting_specialization = State()
    confirm = State()


class ManagerServiceStates(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_duration = State()
    waiting_buffer = State()


class ManagerServiceEditStates(StatesGroup):
    waiting_price = State()
    waiting_duration = State()


class ManagerManualBookStates(StatesGroup):
    pick_staff = State()
    pick_service = State()
    pick_day = State()
    pick_slot = State()
    client_name = State()
    client_phone = State()


class ManagerSettingsStates(StatesGroup):
    waiting_salon_name = State()
    waiting_privacy_url = State()
