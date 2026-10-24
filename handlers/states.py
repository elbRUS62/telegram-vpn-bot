from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    waiting_extend_username = State()
    waiting_extend_days = State()
    waiting_reset_username = State()
    waiting_broadcast_text = State()
    waiting_delete_username = State()
    waiting_approve_request_username = State()
    waiting_comment = State()
    waiting_admin_id = State()