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
waiting_queue_simple = []   # Просто общение
waiting_queue_flirt = []    # Флирт
waiting_queue_kink = []     # Kink
active_chats = {}
pairing_lock = asyncio.Lock()

class Registration(StatesGroup):
    language = State()
    name = State()
    age = State()
    gender = State()
    mode = State()          # Новый шаг
    interests = State()     # Новый шаг

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
        "choose_interests": "Напиши через запятую 1–3 интереса из списка ниже (или просто отправь свои):",
        "profile_saved": "✅ Анкета сохранена!",
        "searching": "🔍 Ищем собеседника по твоим интересам...",
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
        [KeyboardButton(text="❌ Завершить чат")]
    ], resize_keyboard=True)

# ====================== ПЕРЕЗАПУСК И СТАРТ ======================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]
    ], resize_keyboard=True)
    await message.answer("🌐 Выбери язык:", reply_markup=kb)
    await state.set_state(Registration.language)

@dp.message(F.text.contains("Перезапустить"))
async def cmd_restart(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    # Полная очистка
    if uid in active_chats:
        partner = active_chats.pop(uid, None)
        active_chats.pop(partner, None)
    for q in [waiting_queue_simple, waiting_queue_flirt, waiting_queue_kink]:
        if uid in q:
            q.remove(uid)
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
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=TEXTS[lang]["male"]), KeyboardButton(text=TEXTS[lang]["female"])]
    ], resize_keyboard=True)
    await message.answer(TEXTS[lang]["choose_gender"], reply_markup=kb)
    await state.set_state(Registration.gender)

@dp.message(Registration.gender)
async def enter_gender(message: types.Message, state: FSMContext):
    data = await state.get_data()
    gender = "male" if any(x in message.text for x in ["Парень", "Male"]) else "female"
    uid = message.from_user.id
    users[uid].update({"name": data["name"], "age": data["age"], "gender": gender})
    await state.clear()

    # Новый шаг — выбор режима
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
    if "просто" in text:
        mode = "simple"
        interests_text = "Разговор по душам, Юмор и мемы, Советы по жизни"
    elif "флирт" in text:
        mode = "flirt"
        interests_text = "Лёгкий флирт, Комплименты, Секстинг"
    else:
        mode = "kink"
        interests_text = "BDSM, Bondage, Roleplay, Dominance/Sub, Foot fetish, Pet play"

    users[message.from_user.id]["mode"] = mode
    await state.update_data(mode=mode)
    await message.answer(f"Выбран режим: {message.text}\n\nНапиши 1–3 интереса через запятую:\n{interests_text}")
    await state.set_state(Registration.interests)

@dp.message(Registration.interests)
async def choose_interests(message: types.Message, state: FSMContext):
    interests = [x.strip() for x in message.text.split(",") if x.strip()][:3]
    uid = message.from_user.id
    users[uid]["interests"] = interests
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
    mode_text = {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink / ролевые"}.get(u.get("mode", ""), "—")
    interests_text = ", ".join(u.get("interests", [])) or "—"
    await message.answer(f"👤 Твой профиль:\nИмя: {u['name']}\nВозраст: {u['age']}\nПол: {gender_text}\nРежим: {mode_text}\nИнтересы: {interests_text}")

@dp.message(F.text.contains("Помощь"))
async def show_help(message: types.Message):
    await message.answer("🆘 Помощь:\nНажимай кнопки меню.\nЕсли что-то сломалось — нажми «🔄 Перезапустить»", reply_markup=get_main_menu())

# ====================== ПОИСК (умный) ======================
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
    my_interests = set(users[uid].get("interests", []))

    async with pairing_lock:
        # Выбираем нужную очередь
        if mode == "simple":
            queue = waiting_queue_simple
            fallback = None
        elif mode == "flirt":
            queue = waiting_queue_flirt
            fallback = waiting_queue_kink
        else:
            queue = waiting_queue_kink
            fallback = waiting_queue_flirt

        partner_id = None
        # Сначала ищем точное совпадение в своей очереди
        for i in range(len(queue)):
            p_id = queue[i]
            if p_id != uid and set(users[p_id].get("interests", [])) & my_interests:
                partner_id = queue.pop(i)
                break

        if not partner_id and queue:
            partner_id = queue.pop(0)

        # Fallback
        if not partner_id and fallback:
            for i in range(len(fallback)):
                p_id = fallback[i]
                if p_id != uid:
                    partner_id = fallback.pop(i)
                    break

        if partner_id:
            active_chats[uid] = partner_id
            active_chats[partner_id] = uid

            await state.set_state(Searching.chatting)
            key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=key).set_state(Searching.chatting)

            # Показ полного профиля
            p = users.get(partner_id, {})
            p_mode = {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink / ролевые"}.get(p.get("mode", ""), "—")
            p_interests = ", ".join(p.get("interests", [])) or "—"
            profile_text = f"👤 Собеседник найден!\nИмя: {p.get('name','Аноним')}\nВозраст: {p.get('age','?')}\nПол: {'Парень' if p.get('gender')=='male' else 'Девушка'}\nРежим: {p_mode}\nИнтересы: {p_interests}"

            await bot.send_message(uid, profile_text)
            await bot.send_message(partner_id, profile_text.replace(p.get('name','Аноним'), users[uid].get('name','Аноним')))

            await bot.send_message(uid, TEXTS[users[uid]["lang"]]["found"], reply_markup=get_chat_menu())
            await bot.send_message(partner_id, TEXTS[users[partner_id]["lang"]]["found"], reply_markup=get_chat_menu())
        else:
            # Добавляем в свою очередь
            if mode == "simple":
                waiting_queue_simple.append(uid)
            elif mode == "flirt":
                waiting_queue_flirt.append(uid)
            else:
                waiting_queue_kink.append(uid)
            await state.set_state(Searching.waiting)
            await message.answer(TEXTS[users[uid]["lang"]]["searching"])

# ====================== ЧАТ ======================
@dp.message(F.text.contains("Завершить чат"))
@dp.message(F.text.contains("Следующий"))
@dp.message(Command("stop"))
async def cmd_stop_or_next(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    is_next = "Следующий" in (message.text or "")

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
            await asyncio.sleep(0.3)
            await cmd_find(message, state)
    else:
        await message.answer("Ты не в чате", reply_markup=get_main_menu())

@dp.message(Searching.chatting)
async def relay_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await state.clear()
        return
    partner_id = active_chats[uid]

    try:
        await bot.send_chat_action(partner_id, "typing")
    except:
        pass

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
    print("🚀 MatchMe запущен с полной системой режимов и интересов!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
