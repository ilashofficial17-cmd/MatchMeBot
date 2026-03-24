import logging
import asyncio
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
        "welcome": "👋 Привет! Добро пожаловать в MatchMe",
        "enter_name": "Как тебя зовут? (будет видно собеседнику)",
        "enter_age": "Сколько тебе лет?",
        "choose_gender": "Выбери свой пол:",
        "profile_saved": "✅ Анкета сохранена!",
        "searching": "🔍 Ищем собеседника...",
        "found": "✅ Собеседник найден! Можете общаться анонимно.",
        "chat_ended": "💔 Чат завершён.",
        "partner_left": "😔 Собеседник покинул чат.",
        "male": "👨 Парень",
        "female": "👩 Девушка",
        "age_error": "Введите число от 16 до 99",
        "already_chatting": "Ты уже в чате!",
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
        [KeyboardButton(text="❌ Завершить чат")]
    ], resize_keyboard=True)

# Главное меню
@dp.message(Command("start", "menu"))
async def show_menu(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    if uid in active_chats:
        await message.answer("Ты в чате. Используй кнопки ниже ↓", reply_markup=get_chat_menu())
    else:
        await message.answer("🏠 Главное меню MatchMe", reply_markup=get_main_menu())

@dp.message(F.text.casefold().contains("перезапустить"))
async def cmd_restart(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    if uid in active_chats:
        partner = active_chats.pop(uid, None)
        active_chats.pop(partner, None)
    if uid in waiting_queue:
        waiting_queue.remove(uid)
    await message.answer("🔄 Всё сброшено. Начинаем заново!", reply_markup=get_main_menu())

# Регистрация (оставил как было, только чуть короче)
@dp.message(Registration.language)
async def choose_language(message: types.Message, state: FSMContext):
    lang = "ru" if "Русский" in message.text else "en"
    users[message.from_user.id] = {"lang": lang}
    await state.update_data(lang=lang)
    await message.answer(TEXTS[lang]["welcome"], reply_markup=ReplyKeyboardRemove())
    await message.answer(TEXTS[lang]["enter_name"])
    await state.set_state(Registration.name)

# ... (остальные функции регистрации enter_name, enter_age, enter_gender — оставь как в предыдущей версии, они не менялись)

@dp.message(F.text.casefold().contains("мой профиль"))
async def show_profile(message: types.Message):
    uid = message.from_user.id
    if uid not in users or "name" not in users[uid]:
        await message.answer(TEXTS.get(users.get(uid, {}).get("lang", "ru"), TEXTS["ru"])["need_profile"])
        return
    u = users[uid]
    gender = "Парень 👨" if u["gender"] == "male" else "Девушка 👩"
    await message.answer(f"👤 Твой профиль:\nИмя: {u['name']}\nВозраст: {u['age']}\nПол: {gender}")

@dp.message(F.text.casefold().contains("помощь"))
async def show_help(message: types.Message):
    await message.answer("🆘 Помощь:\n\nНажимай кнопки в меню.\nВ чате используй «Следующий» или «Завершить чат».", reply_markup=get_main_menu())

# Поиск
@dp.message(F.text.casefold().contains("найти собеседника"))
@dp.message(Command("find"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in users or "name" not in users[uid]:
        await message.answer("Сначала заполни анкету — нажми «🔄 Перезапустить»")
        return
    if uid in active_chats:
        await message.answer("Ты уже в чате!")
        return

    async with pairing_lock:
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
            await FSMContext(storage=dp.storage, key=key).set_state(Searching.chatting)

            # Профиль
            p = users.get(partner_id, {})
            profile = f"👤 Собеседник найден!\nИмя: {p.get('name','Аноним')}\nВозраст: {p.get('age','?')}\nПол: {'Парень' if p.get('gender')=='male' else 'Девушка'}"
            await bot.send_message(uid, profile)
            await bot.send_message(partner_id, profile.replace(p.get('name','Аноним'), users[uid].get('name','Аноним')))

            await bot.send_message(uid, TEXTS[users[uid]["lang"]]["found"], reply_markup=get_chat_menu())
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["found"], reply_markup=get_chat_menu())
        else:
            waiting_queue.append(uid)
            await state.set_state(Searching.waiting)
            await message.answer(TEXTS[users[uid]["lang"]]["searching"])

# Кнопки в чате + /stop
@dp.message(F.text.casefold().contains("завершить чат"))
@dp.message(F.text.casefold().contains("следующий"))
@dp.message(Command("stop"))
async def cmd_stop_or_next(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    is_next = "следующий" in message.text.lower() if message.text else False

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

        if is_next:
            await asyncio.sleep(0.5)
            await cmd_find(message, state)
    else:
        await message.answer("Ты не в чате.", reply_markup=get_main_menu())

# Пересылка + "печатает"
@dp.message(Searching.chatting)
async def relay_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await state.clear()
        return

    partner_id = active_chats[uid]

    # Показываем "печатает"
    try:
        await bot.send_chat_action(partner_id, "typing")
    except:
        pass

    # Пересылаем
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
        print(f"Relay error: {e}")

async def main():
    print("🚀 Бот запущен с исправленными кнопками!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
