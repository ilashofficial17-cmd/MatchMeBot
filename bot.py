import asyncio
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Проверка токена, чтобы бот не падал с непонятной ошибкой при запуске
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Базы данных в памяти
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
        "need_profile": "Сначала заполни анкету",
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
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def get_cancel_search_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить поиск")]], resize_keyboard=True)

# ====================== УТИЛИТЫ ======================
async def remove_from_queues(uid):
    """Удаляет пользователя из всех очередей поиска"""
    for q in [waiting_queue_simple, waiting_queue_flirt, waiting_queue_kink]:
        if uid in q:
            q.remove(uid)

async def cleanup_user_chat(uid, state: FSMContext = None):
    """Безопасно очищает текущий чат и состояние пользователя"""
    await remove_from_queues(uid)
    partner_id = active_chats.pop(uid, None)
    if partner_id:
        active_chats.pop(partner_id, None)
    if state:
        await state.clear()
    return partner_id

# ====================== СТАРТ И БАЗОВЫЕ КОМАНДЫ ======================
@dp.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    await cleanup_user_chat(message.from_user.id, state)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]], resize_keyboard=True)
    await message.answer("🌐 Выбери язык / Choose language:", reply_markup=kb)
    await state.set_state(Registration.language)

@dp.message(F.text.contains("Перезапустить"), StateFilter("*"))
async def cmd_restart(message: types.Message, state: FSMContext):
    partner_id = await cleanup_user_chat(message.from_user.id, state)
    if partner_id:
        try:
            await bot.send_message(partner_id, "😔 Собеседник перезапустил бота. Чат завершён.", reply_markup=get_main_menu())
            # Сбрасываем состояние партнера
            key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=key).clear()
        except:
            pass
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
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=i, callback_data=f"interest:{i}")]
        for i in interests_list
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="done")])

    await message.answer(TEXTS[users[uid]["lang"]]["choose_interests"], reply_markup=ReplyKeyboardRemove())
    await message.answer("Выбирай:", reply_markup=kb)
    await state.set_state(Registration.interests)

@dp.callback_query(F.data.startswith("interest:"), StateFilter(Registration.interests))
async def add_interest(callback: types.CallbackQuery):
    uid = callback.from_user.id
    interest = callback.data.split(":", 1)[1]
    
    # Безопасная инициализация на случай непредвиденных сбоев
    if uid not in users:
        users[uid] = {"lang": "ru"}
    if "temp_interests" not in users[uid]:
        users[uid]["temp_interests"] = []
        
    if interest not in users[uid]["temp_interests"]:
        users[uid]["temp_interests"].append(interest)
        await callback.answer(f"✅ Добавлено: {interest}")
    else:
        await callback.answer("Уже добавлено!")

@dp.callback_query(F.data == "done", StateFilter(Registration.interests))
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

