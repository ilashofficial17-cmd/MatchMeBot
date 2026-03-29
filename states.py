from aiogram.fsm.state import State, StatesGroup


class Reg(StatesGroup):
    name = State()
    age = State()
    gender = State()
    mode = State()
    interests = State()


class Chat(StatesGroup):
    waiting = State()
    chatting = State()


class Rules(StatesGroup):
    waiting = State()


class Complaint(StatesGroup):
    reason = State()


class EditProfile(StatesGroup):
    name = State()
    age = State()
    gender = State()
    mode = State()
    interests = State()
    search_gender = State()


class AdminState(StatesGroup):
    waiting_user_id = State()


class ResetProfile(StatesGroup):
    confirm = State()


class AIChat(StatesGroup):
    choosing = State()
    chatting = State()
