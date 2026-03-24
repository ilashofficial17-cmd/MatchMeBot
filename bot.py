import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

users = {}
waiting_queue_simple = []
waiting_queue_flirt = []
waiting_queue_kink = []
active_chats = {}
last_message_time = {}
message_count = {}
pairing_lock = asyncio.Lock()

class Registration(StatesGroup):
    language = State()
    name = State()
    age = State()
    gender = State()
    mode = State()
    interests = State()

class Searching(StatesGroup):
    waiting = State()
    chatting = State()

TEXTS = {
    "ru": {
        "welcome": "👋 Привет! Добро пожаловать в MatchMe",
        "enter_name": "Как тебя зовут? (будет видно собеседнику)",
        "enter_age": "Сколько тебе лет?",
        "choose_gender": "Выбери свой пол:",
        "choose_mode": "Выбери режим общения:",
        "choose_interests": "Выбери 1–3 интереса (нажимай кнопки):",
        "profile_saved": "✅ Анкета сохранена!",
        "searching": "🔍 Ищем собеседника...",
        "found": "✅ Собеседник найден!",
        "chat_ended": "💔 Чат завершён.",
        "partner_left": "😔 Собеседник покинул чат.",
        "inactive": "⏰ Чат завершён из-за неактивности.",
        "male": "👨 Парень",
        "female": "👩 Девушка",
        "age_error": "Пожалуйста введи число от 16 до 99",
        "need_profile": "Сначала заполни анкету",
        "done": "✅ Готово",
        "complain": "🚩 Пожаловаться",
        "complain_sent": "🚩 Жалоба отправлена. Чат завершён.",
        "flood_warning": "Не спамь! Подожди немного.",
    }
}

def get_main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти собеседника")],
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="🔄 Перезапустить")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)

def get_chat_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Следующий собеседник")],
        [KeyboardButton(text="❌ Завершить чат")],
        [KeyboardButton(text="🚩 Пожаловаться")]
    ], resize_keyboard=True)

def get_cancel_search_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить поиск")]], resize_keyboard=True)

# ====================== СТАРТ И ПЕРЕЗАПУСК ======================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]], resize_keyboard=True)
    await message.answer("🌐 Выбери язык:", reply_markup=kb)
    await state.set_state(Registration.language)

@dp.message(F.text.contains("Перезапустить"))
async def cmd_restart(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    for q in [waiting_queue_simple, waiting_queue_flirt, waiting_queue_kink]:
        if uid in q: q.remove(uid)
    if uid in active_chats:
        partner = active_chats.pop(uid, None)
        active_chats.pop(partner, None)
    await message.answer("🔄 Бот полностью перезапущен!")
    await cmd_start(message, state)

# ====================== РЕГИСТРАЦИЯ ======================
@dp.message(Registration.language)
async def choose_language(message: types.Message, state: FSMContext):
    lang = "ru" if "Русский" in message.text else "en"
    users[message.from_user.id] = {"lang": lang}
    await state.update_data(lang=lang)
    await message.answer(TEXTS[lang]["welcome"], reply_markup=ReplyKeyboardRemove())
    await message.answer(TEXTS[lang]["enter_name"])
    await state.set_state(Registration.name)

@dp.message(Registration.name)
async def enter_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer(TEXTS[users[message.from_user.id]["lang"]]["enter_age"])
    await state.set_state(Registration.age)

@dp.message(Registration.age)
async def enter_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer(TEXTS[users[message.from_user.id]["lang"]]["age_error"])
        return
    await state.update_data(age=int(message.text))
    lang = users[message.from_user.id]["lang"]
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=TEXTS[lang]["male"]), KeyboardButton(text=TEXTS[lang]["female"])]], resize_keyboard=True)
    await message.answer(TEXTS[lang]["choose_gender"], reply_markup=kb)
    await state.set_state(Registration.gender)

@dp.message(Registration.gender)
async def enter_gender(message: types.Message, state: FSMContext):
    data = await state.get_data()
    gender = "male" if any(x in message.text for x in ["Парень", "Male"]) else "female"
    uid = message.from_user.id
    users[uid].update({"name": data["name"], "age": data["age"], "gender": gender})
    await state.clear()

    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="1️⃣ Просто общение")],
        [KeyboardButton(text="2️⃣ Флирт")],
        [KeyboardButton(text="3️⃣ Kink / ролевые (18+)")]
    ], resize_keyboard=True)
    await message.answer(TEXTS[users[uid]["lang"]]["choose_mode"], reply_markup=kb)
    await state.set_state(Registration.mode)

@dp.message(Registration.mode)
async def choose_mode(message: types.Message, state: FSMContext):
    text = message.text.lower()
    uid = message.from_user.id
    if "просто" in text:
        mode = "simple"
        interests_list = ["Разговор по душам", "Юмор и мемы", "Советы по жизни", "Книги и фильмы", "Музыка"]
    elif "флирт" in text:
        mode = "flirt"
        interests_list = ["Лёгкий флирт", "Комплименты", "Секстинг", "Романтика", "Игривый настрой"]
    else:
        mode = "kink"
        interests_list = ["BDSM", "Bondage", "Roleplay", "Dominance/Sub", "Foot fetish", "Pet play", "Impact play"]

    users[uid]["mode"] = mode
    users[uid]["temp_interests"] = []
    await state.update_data(mode=mode)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=interest, callback_data=f"interest:{interest}")]
        for interest in interests_list
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="interests_done")])

    await message.answer(TEXTS[users[uid]["lang"]]["choose_interests"], reply_markup=kb)
    await state.set_state(Registration.interests)

@dp.callback_query(F.data.startswith("interest:"))
async def add_interest(callback: types.CallbackQuery):
    uid = callback.from_user.id
