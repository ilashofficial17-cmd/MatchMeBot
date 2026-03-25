import asyncio
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, 
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
)

# ====================== НАСТРОЙКИ ======================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден!")

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
        "age_error": "Пожалуйста, введи число от 16 до 99",
        "done": "✅ Готово",
    }
}

# ====================== КЛАВИАТУРЫ ======================
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
        [KeyboardButton(text="🔄 Перезапустить")],   # Добавил обратно
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def get_cancel_search_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить поиск")]], resize_keyboard=True)

# ====================== УТИЛИТЫ (из кода Джиммини) ======================
async def remove_from_queues(uid):
    for q in [waiting_queue_simple, waiting_queue_flirt, waiting_queue_kink]:
        if uid in q: 
            q.remove(uid)

async def cleanup_user_chat(uid, state: FSMContext = None):
    await remove_from_queues(uid)
    partner_id = active_chats.pop(uid, None)
    if partner_id:
        active_chats.pop(partner_id, None)
    if state:
        await state.clear()
    return partner_id

# ====================== КОМАНДЫ ======================
async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🚀 Запуск / Регистрация"),
        BotCommand(command="find", description="🔍 Найти собеседника"),
        BotCommand(command="next", description="🔄 Следующий"),
        BotCommand(command="stop", description="❌ Завершить чат"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="help", description="❓ Помощь")
    ]
    await bot.set_my_commands(commands)

# ====================== СТАРТ ======================
@dp.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    await cleanup_user_chat(message.from_user.id, state)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]], resize_keyboard=True)
    await message.answer("🌐 Выбери язык:", reply_markup=kb)
    await state.set_state(Registration.language)

@dp.message(F.text.contains("Перезапустить"), StateFilter("*"))
async def cmd_restart(message: types.Message, state: FSMContext):
    partner_id = await cleanup_user_chat(message.from_user.id, state)
    if partner_id:
        try:
            await bot.send_message(partner_id, "😔 Собеседник перезапустил бота. Чат завершён.", reply_markup=get_main_menu())
            key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=key).clear()
        except: pass
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
        mode, interests_list = "simple", ["Разговор по душам", "Юмор и мемы", "Советы по жизни"]
    elif "флирт" in text:
        mode, interests_list = "flirt", ["Лёгкий флирт", "Комплименты", "Секстинг"]
    else:
        mode, interests_list = "kink", ["BDSM", "Bondage", "Roleplay"]

    users[uid]["mode"] = mode
    users[uid]["temp_interests"] = []
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=i, callback_data=f"interest:{i}")] for i in interests_list
    ] + [[InlineKeyboardButton(text="✅ Готово", callback_data="done")]])

    await message.answer(TEXTS[users[uid]["lang"]]["choose_interests"], reply_markup=kb)
    await state.set_state(Registration.interests)

@dp.callback_query(F.data.startswith("interest:"), StateFilter(Registration.interests))
async def add_interest(callback: types.CallbackQuery):
    uid = callback.from_user.id
    interest = callback.data.split(":", 1)[1]
    if "temp_interests" not in users.get(uid, {}):
        users[uid]["temp_interests"] = []
    if interest not in users[uid]["temp_interests"]:
        users[uid]["temp_interests"].append(interest)
        await callback.answer(f"✅ Добавлено: {interest}")
    else:
        await callback.answer("Уже в списке")

