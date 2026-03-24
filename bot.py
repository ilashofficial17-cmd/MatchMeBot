import logging
import asyncio
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

# Хранилище
users = {}
waiting_queue = []
active_chats = {}
pairing_lock = asyncio.Lock()

class Registration(StatesGroup):
    language = State()
    name = State()
    age = State()
    gender = State()

class Searching(StatesGroup):
    waiting = State()
    chatting = State()

TEXTS = {
    "ru": {
        "welcome": "👋 Привет! Добро пожаловать в MatchMe — анонимный чат для знакомств.",
        "enter_name": "Как тебя зовут? (будет видно собеседнику)",
        "enter_age": "Сколько тебе лет?",
        "choose_gender": "Выбери свой пол:",
        "profile_saved": "✅ Анкета успешно сохранена!",
        "searching": "🔍 Ищем тебе собеседника...\n\nНапиши /stop или нажми кнопку ниже, чтобы отменить.",
        "found": "✅ Собеседник найден!",
        "stopped_searching": "❌ Поиск отменён.",
        "chat_ended": "💔 Чат завершён.",
        "partner_left": "😔 Собеседник покинул чат.",
        "male": "👨 Парень",
        "female": "👩 Девушка",
        "age_error": "Пожалуйста, введи число от 16 до 99.",
        "already_chatting": "Ты уже в чате!",
        "need_profile": "Сначала заполни анкету с помощью /start",
    }
}

def t(user_id, key, **kwargs):
    lang = users.get(user_id, {}).get("lang", "ru")
    text = TEXTS[lang].get(key, key)
    return text.format(**kwargs) if kwargs else text

# ==================== ГЛАВНОЕ МЕНЮ ====================
def get_main_menu():
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти собеседника")],
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)
    return kb

# ==================== START И РЕГИСТРАЦИЯ ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]
    ], resize_keyboard=True)
    await message.answer("🌐 Выбери язык:", reply_markup=kb)
    await state.set_state(Registration.language)

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
    await state.update_data(name=message.text)
    await message.answer(TEXTS[users[message.from_user.id]["lang"]]["enter_age"])
    await state.set_state(Registration.age)

@dp.message(Registration.age)
async def enter_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer(TEXTS[users[message.from_user.id]["lang"]]["age_error"])
        return
    await state.update_data(age=int(message.text))
    lang = users[message.from_user.id]["lang"]
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=TEXTS[lang]["male"]), KeyboardButton(text=TEXTS[lang]["female"])]
    ], resize_keyboard=True)
    await message.answer(TEXTS[lang]["choose_gender"], reply_markup=kb)
    await state.set_state(Registration.gender)

@dp.message(Registration.gender)
async def enter_gender(message: types.Message, state: FSMContext):
    data = await state.get_data()
    gender = "male" if "Парень" in message.text or "Male" in message.text else "female"
    users[message.from_user.id].update({
        "name": data["name"],
        "age": data["age"],
        "gender": gender,
        "lang": data.get("lang", "ru")
    })
    await state.clear()
    await message.answer(TEXTS[users[message.from_user.id]["lang"]]["profile_saved"], reply_markup=get_main_menu())

# ==================== ГЛАВНОЕ МЕНЮ ====================
@dp.message(Command("menu"))
@dp.message(F.text == "❓ Помощь")
async def show_menu(message: types.Message):
    await message.answer("🏠 Главное меню:", reply_markup=get_main_menu())

@dp.message(F.text == "👤 Мой профиль")
async def cmd_profile(message: types.Message):
    uid = message.from_user.id
    if uid not in users or "name" not in users[uid]:
        await message.answer(TEXTS[users.get(uid, {}).get("lang", "ru")]["need_profile"])
        return
    u = users[uid]
    lang = u["lang"]
    gender_text = TEXTS[lang]["male"] if u["gender"] == "male" else TEXTS[lang]["female"]
    await message.answer(f"👤 Твой профиль:\n\nИмя: {u['name']}\nВозраст: {u['age']}\nПол: {gender_text}")

