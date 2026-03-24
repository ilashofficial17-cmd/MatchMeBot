import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
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

# ====================== РЕГИСТРАЦИЯ (упрощённая для стабильности) ======================
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
    await message.answer(TEXTS[users[uid]["lang"]]["profile_saved"], reply_markup=get_main_menu())

# ====================== МЕНЮ ======================
@dp.message(F.text.contains("Мой профиль"))
async def show_profile(message: types.Message):
    uid = message.from_user.id
    if uid not in users or "name" not in users[uid]:
        await message.answer("Сначала заполни анкету!")
        return
    u = users[uid]
    gender_text = "Парень 👨" if u["gender"] == "male" else "Девушка 👩"
    await message.answer(f"👤 Твой профиль:\nИмя: {u['name']}\nВозраст: {u['age']}\nПол: {gender_text}")

@dp.message(F.text.contains("Помощь"))
async def show_help(message: types.Message):
    await message.answer("🆘 Помощь:\nНажимай кнопки меню.\nЕсли что-то сломалось — нажми «🔄 Перезапустить»", reply_markup=get_main_menu())

# ====================== ПОИСК ======================
@dp.message(F.text.contains("Найти собеседника"))
@dp.message(Command("find"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in users or "name" not in users[uid]:
        await message.answer("Сначала заполни анкету!")
        return
    if uid in active_chats:
        await message.answer("Ты уже в чате!")
        return

    await message.answer("🔍 Начинаем поиск...", reply_markup=get_cancel_search_menu())

    async with pairing_lock:
        partner_id = None
        if waiting_queue_simple:
            partner_id = waiting_queue_simple.pop(0)
        else:
            waiting_queue_simple.append(uid)
            await state.set_state(Searching.waiting)
            return

        if partner_id:
            active_chats[uid] = partner_id
            active_chats[partner_id] = uid

            await state.set_state(Searching.chatting)
            key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=key).set_state(Searching.chatting)

            await bot.send_message(uid, TEXTS[users[uid]["lang"]]["found"], reply_markup=get_chat_menu())
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["found"], reply_markup=get_chat_menu())

# ====================== КНОПКИ В ЧАТЕ ======================
@dp.message(F.text == "🔄 Следующий собеседник")
async def next_partner(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid in active_chats:
        partner_id = active_chats.pop(uid, None)
        if partner_id:
            active_chats.pop(partner_id, None)
        await state.clear()
    await cmd_find(message, state)

@dp.message(F.text == "❌ Завершить чат")
async def end_chat(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid in active_chats:
        partner_id = active_chats.pop(uid, None)
        if partner_id:
            active_chats.pop(partner_id, None)
        await state.clear()
        await message.answer(TEXTS[users[uid]["lang"]]["chat_ended"], reply_markup=get_main_menu())
        try:
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["partner_left"], reply_markup=get_main_menu())
        except:
            pass

@dp.message(F.text == "🚩 Пожаловаться")
async def complain(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await message.answer("Ты не в чате")
        return
    partner_id = active_chats.pop(uid, None)
    if partner_id:
        active_chats.pop(partner_id, None)
    await state.clear()
    await message.answer("🚩 Жалоба отправлена. Чат завершён.")
    try:
        await bot.send_message(partner_id, "😔 На тебя поступила жалоба. Чат завершён.")
    except:
        pass

@dp.message(F.text == "🏠 Главное меню")
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Возвращаемся в главное меню", reply_markup=get_main_menu())

# ====================== ПЕРЕСЫЛКА СООБЩЕНИЙ ======================
@dp.message(Searching.chatting)
async def relay_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await state.clear()
        return
    partner_id = active_chats[uid]

    try:
        if message.text:
            await bot.send_message(partner_id, message.text)
        elif message.sticker:
            await bot.send_sticker(partner_id, message.sticker.file_id)
        elif message.photo:
            await bot.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption)
        elif message.voice:
            await bot.send_voice(partner_id, message.voice.file_id)
    except:
        pass

async def main():
    print("🚀 Бот запущен с новым меню в чате!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
