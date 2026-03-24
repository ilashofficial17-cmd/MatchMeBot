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
last_message_time = {}
message_count = {}
complaints = {}
bans = {}
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
        "complain_sent": "🚩 Жалоба отправлена. Чат завершён.",
        "banned": "🚫 Ты забанен за жалобы на 24 часа.",
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
        [KeyboardButton(text="🔄 Следующий")],
        [KeyboardButton(text="❌ Завершить чат")],
        [KeyboardButton(text="🚩 Пожаловаться")],
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def get_cancel_search_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить поиск")]], resize_keyboard=True)

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid in bans and bans[uid] > datetime.now():
        await message.answer(TEXTS["ru"]["banned"])
        return
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

# (Регистрация остаётся как в последней рабочей версии — с кнопками для интересов. 
# Если нужно — могу добавить её полностью, но чтобы не делать сообщение огромным, предполагаю, что она у тебя уже есть)

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

    # ... (логика поиска остаётся как была раньше — она рабочая)

    async with pairing_lock:
        partner_id = None
        # ... (твой код поиска)

        if partner_id:
            active_chats[uid] = partner_id
            active_chats[partner_id] = uid
            last_message_time[uid] = last_message_time[partner_id] = datetime.now()

            await state.set_state(Searching.chatting)
            key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=key).set_state(Searching.chatting)

            # Показ профиля (как раньше)
            p = users.get(partner_id, {})
            profile_text = f"👤 Собеседник найден!\nИмя: {p.get('name','Аноним')}\nВозраст: {p.get('age','?')}\nПол: {'Парень' if p.get('gender')=='male' else 'Девушка'}\nРежим: {p.get('mode','—')}\nИнтересы: {', '.join(p.get('interests', [])) or '—'}"

            await bot.send_message(uid, profile_text)
            await bot.send_message(partner_id, profile_text.replace(p.get('name','Аноним'), users[uid].get('name','Аноним')))

            await bot.send_message(uid, TEXTS[users[uid]["lang"]]["found"], reply_markup=get_chat_menu())
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["found"], reply_markup=get_chat_menu())
        else:
            if mode == "simple":
                waiting_queue_simple.append(uid)
            elif mode == "flirt":
                waiting_queue_flirt.append(uid)
            else:
                waiting_queue_kink.append(uid)
            await state.set_state(Searching.waiting)

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

    complaints[partner_id] = complaints.get(partner_id, 0) + 1
    await message.answer(TEXTS[users[uid]["lang"]]["complain_sent"])

    try:
        await bot.send_message(partner_id, "😔 На тебя поступила жалоба. Чат завершён.")
    except:
        pass

    if complaints.get(partner_id, 0) >= 3:
        bans[partner_id] = datetime.now() + timedelta(hours=24)
        try:
            await bot.send_message(partner_id, "🚫 Ты получил 3 жалобы и забанен на 24 часа.")
        except:
            pass

@dp.message(F.text == "🏠 Главное меню")
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Возвращаемся в главное меню", reply_markup=get_main_menu())

# ====================== ЧАТ ======================
@dp.message(Searching.chatting)
async def relay_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await state.clear()
        return
    partner_id = active_chats[uid]

    # Анти-флуд
    now = datetime.now()
    if uid not in message_count:
        message_count[uid] = []
    message_count[uid] = [t for t in message_count[uid] if (now - t).total_seconds() < 5]
    message_count[uid].append(now)
    if len(message_count[uid]) > 4:
        await message.answer(TEXTS[users[uid]["lang"]]["flood_warning"])
        return

    last_message_time[uid] = last_message_time[partner_id] = now

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