# ====================== МЕНЮ ПРОФИЛЯ ======================
@dp.message(F.text.contains("Мой профиль"), StateFilter("*"))
async def show_profile(message: types.Message):
    uid = message.from_user.id
    if uid not in users or "mode" not in users[uid]:
        await message.answer("Сначала заполни анкету! Нажми /start")
        return
    u = users[uid]
    gender_text = "Парень 👨" if u["gender"] == "male" else "Девушка 👩"
    mode_text = {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink / ролевые"}.get(u["mode"], "—")
    interests_text = ", ".join(u.get("interests", [])) or "Не выбраны"
    await message.answer(f"👤 Твой профиль:\nИмя: {u.get('name', '—')}\nВозраст: {u.get('age', '—')}\nПол: {gender_text}\nРежим: {mode_text}\nИнтересы: {interests_text}")

@dp.message(F.text.contains("Помощь"), StateFilter("*"))
async def show_help(message: types.Message):
    await message.answer("🆘 Помощь:\nИспользуй кнопки меню для навигации.\nЕсли всё зависло — жми «🔄 Перезапустить»", reply_markup=get_main_menu())

# ====================== ЛОГИКА ПОИСКА И ЧАТА ======================
@dp.message(F.text == "❌ Отменить поиск", StateFilter(Searching.waiting))
async def cancel_search(message: types.Message, state: FSMContext):
    await remove_from_queues(message.from_user.id)
    await state.clear()
    await message.answer("❌ Поиск отменен.", reply_markup=get_main_menu())

@dp.message(F.text.contains("Найти собеседника"), StateFilter("*"))
@dp.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in users or "mode" not in users[uid]:
        await message.answer("Сначала заполни анкету! Жми /start")
        return
    if uid in active_chats:
        await message.answer("Ты уже в чате! Если хочешь сменить собеседника, нажми «🔄 Следующий собеседник».")
        return

    mode = users[uid]["mode"]
    mode_name = {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink"}.get(mode, "—")
    
    queue = waiting_queue_simple if mode == "simple" else waiting_queue_flirt if mode == "flirt" else waiting_queue_kink
    
    # Защита от двойного добавления в очередь
    if uid in queue:
        await message.answer("🔍 Ты уже в поиске... Ожидай!", reply_markup=get_cancel_search_menu())
        return

    await message.answer(f"👥 Сейчас в очереди режима **{mode_name}**: {len(queue)} человек\n\n🔍 Начинаем поиск...", reply_markup=get_cancel_search_menu())

    async with pairing_lock:
        partner_id = None
        my_interests = set(users[uid].get("interests", []))

        fallback = None
        if mode == "flirt":
            fallback = waiting_queue_kink
        elif mode == "kink":
            fallback = waiting_queue_flirt

        # 1. Ищем по интересам
        for i in range(len(queue)):
            if queue[i] != uid and set(users[queue[i]].get("interests", [])) & my_interests:
                partner_id = queue.pop(i)
                break

        # 2. Ищем любого в своей очереди
        if not partner_id and queue:
            partner_id = queue.pop(0)

        # 3. Ищем в смежной очереди (флирт <-> кинк)
        if not partner_id and fallback:
            for i in range(len(fallback)):
                if fallback[i] != uid:
                    partner_id = fallback.pop(i)
                    break

        if partner_id:
            active_chats[uid] = partner_id
            active_chats[partner_id] = uid

            # Ставим статус "в чате" себе
            await state.set_state(Searching.chatting)
            
            # Ставим статус "в чате" партнеру
            key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=key).set_state(Searching.chatting)

            def get_profile_text(p_id):
                p = users.get(p_id, {})
                p_mode = {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink"}.get(p.get("mode"), "—")
                p_gender = "Парень 👨" if p.get("gender") == "male" else "Девушка 👩"
                p_interests = ", ".join(p.get("interests", [])) or "Не указаны"
                return f"👤 Собеседник найден!\nИмя: {p.get('name','Аноним')}\nВозраст: {p.get('age','?')}\nПол: {p_gender}\nРежим: {p_mode}\nИнтересы: {p_interests}"

            # Отправляем анкеты друг другу
            await bot.send_message(uid, get_profile_text(partner_id))
            await bot.send_message(partner_id, get_profile_text(uid))

            await bot.send_message(uid, TEXTS[users[uid]["lang"]]["found"], reply_markup=get_chat_menu())
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["found"], reply_markup=get_chat_menu())
        else:
            queue.append(uid)
            await state.set_state(Searching.waiting)

# ====================== КНОПКИ УПРАВЛЕНИЯ ЧАТОМ ======================
# Важно: StateFilter("*") позволяет этим кнопкам работать даже если состояние сбилось
@dp.message(F.text == "🔄 Следующий собеседник", StateFilter("*"))
async def next_partner(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    partner_id = await cleanup_user_chat(uid, state)
    
    if partner_id:
        try:
            partner_key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=partner_key).clear()
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["partner_left"], reply_markup=get_main_menu())
        except:
            pass
            
    await cmd_find(message, state)

@dp.message(F.text == "❌ Завершить чат", StateFilter("*"))
async def end_chat(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    partner_id = await cleanup_user_chat(uid, state)
    
    await message.answer(TEXTS[users[uid]["lang"]]["chat_ended"], reply_markup=get_main_menu())
    
    if partner_id:
        try:
            partner_key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=partner_key).clear()
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["partner_left"], reply_markup=get_main_menu())
        except:
            pass

@dp.message(F.text == "🚩 Пожаловаться", StateFilter("*"))
async def complain(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    partner_id = await cleanup_user_chat(uid, state)
    
    if not partner_id:
        await message.answer("Ты сейчас ни с кем не общаешься.", reply_markup=get_main_menu())
        return
        
    await message.answer("🚩 Жалоба отправлена модераторам. Чат завершён.", reply_markup=get_main_menu())
    try:
        partner_key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
        await FSMContext(dp.storage, key=partner_key).clear()
        await bot.send_message(partner_id, "😔 На тебя поступила жалоба от собеседника. Чат завершён.", reply_markup=get_main_menu())
    except:
        pass

@dp.message(F.text == "🏠 Главное меню", StateFilter("*"))
async def back_to_menu(message: types.Message, state: FSMContext):
    await end_chat(message, state) # Безопасно завершаем чат перед выходом в меню

# ====================== ПЕРЕСЫЛКА СООБЩЕНИЙ ======================
@dp.message(Searching.chatting)
async def relay_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await state.clear()
        return
    partner_id = active_chats[uid]

    # Игнорируем нажатия кнопок управления чатом, чтобы они не пересылались текстом
    if message.text in ["🔄 Следующий собеседник", "❌ Завершить чат", "🚩 Пожаловаться", "🏠 Главное меню"]:
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
        elif message.video:
            await bot.send_video(partner_id, message.video.file_id, caption=message.caption)
        elif message.video_note: # Кружочки
            await bot.send_video_note(partner_id, message.video_note.file_id)
        elif message.document:
            await bot.send_document(partner_id, message.document.file_id, caption=message.caption)
        else:
            await message.answer("⚠️ Этот тип сообщения пока не поддерживается.")
    except Exception:
        # Срабатывает, если собеседник заблокировал бота
        await end_chat(message, state)

# ====================== ЗАПУСК ======================
async def main():
    print("🚀 Бот запущен и готов к работе!")
    # Отбрасываем старые апдейты, чтобы бот не сошел с ума при включении
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот остановлен вручную.")