# ====================== ИСПРАВЛЕННАЯ ФУНКЦИЯ (главный фикс) ======================
@dp.callback_query(F.data == "done", StateFilter(Registration.interests))
async def finish_interests(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    users[uid]["interests"] = users[uid].get("temp_interests", [])[:3]
    users[uid].pop("temp_interests", None)
    
    await state.clear()
    
    # ФИКС: нельзя передавать ReplyKeyboardMarkup в edit_text
    await callback.message.edit_text("✅ Интересы сохранены!")
    await callback.message.answer("✅ Анкета полностью сохранена!\nТеперь можешь искать собеседника.", 
                                  reply_markup=get_main_menu())
    
    await callback.answer("Готово!")

# ====================== ПРОФИЛЬ И ПОМОЩЬ ======================
@dp.message(F.text.contains("Мой профиль"), StateFilter("*"))
@dp.message(Command("profile"), StateFilter("*"))
async def show_profile(message: types.Message):
    uid = message.from_user.id
    if uid not in users or "mode" not in users[uid]:
        await message.answer("Сначала заполни анкету! Нажми /start")
        return
    u = users[uid]
    gender_text = "Парень 👨" if u["gender"] == "male" else "Девушка 👩"
    mode_text = {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink"}.get(u["mode"], "—")
    await message.answer(f"👤 Профиль:\nИмя: {u['name']}\nВозраст: {u['age']}\nПол: {gender_text}\nРежим: {mode_text}\nИнтересы: {', '.join(u.get('interests', []))}")

@dp.message(F.text.contains("Помощь"), StateFilter("*"))
@dp.message(Command("help"), StateFilter("*"))
async def show_help(message: types.Message):
    await message.answer("🆘 Помощь:\nИспользуй кнопки меню или команды из списка слева.", reply_markup=get_main_menu())

# ====================== ПОИСК (оставил из твоей версии) ======================
@dp.message(F.text == "❌ Отменить поиск", StateFilter(Searching.waiting))
async def cancel_search(message: types.Message, state: FSMContext):
    await remove_from_queues(message.from_user.id)
    await state.clear()
    await message.answer("❌ Поиск отменён.", reply_markup=get_main_menu())

@dp.message(F.text.contains("Найти собеседника"), StateFilter("*"))
@dp.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in users or "mode" not in users[uid]:
        await message.answer("Сначала заполни анкету через /start")
        return
    if uid in active_chats:
        await message.answer("Ты уже в чате!")
        return

    mode = users[uid]["mode"]
    queue = waiting_queue_simple if mode == "simple" else waiting_queue_flirt if mode == "flirt" else waiting_queue_kink
    
    await message.answer(f"🔍 Ищем в режиме {mode}...", reply_markup=get_cancel_search_menu())

    async with pairing_lock:
        partner_id = None
        my_interests = set(users[uid].get("interests", []))

        for i in range(len(queue)):
            if queue[i] != uid and set(users[queue[i]].get("interests", [])) & my_interests:
                partner_id = queue.pop(i)
                break
        if not partner_id and queue:
            partner_id = queue.pop(0)

        if partner_id:
            active_chats[uid] = partner_id
            active_chats[partner_id] = uid

            await state.set_state(Searching.chatting)
            p_key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=p_key).set_state(Searching.chatting)

            for target in [uid, partner_id]:
                other = partner_id if target == uid else uid
                p = users[other]
                info = f"👤 Собеседник найден!\nИмя: {p.get('name','Аноним')}\nВозраст: {p.get('age','?')}\nПол: {'Парень' if p.get('gender')=='male' else 'Девушка'}\nРежим: {mode}\nИнтересы: {', '.join(p.get('interests', []))}"
                await bot.send_message(target, info)
                await bot.send_message(target, TEXTS[users[target]["lang"]]["found"], reply_markup=get_chat_menu())
        else:
            queue.append(uid)
            await state.set_state(Searching.waiting)

# ====================== УПРАВЛЕНИЕ ЧАТОМ ======================
@dp.message(F.text == "🔄 Следующий собеседник", StateFilter("*"))
@dp.message(Command("next"), StateFilter("*"))
async def next_partner(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    partner_id = await cleanup_user_chat(uid, state)
    if partner_id:
        try:
            await bot.send_message(partner_id, "😔 Собеседник переключился.", reply_markup=get_main_menu())
        except: pass
    await cmd_find(message, state)

@dp.message(F.text.in_(["❌ Завершить чат", "🏠 Главное меню"]), StateFilter("*"))
@dp.message(Command("stop"), StateFilter("*"))
async def end_chat(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    partner_id = await cleanup_user_chat(uid, state)
    await message.answer("💔 Чат завершён.", reply_markup=get_main_menu())
    if partner_id:
        try:
            await bot.send_message(partner_id, "😔 Собеседник покинул чат.", reply_markup=get_main_menu())
        except: pass

@dp.message(F.text == "🚩 Пожаловаться", StateFilter("*"))
async def complain(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    partner_id = await cleanup_user_chat(uid, state)
    if partner_id:
        await message.answer("🚩 Жалоба отправлена. Чат завершён.", reply_markup=get_main_menu())
        try:
            await bot.send_message(partner_id, "😔 На тебя поступила жалоба.", reply_markup=get_main_menu())
        except: pass
    else:
        await message.answer("Ты не в чате.")

# ====================== ПЕРЕСЫЛКА ======================
@dp.message(Searching.chatting)
async def relay_message(message: types.Message):
    if message.text in ["🔄 Следующий собеседник", "❌ Завершить чат", "🚩 Пожаловаться", "🏠 Главное меню", "🔄 Перезапустить"]:
        return
    partner_id = active_chats.get(message.from_user.id)
    if not partner_id:
        return
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

# ====================== ЗАПУСК ======================
async def main():
    await set_bot_commands(bot)
    print("🚀 Бот запущен! (структура Джиммини + исправленные ошибки)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