# ==================== ПОИСК СОБЕСЕДНИКА ====================
@dp.message(F.text == "🔍 Найти собеседника")
@dp.message(Command("find"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    print(f"[DEBUG] /find от {uid}")

    if uid not in users or "name" not in users[uid]:
        await message.answer(TEXTS[users.get(uid, {}).get("lang", "ru")]["need_profile"])
        return
    if uid in active_chats:
        await message.answer(TEXTS[users[uid]["lang"]]["already_chatting"])
        return

    async with pairing_lock:
        if uid in waiting_queue:
            await message.answer("🔄 Ты уже в поиске...")
            return

        partner_id = None
        for i in range(len(waiting_queue)):
            if waiting_queue[i] != uid:
                partner_id = waiting_queue.pop(i)
                break

        if partner_id:
            active_chats[uid] = partner_id
            active_chats[partner_id] = uid

            await state.set_state(Searching.chatting)

            key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            partner_state = FSMContext(storage=dp.storage, key=key)
            await partner_state.set_state(Searching.chatting)

            # Показ профиля
            partner = users.get(partner_id, {})
            p_name = partner.get("name", "Аноним")
            p_age = partner.get("age", "?")
            p_gender = "Парень" if partner.get("gender") == "male" else "Девушка"

            profile_text = f"👤 Собеседник найден!\n\nИмя: {p_name}\nВозраст: {p_age}\nПол: {p_gender}\n\nМожете общаться анонимно."

            await bot.send_message(uid, profile_text)
            await bot.send_message(partner_id, profile_text.replace(p_name, users[uid].get("name", "Аноним")))

            await bot.send_message(uid, TEXTS[users[uid]["lang"]]["found"])
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["found"])

            # Кнопки в чате
            chat_kb = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="🔄 Следующий")],
                [KeyboardButton(text="❌ Завершить чат")]
            ], resize_keyboard=True)
            await bot.send_message(uid, "Управление чатом:", reply_markup=chat_kb)
            await bot.send_message(partner_id, "Управление чатом:", reply_markup=chat_kb)

        else:
            waiting_queue.append(uid)
            await state.set_state(Searching.waiting)
            await message.answer(TEXTS[users[uid]["lang"]]["searching"])

# ==================== ОБРАБОТКА КНОПОК В ЧАТЕ ====================
@dp.message(F.text == "❌ Завершить чат")
@dp.message(F.text == "🔄 Следующий")
@dp.message(Command("stop"))
async def cmd_stop_or_next(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    is_next = "Следующий" in (message.text or "")

    if uid in active_chats:
        partner_id = active_chats.pop(uid)
        active_chats.pop(partner_id, None)
        await state.clear()

        await message.answer(TEXTS[users[uid]["lang"]]["chat_ended"])

        try:
            msg = "😔 Собеседник ищет нового..." if is_next else TEXTS[users[partner_id]["lang"]]["partner_left"]
            await bot.send_message(partner_id, msg)
        except:
            pass

        if is_next:
            await cmd_find(message, state)
        else:
            await message.answer("🏠 Возвращаемся в меню", reply_markup=get_main_menu())
    else:
        await message.answer(TEXTS[users.get(uid, {}).get("lang", "ru")]["stopped_searching"])

# ==================== ПЕЧАТАЕТ... ====================
@dp.message(Searching.chatting, F.text)
async def typing_indicator(message: types.Message):
    uid = message.from_user.id
    if uid not in active_chats:
        return
    try:
        await bot.send_chat_action(active_chats[uid], "typing")
    except:
        pass

# ==================== ПЕРЕСЫЛКА СООБЩЕНИЙ ====================
@dp.message(Searching.chatting)
async def relay_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await state.clear()
        return
    partner_id = active_chats[uid]

    key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
    partner_state = FSMContext(storage=dp.storage, key=key)
    await partner_state.set_state(Searching.chatting)

    try:
        if message.text:
            await bot.send_message(partner_id, message.text)
        elif message.sticker:
            await bot.send_sticker(partner_id, message.sticker.file_id)
        elif message.photo:
            await bot.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption)
        elif message.voice:
            await bot.send_voice(partner_id, message.voice.file_id)
    except Exception as e:
        print(f"[ERROR] {e}")

async def main():
    print("🚀 MatchMe бот запущен!")
    print("   ✅ Красивое меню")
    print("   ✅ Удобные кнопки")
    print("   ✅ Профиль при подключении")
    print("   ✅ Кнопки в чате")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
