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
        "male": "👨 Парень",
        "female": "👩 Девушка",
        "age_error": "Пожалуйста введи число от 16 до 99",
        "need_profile": "Сначала заполни анкету",
        "done": "✅ Готово",
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
        [KeyboardButton(text="🚩 Пожаловаться")],
        [KeyboardButton(text="🔄 Перезапустить")],   # ← Добавлена здесь
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def get_cancel_search_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить поиск")]], resize_keyboard=True)

# ====================== СТАРТ ======================
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
        interests_list = ["Разговор по душам", "Юмор и мемы", "Советы по жизни"]
    elif "флирт" in text:
        mode = "flirt"
        interests_list = ["Лёгкий флирт", "Комплименты", "Секстинг"]
    else:
        mode = "kink"
        interests_list = ["BDSM", "Bondage", "Roleplay"]

    users[uid]["mode"] = mode
    users[uid]["temp_interests"] = []
    await state.update_data(mode=mode)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=i, callback_data=f"interest:{i}")]
        for i in interests_list
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="done")])

    await message.answer(TEXTS[users[uid]["lang"]]["choose_interests"], reply_markup=kb)
    await state.set_state(Registration.interests)

@dp.callback_query(F.data.startswith("interest:"))
async def add_interest(callback: types.CallbackQuery):
    uid = callback.from_user.id
    interest = callback.data.split(":", 1)[1]
    if "temp_interests" not in users[uid]:
        users[uid]["temp_interests"] = []
    if interest not in users[uid]["temp_interests"]:
        users[uid]["temp_interests"].append(interest)
    await callback.answer("Добавлено")

@dp.callback_query(F.data == "done")
async def finish_interests(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    interests = users[uid].get("temp_interests", [])[:3]
    users[uid]["interests"] = interests
    if "temp_interests" in users[uid]:
        del users[uid]["temp_interests"]
    await state.clear()
    await callback.message.edit_text("✅ Интересы сохранены!")
    await callback.message.answer(TEXTS[users[uid]["lang"]]["profile_saved"], reply_markup=get_main_menu())
    await callback.answer()

# ====================== МЕНЮ ======================
@dp.message(F.text.contains("Мой профиль"))
async def show_profile(message: types.Message):
    uid = message.from_user.id
    if uid not in users or "mode" not in users[uid]:
        await message.answer("Сначала заполни анкету!")
        return
    u = users[uid]
    gender_text = "Парень 👨" if u["gender"] == "male" else "Девушка 👩"
    mode_text = {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink / ролевые"}.get(u["mode"], "—")
    interests_text = ", ".join(u.get("interests", [])) or "—"
    await message.answer(f"👤 Твой профиль:\nИмя: {u['name']}\nВозраст: {u['age']}\nПол: {gender_text}\nРежим: {mode_text}\nИнтересы: {interests_text}")

@dp.message(F.text.contains("Помощь"))
async def show_help(message: types.Message):
    await message.answer("🆘 Помощь:\nНажимай кнопки меню.\nЕсли что-то сломалось — нажми «🔄 Перезапустить»", reply_markup=get_main_menu())

# ====================== ПОИСК ======================
@dp.message(F.text.contains("Найти собеседника"))
@dp.message(Command("find"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in users or "mode" not in users[uid]:
        await message.answer("Сначала заполни анкету!")
        return
    if uid in active_chats:
        await message.answer("Ты уже в чате!")
        return

    mode = users[uid]["mode"]
    mode_name = {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink"}.get(mode, "—")
    online = len(waiting_queue_simple if mode == "simple" else waiting_queue_flirt if mode == "flirt" else waiting_queue_kink)

    await message.answer(f"👥 Сейчас онлайн в режиме **{mode_name}**: **{online}** человек\n\n🔍 Начинаем поиск...", reply_markup=get_cancel_search_menu())

    async with pairing_lock:
        partner_id = None
        my_interests = set(users[uid].get("interests", []))

        if mode == "simple":
            queue = waiting_queue_simple
            fallback = None
        elif mode == "flirt":
            queue = waiting_queue_flirt
            fallback = waiting_queue_kink
        else:
            queue = waiting_queue_kink
            fallback = waiting_queue_flirt

        for i in range(len(queue)):
            if queue[i] != uid and set(users[queue[i]].get("interests", [])) & my_interests:
                partner_id = queue.pop(i)
                break

        if not partner_id and queue:
            partner_id = queue.pop(0)

        if not partner_id and fallback:
            for i in range(len(fallback)):
                if fallback[i] != uid:
                    partner_id = fallback.pop(i)
                    break

        if partner_id
