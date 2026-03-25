import asyncio
import os
from datetime import datetime, timedelta
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
import asyncpg

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

db_pool = None
active_chats = {}
waiting_anon = []
waiting_simple = []
waiting_flirt = []
waiting_kink = []
last_msg_time = {}
msg_count = {}
pairing_lock = asyncio.Lock()

# ====================== СОСТОЯНИЯ ======================
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

# ====================== БД ======================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                uid BIGINT PRIMARY KEY,
                lang TEXT DEFAULT 'ru',
                accepted_rules BOOLEAN DEFAULT FALSE,
                name TEXT,
                age INTEGER,
                gender TEXT,
                mode TEXT,
                interests TEXT DEFAULT '',
                likes INTEGER DEFAULT 0,
                dislikes INTEGER DEFAULT 0,
                complaints INTEGER DEFAULT 0,
                ban_until TEXT DEFAULT NULL,
                accept_simple BOOLEAN DEFAULT TRUE,
                accept_flirt BOOLEAN DEFAULT TRUE,
                accept_kink BOOLEAN DEFAULT FALSE,
                only_own_mode BOOLEAN DEFAULT FALSE,
                search_gender TEXT DEFAULT 'any',
                search_age_min INTEGER DEFAULT 16,
                search_age_max INTEGER DEFAULT 99,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS complaints_log (
                id SERIAL PRIMARY KEY,
                from_uid BIGINT,
                to_uid BIGINT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

async def get_user(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
        if row:
            return dict(row)
        return None

async def ensure_user(uid):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", uid
        )

async def update_user(uid, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs))
    vals = list(kwargs.values())
    async with db_pool.acquire() as conn:
        await conn.execute(f"UPDATE users SET {sets} WHERE uid=$1", uid, *vals)

async def is_banned(uid):
    u = await get_user(uid)
    if not u or not u.get("ban_until"):
        return False, None
    if u["ban_until"] == "permanent":
        return True, "permanent"
    ban_until = datetime.fromisoformat(u["ban_until"])
    if datetime.now() < ban_until:
        return True, ban_until
    await update_user(uid, ban_until=None)
    return False, None

async def apply_ban(uid):
    u = await get_user(uid)
    count = u.get("complaints", 0)
    if count == 1:
        until = datetime.now() + timedelta(hours=3)
        await update_user(uid, ban_until=until.isoformat())
        return "3 часа"
    elif count == 2:
        until = datetime.now() + timedelta(hours=24)
        await update_user(uid, ban_until=until.isoformat())
        return "24 часа"
    elif count >= 3:
        await update_user(uid, ban_until="permanent")
        return "навсегда"
    return None

# ====================== ТЕКСТЫ ======================
WELCOME_TEXT = (
    "👋 Привет! Я MatchMe — анонимный чат для общения, флирта и знакомств.\n\n"
    "🇷🇺 Нажми кнопку для продолжения\n"
    "🇬🇧 Click button to continue"
)

RULES_RU = """📜 Правила MatchMe:

✅ Разрешено:
• Общение, флирт, ролевые игры (18+)
• Уважительное общение
• Использование кнопки жалобы при нарушениях

❌ Запрещено:
• Спам, реклама, продажа
• Контент с несовершеннолетними — бан навсегда
• Угрозы, оскорбления, травля
• Злоупотребление кнопкой жалобы (бан за ложные жалобы)

⚠️ Система банов:
• 1-я жалоба: бан 3 часа
• 2-я жалоба: бан 24 часа
• 3-я жалоба: перманентный бан

Нажми ✅ Принять правила для продолжения."""

MODE_NAMES = {"simple": "Просто общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}
INTERESTS_MAP = {
    "simple": ["Разговор по душам 🗣", "Юмор и мемы 😂", "Советы по жизни 💡", "Музыка 🎵", "Игры 🎮"],
    "flirt":  ["Лёгкий флирт 😏", "Комплименты 💌", "Секстинг 🔥", "Виртуальные свидания 💑", "Флирт и игры 🎭"],
    "kink":   ["BDSM 🖤", "Bondage 🔗", "Roleplay 🎭", "Dom/Sub ⛓", "Pet play 🐾", "Другой фетиш ✨"],
}

# ====================== КЛАВИАТУРЫ ======================
def kb_lang():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]
    ], resize_keyboard=True)

def kb_rules():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Принять правила")]
    ], resize_keyboard=True)

def kb_main():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡ Анонимный поиск")],
        [KeyboardButton(text="🔍 Поиск по анкете")],
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)

def kb_gender():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨 Парень"), KeyboardButton(text="👩 Девушка")],
        [KeyboardButton(text="⚧ Другое")]
    ], resize_keyboard=True)

def kb_mode():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💬 Просто общение")],
        [KeyboardButton(text="💋 Флирт")],
        [KeyboardButton(text="🔥 Kink / ролевые (18+)")]
    ], resize_keyboard=True)

def kb_search_gender():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨 Парня"), KeyboardButton(text="👩 Девушку")],
        [KeyboardButton(text="⚧ Другое"), KeyboardButton(text="🔀 Не важно")]
    ], resize_keyboard=True)

def kb_interests(mode, selected):
    interests = INTERESTS_MAP.get(mode, [])
    buttons = []
    for interest in interests:
        mark = "✅ " if interest in selected else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{interest}",
            callback_data=f"int:{interest}"
        )])
    buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data="int:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_chat():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ Следующий"), KeyboardButton(text="❌ Стоп")],
        [KeyboardButton(text="👍 Лайк"), KeyboardButton(text="🚩 Жалоба")],
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def kb_cancel():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Отменить поиск")]
    ], resize_keyboard=True)

def kb_complaint():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔞 Несовершеннолетние", callback_data="rep:minor")],
        [InlineKeyboardButton(text="💰 Спам / Реклама", callback_data="rep:spam")],
        [InlineKeyboardButton(text="😡 Угрозы / Оскорбления", callback_data="rep:abuse")],
        [InlineKeyboardButton(text="🔄 Другое", callback_data="rep:other")],
    ])

async def kb_settings(uid):
    u = await get_user(uid)
    if not u:
        return InlineKeyboardMarkup(inline_keyboard=[])
    s = "✅"
    n = "❌"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅' if u['accept_simple'] else '❌'} Принимать из Общения",
            callback_data="set:simple")],
        [InlineKeyboardButton(
            text=f"{'✅' if u['accept_flirt'] else '❌'} Принимать из Флирта",
            callback_data="set:flirt")],
        [InlineKeyboardButton(
            text=f"{'✅' if u['accept_kink'] else '❌'} Принимать из Kink",
            callback_data="set:kink")],
        [InlineKeyboardButton(
            text=f"{'✅' if u['only_own_mode'] else '❌'} Только свой режим",
            callback_data="set:only_own")],
        [InlineKeyboardButton(text="👤 Фильтр по полу", callback_data="set:gender")],
        [InlineKeyboardButton(text="🎂 Фильтр по возрасту", callback_data="set:age")],
    ])

def kb_edit():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Имя", callback_data="edit:name"),
         InlineKeyboardButton(text="🎂 Возраст", callback_data="edit:age")],
        [InlineKeyboardButton(text="⚧ Пол", callback_data="edit:gender"),
         InlineKeyboardButton(text="💬 Режим", callback_data="edit:mode")],
        [InlineKeyboardButton(text="🎯 Интересы", callback_data="edit:interests")],
    ])

# ====================== УТИЛИТЫ ======================
def get_queue(mode):
    if mode == "simple": return waiting_simple
    if mode == "flirt": return waiting_flirt
    if mode == "kink": return waiting_kink
    return waiting_anon

def get_rating_score(u):
    return u.get("likes", 0) - u.get("dislikes", 0)

async def cleanup(uid, state=None):
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink]:
        if uid in q: q.remove(uid)
    partner = active_chats.pop(uid, None)
    if partner: active_chats.pop(partner, None)
    if state: await state.clear()
    return partner

async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать / перезапустить"),
        BotCommand(command="find", description="Найти собеседника"),
        BotCommand(command="stop", description="Завершить чат"),
        BotCommand(command="next", description="Следующий собеседник"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="help", description="Помощь"),
    ])

# ====================== СТАРТ ======================
@dp.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await cleanup(uid, state)
    await ensure_user(uid)

    banned, until = await is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer("🚫 Ты заблокирован навсегда за нарушение правил.")
        else:
            await message.answer(f"🚫 Ты заблокирован до {until.strftime('%H:%M %d.%m.%Y')}")
        return

    u = await get_user(uid)
    if not u.get("accepted_rules"):
        await state.set_state(Rules.waiting)
        await message.answer(WELCOME_TEXT, reply_markup=kb_lang())
    else:
        await message.answer("👋 С возвращением!", reply_markup=kb_main())

# ====================== ЯЗЫК И ПРАВИЛА ======================
@dp.message(StateFilter(Rules.waiting), F.text.in_(["🇷🇺 Русский", "🇬🇧 English"]))
async def choose_lang(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = "ru" if "Русский" in message.text else "en"
    await update_user(uid, lang=lang)
    await message.answer(RULES_RU, reply_markup=kb_rules())

@dp.message(StateFilter(Rules.waiting), F.text == "✅ Принять правила")
async def accept_rules(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await update_user(uid, accepted_rules=True)
    await state.clear()
    await message.answer("✅ Правила приняты! Добро пожаловать в MatchMe!", reply_markup=kb_main())

# ====================== АНОНИМНЫЙ ПОИСК ======================
@dp.message(F.text == "⚡ Анонимный поиск", StateFilter("*"))
async def anon_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await cleanup(uid, state)

    banned, until = await is_banned(uid)
    if banned:
        await message.answer("🚫 Ты заблокирован.")
        return

    await message.answer("⚡ Ищем анонимного собеседника...", reply_markup=kb_cancel())

    async with pairing_lock:
        partner = None
        for i, pid in enumerate(waiting_anon):
            if pid != uid:
                partner = waiting_anon.pop(i)
                break

        if partner:
            active_chats[uid] = partner
            active_chats[partner] = uid
            last_msg_time[uid] = last_msg_time[partner] = datetime.now()
            await state.set_state(Chat.chatting)
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).set_state(Chat.chatting)
            await bot.send_message(uid, "👤 Соединено с анонимным собеседником!\nУдачи! 🎉", reply_markup=kb_chat())
            await bot.send_message(partner, "👤 Соединено с анонимным собеседником!\nУдачи! 🎉", reply_markup=kb_chat())
        else:
            waiting_anon.append(uid)
            await state.set_state(Chat.waiting)

# ====================== ПОИСК ПО АНКЕТЕ ======================
@dp.message(F.text.in_(["🔍 Поиск по анкете", "🔍 Найти собеседника"]), StateFilter("*"))
@dp.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await cleanup(uid, state)

    banned, until = await is_banned(uid)
    if banned:
        await message.answer("🚫 Ты заблокирован.")
        return

    u = await get_user(uid)
    if not u or not u.get("name") or not u.get("mode"):
        await state.set_state(Reg.name)
        await message.answer("📝 Заполним анкету!\n\nКак тебя зовут?", reply_markup=ReplyKeyboardRemove())
        return

    mode = u["mode"]
    online = len(get_queue(mode))
    await message.answer(
        f"👥 В режиме {MODE_NAMES[mode]}: {online} чел.\n\n🔍 Ищем...",
        reply_markup=kb_cancel()
    )

    async with pairing_lock:
        partner = None
        my_interests = set(u.get("interests", "").split(",")) if u.get("interests") else set()
        my_rating = get_rating_score(u)
        only_own = u.get("only_own_mode", False)
        search_gender = u.get("search_gender", "any")
        search_age_min = u.get("search_age_min", 16)
        search_age_max = u.get("search_age_max", 99)

        queues = [get_queue(mode)]
        if not only_own:
            if mode == "flirt" and u.get("accept_kink"): queues.append(waiting_kink)
            if mode == "kink" and u.get("accept_flirt"): queues.append(waiting_flirt)

        candidates = []
        for q in queues:
            for pid in q:
                if pid == uid: continue
                pu = await get_user(pid)
                if not pu: continue
                # Фильтр по полу
                if search_gender != "any" and pu.get("gender") != search_gender: continue
                # Фильтр по возрасту
                p_age = pu.get("age", 0)
                if p_age < search_age_min or p_age > search_age_max: continue
                # Проверяем взаимные настройки
                if mode == "simple" and not pu.get("accept_simple", True): continue
                if mode == "flirt" and not pu.get("accept_flirt", True): continue
                if mode == "kink" and not pu.get("accept_kink", False): continue
                p_interests = set(pu.get("interests", "").split(",")) if pu.get("interests") else set()
                common = len(my_interests & p_interests)
                rating_diff = abs(get_rating_score(pu) - my_rating)
                candidates.append((pid, common, rating_diff, q))

        if candidates:
            candidates.sort(key=lambda x: (-x[1], x[2]))
            best = candidates[0]
            partner = best[0]
            best[3].remove(partner)

        if partner:
            active_chats[uid] = partner
            active_chats[partner] = uid
            last_msg_time[uid] = last_msg_time[partner] = datetime.now()
            await state.set_state(Chat.chatting)
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).set_state(Chat.chatting)

            pu = await get_user(partner)
            g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}

            p_text = (
                f"👤 Собеседник найден!\n"
                f"Имя: {pu.get('name','Аноним')}\n"
                f"Возраст: {pu.get('age','?')}\n"
                f"Пол: {g_map.get(pu.get('gender',''),'?')}\n"
                f"Режим: {MODE_NAMES.get(pu.get('mode',''),'—')}\n"
                f"Интересы: {pu.get('interests','—')}\n"
                f"⭐ Рейтинг: {get_rating_score(pu)}"
            )
            my_text = (
                f"👤 Собеседник найден!\n"
                f"Имя: {u.get('name','Аноним')}\n"
                f"Возраст: {u.get('age','?')}\n"
                f"Пол: {g_map.get(u.get('gender',''),'?')}\n"
                f"Режим: {MODE_NAMES.get(u.get('mode',''),'—')}\n"
                f"Интересы: {u.get('interests','—')}\n"
                f"⭐ Рейтинг: {get_rating_score(u)}"
            )
            await bot.send_message(uid, p_text)
            await bot.send_message(partner, my_text)
            await bot.send_message(uid, "✅ Начинайте общение!", reply_markup=kb_chat())
            await bot.send_message(partner, "✅ Начинайте общение!", reply_markup=kb_chat())
        else:
            q = get_queue(mode)
            if uid not in q:
                q.append(uid)
            await state.set_state(Chat.waiting)
            asyncio.create_task(notify_no_partner(uid))

async def notify_no_partner(uid):
    await asyncio.sleep(60)
    if uid in (waiting_simple + waiting_flirt + waiting_kink + waiting_anon):
        try:
            await bot.send_message(uid,
                "😔 Пока никого нет в сети по твоим параметрам.\n\n"
                "Можешь подождать или изменить настройки поиска (/settings)",
                reply_markup=kb_main()
            )
        except: pass

# ====================== РЕГИСТРАЦИЯ ======================
@dp.message(StateFilter(Reg.name))
async def reg_name(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await update_user(uid, name=message.text.strip()[:20])
    await state.set_state(Reg.age)
    await message.answer("🎂 Сколько тебе лет?")

@dp.message(StateFilter(Reg.age))
async def reg_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not message.text.isdigit():
        await message.answer("❗ Введи число.")
        return
    age = int(message.text)
    if age < 16:
        await message.answer("❌ Тебе должно быть минимум 16 лет.\n\nВведи правильный возраст:")
        return
    if age > 99:
        await message.answer("❗ Введи реальный возраст (16–99).")
        return
    await update_user(uid, age=age)
    await state.set_state(Reg.gender)
    await message.answer("⚧ Выбери свой пол:", reply_markup=kb_gender())

@dp.message(StateFilter(Reg.gender))
async def reg_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text
    if "Парень" in txt: gender = "male"
    elif "Девушка" in txt: gender = "female"
    else: gender = "other"
    await update_user(uid, gender=gender)
    await state.set_state(Reg.mode)
    await message.answer("💬 Выбери режим:", reply_markup=kb_mode())

@dp.message(StateFilter(Reg.mode))
async def reg_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text.lower()
    if "общение" in txt: mode = "simple"
    elif "флирт" in txt: mode = "flirt"
    else: mode = "kink"
    await update_user(uid, mode=mode)
    await state.update_data(temp_interests=[], reg_mode=mode)
    await state.set_state(Reg.interests)
    await message.answer("🎯 Выбери 1–3 интереса:", reply_markup=ReplyKeyboardRemove())
    await message.answer("👇", reply_markup=kb_interests(mode, []))

@dp.callback_query(F.data.startswith("int:"), StateFilter(Reg.interests))
async def reg_interest(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    sel = data.get("temp_interests", [])
    mode = data.get("reg_mode", "simple")

    if val == "done":
        if not sel:
            await callback.answer("Выбери хотя бы один!", show_alert=True)
            return
        await update_user(uid, interests=",".join(sel))
        await state.clear()
        await callback.message.edit_text("✅ Анкета заполнена!")
        await callback.message.answer("🔍 Ищем собеседника...", reply_markup=kb_cancel())
        await callback.answer()
        await cmd_find(callback.message, state)
        return

    if val in sel:
        sel.remove(val)
        await callback.answer(f"Убрано: {val}")
    elif len(sel) < 3:
        sel.append(val)
        await callback.answer(f"Добавлено: {val}")
    else:
        await callback.answer("Максимум 3 интереса!", show_alert=True)
        return

    await state.update_data(temp_interests=sel)
    await callback.message.edit_reply_markup(reply_markup=kb_interests(mode, sel))

# ====================== ЧАТ ======================
@dp.message(StateFilter(Chat.chatting))
async def relay(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""

    if any(x in txt for x in ["⏭ Следующий", "Следующий"]):
        await end_chat(uid, state, go_next=True)
        return
    if any(x in txt for x in ["❌ Стоп", "Стоп"]):
        await end_chat(uid, state, go_next=False)
        return
    if "🚩 Жалоба" in txt or "Жалоба" in txt:
        await state.set_state(Complaint.reason)
        await message.answer("🚩 Причина жалобы:", reply_markup=kb_complaint())
        return
    if "👍 Лайк" in txt or "Лайк" in txt:
        if uid in active_chats:
            partner = active_chats[uid]
            pu = await get_user(partner)
            new_likes = pu.get("likes", 0) + 1
            await update_user(partner, likes=new_likes)
            await message.answer("👍 Лайк отправлен!")
            try: await bot.send_message(partner, "👍 Собеседник поставил тебе лайк!")
            except: pass
        return
    if "🏠" in txt or "Главное меню" in txt:
        await end_chat(uid, state, go_next=False)
        return

    if uid not in active_chats:
        await state.clear()
        await message.answer("Ты не в чате.", reply_markup=kb_main())
        return

    partner = active_chats[uid]

    now = datetime.now()
    msg_count.setdefault(uid, [])
    msg_count[uid] = [t for t in msg_count[uid] if (now - t).total_seconds() < 5]
    if len(msg_count[uid]) >= 5:
        await message.answer("⚠️ Не спамь!")
        return
    msg_count[uid].append(now)
    last_msg_time[uid] = last_msg_time[partner] = now

    try:
        if message.text: await bot.send_message(partner, message.text)
        elif message.sticker: await bot.send_sticker(partner, message.sticker.file_id)
        elif message.photo: await bot.send_photo(partner, message.photo[-1].file_id, caption=message.caption)
        elif message.voice: await bot.send_voice(partner, message.voice.file_id)
        elif message.video: await bot.send_video(partner, message.video.file_id, caption=message.caption)
        elif message.video_note: await bot.send_video_note(partner, message.video_note.file_id)
        elif message.document: await bot.send_document(partner, message.document.file_id, caption=message.caption)
        elif message.audio: await bot.send_audio(partner, message.audio.file_id)
    except: pass

async def end_chat(uid, state, go_next=False):
    partner = active_chats.pop(uid, None)
    if partner: active_chats.pop(partner, None)
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink]:
        if uid in q: q.remove(uid)
    await state.clear()
    await bot.send_message(uid, "💔 Чат завершён.", reply_markup=kb_main())
    if partner:
        try:
            await bot.send_message(partner, "😔 Собеседник покинул чат.", reply_markup=kb_main())
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).clear()
        except: pass
    if go_next:
        await asyncio.sleep(0.3)
        class FakeMsg:
            from_user = type("u", (), {"id": uid})()
            text = "find"
        await cmd_find(FakeMsg(), state)

# ====================== ЖАЛОБА ======================
@dp.callback_query(F.data.startswith("rep:"), StateFilter(Complaint.reason))
async def handle_complaint(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    reason_map = {"minor": "Несовершеннолетние", "spam": "Спам/Реклама", "abuse": "Угрозы/Оскорбления", "other": "Другое"}
    reason = reason_map.get(callback.data.split(":", 1)[1], "Другое")

    partner = active_chats.get(uid)
    if not partner:
        await callback.message.edit_text("Ты не в чате.")
        await state.clear()
        return

    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO complaints_log (from_uid, to_uid, reason) VALUES ($1,$2,$3)", uid, partner, reason)
        pu = await get_user(partner)
        new_count = pu.get("complaints", 0) + 1
        await update_user(partner, complaints=new_count)

    ban_msg = await apply_ban(partner)
    active_chats.pop(uid, None)
    active_chats.pop(partner, None)
    await state.clear()

    await callback.message.edit_text(f"🚩 Жалоба отправлена. Причина: {reason}")
    await bot.send_message(uid, "Чат завершён.", reply_markup=kb_main())

    if ban_msg:
        try: await bot.send_message(partner, f"🚫 Жалоба ({reason}). Ты заблокирован на {ban_msg}.", reply_markup=ReplyKeyboardRemove())
        except: pass
    else:
        try: await bot.send_message(partner, "⚠️ На тебя поступила жалоба. Будь внимательнее!", reply_markup=kb_main())
        except: pass
    await callback.answer()

# ====================== ОТМЕНА ПОИСКА ======================
@dp.message(F.text == "❌ Отменить поиск", StateFilter("*"))
async def cancel_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    removed = any(uid in q for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink])
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink]:
        if uid in q: q.remove(uid)
    await state.clear()
    await message.answer("❌ Поиск отменён." if removed else "Ты не в поиске.", reply_markup=kb_main())

# ====================== СТОП / СЛЕДУЮЩИЙ ======================
@dp.message(Command("stop"), StateFilter("*"))
async def cmd_stop(message: types.Message, state: FSMContext):
    await end_chat(message.from_user.id, state, go_next=False)

@dp.message(Command("next"), StateFilter("*"))
async def cmd_next(message: types.Message, state: FSMContext):
    await end_chat(message.from_user.id, state, go_next=True)

# ====================== ПРОФИЛЬ ======================
@dp.message(F.text == "👤 Мой профиль", StateFilter("*"))
@dp.message(Command("profile"), StateFilter("*"))
async def show_profile(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    u = await get_user(uid)
    if not u or not u.get("name"):
        await message.answer("Анкета не заполнена.", reply_markup=kb_main())
        return
    g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
    await message.answer(
        f"👤 Профиль:\n"
        f"Имя: {u['name']}\n"
        f"Возраст: {u['age']}\n"
        f"Пол: {g_map.get(u.get('gender',''), '—')}\n"
        f"Режим: {MODE_NAMES.get(u.get('mode',''), '—')}\n"
        f"Интересы: {u.get('interests','—')}\n"
        f"⭐ Рейтинг: {get_rating_score(u)}\n"
        f"👍 Лайков: {u.get('likes',0)}",
        reply_markup=kb_edit()
    )

# ====================== РЕДАКТИРОВАНИЕ ======================
@dp.callback_query(F.data.startswith("edit:"))
async def edit_profile(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    await callback.answer()
    if field == "name":
        await state.set_state(EditProfile.name)
        await callback.message.answer("✏️ Новое имя:")
    elif field == "age":
        await state.set_state(EditProfile.age)
        await callback.message.answer("🎂 Новый возраст:")
    elif field == "gender":
        await state.set_state(EditProfile.gender)
        await callback.message.answer("⚧ Выбери пол:", reply_markup=kb_gender())
    elif field == "mode":
        await state.set_state(EditProfile.mode)
        await callback.message.answer("💬 Выбери режим:", reply_markup=kb_mode())
    elif field == "interests":
        u = await get_user(uid)
        mode = u.get("mode", "simple")
        await state.set_state(EditProfile.interests)
        await state.update_data(temp_interests=[], edit_mode=mode)
        await callback.message.answer("🎯 Выбери интересы:", reply_markup=kb_interests(mode, []))

@dp.message(StateFilter(EditProfile.name))
async def edit_name(message: types.Message, state: FSMContext):
    await update_user(message.from_user.id, name=message.text.strip()[:20])
    await state.clear()
    await message.answer("✅ Имя обновлено!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.age))
async def edit_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer("❗ Введи число от 16 до 99")
        return
    await update_user(message.from_user.id, age=int(message.text))
    await state.clear()
    await message.answer("✅ Возраст обновлён!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.gender))
async def edit_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if "Парень" in message.text: g = "male"
    elif "Девушка" in message.text: g = "female"
    else: g = "other"
    await update_user(uid, gender=g)
    await state.clear()
    await message.answer("✅ Пол обновлён!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.mode))
async def edit_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text.lower()
    if "общение" in txt: mode = "simple"
    elif "флирт" in txt: mode = "flirt"
    else: mode = "kink"
    await update_user(uid, mode=mode)
    await state.set_state(EditProfile.interests)
    await state.update_data(temp_interests=[], edit_mode=mode)
    await message.answer("🎯 Выбери новые интересы:", reply_markup=kb_interests(mode, []))

@dp.callback_query(F.data.startswith("int:"), StateFilter(EditProfile.interests))
async def edit_interest(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    sel = data.get("temp_interests", [])
    mode = data.get("edit_mode", "simple")

    if val == "done":
        if not sel:
            await callback.answer("Выбери хотя бы один!", show_alert=True)
            return
        await update_user(uid, interests=",".join(sel))
        await state.clear()
        await callback.message.edit_text("✅ Интересы обновлены!")
        await callback.message.answer("Готово!", reply_markup=kb_main())
        await callback.answer()
        return

    if val in sel:
        sel.remove(val)
        await callback.answer(f"Убрано: {val}")
    elif len(sel) < 3:
        sel.append(val)
        await callback.answer(f"Добавлено: {val}")
    else:
        await callback.answer("Максимум 3!", show_alert=True)
        return

    await state.update_data(temp_interests=sel)
    await callback.message.edit_reply_markup(reply_markup=kb_interests(mode, sel))

# ====================== НАСТРОЙКИ ======================
@dp.message(F.text == "⚙️ Настройки", StateFilter("*"))
@dp.message(Command("settings"), StateFilter("*"))
async def show_settings(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await message.answer("⚙️ Настройки поиска:", reply_markup=await kb_settings(uid))

@dp.callback_query(F.data.startswith("set:"))
async def toggle_setting(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    key = callback.data.split(":", 1)[1]
    u = await get_user(uid)

    if key == "gender":
        await state.set_state(EditProfile.gender)
        await callback.message.answer(
            "👤 Кого хочешь искать?",
            reply_markup=kb_search_gender()
        )
        await state.update_data(editing_search_gender=True)
        await callback.answer()
        return
    elif key == "age":
        await callback.message.answer(
            "🎂 Введи диапазон возраста через дефис (например: 18-25):"
        )
        await state.set_state(EditProfile.age)
        await state.update_data(editing_search_age=True)
        await callback.answer()
        return
    elif key == "simple":
        await update_user(uid, accept_simple=not u.get("accept_simple", True))
    elif key == "flirt":
        await update_user(uid, accept_flirt=not u.get("accept_flirt", True))
    elif key == "kink":
        await update_user(uid, accept_kink=not u.get("accept_kink", False))
    elif key == "only_own":
        await update_user(uid, only_own_mode=not u.get("only_own_mode", False))

    await callback.message.edit_reply_markup(reply_markup=await kb_settings(uid))
    await callback.answer("✅ Изменено")

@dp.message(StateFilter(EditProfile.gender))
async def handle_gender_setting(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()

    if data.get("editing_search_gender"):
        txt = message.text
        if "Парня" in txt: sg = "male"
        elif "Девушку" in txt: sg = "female"
        elif "Другое" in txt: sg = "other"
        else: sg = "any"
        await update_user(uid, search_gender=sg)
        await state.clear()
        await message.answer("✅ Фильтр по полу сохранён!", reply_markup=kb_main())
    else:
        if "Парень" in message.text: g = "male"
        elif "Девушка" in message.text: g = "female"
        else: g = "other"
        await update_user(uid, gender=g)
        await state.clear()
        await message.answer("✅ Пол обновлён!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.age))
async def handle_age_setting(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()

    if data.get("editing_search_age"):
        try:
            parts = message.text.split("-")
            min_age = int(parts[0].strip())
            max_age = int(parts[1].strip())
            if 16 <= min_age <= max_age <= 99:
                await update_user(uid, search_age_min=min_age, search_age_max=max_age)
                await state.clear()
                await message.answer(f"✅ Возраст поиска: {min_age}–{max_age}", reply_markup=kb_main())
            else:
                await message.answer("❗ Введи корректный диапазон (16–99), например: 18-25")
        except:
            await message.answer("❗ Формат: 18-25")
    else:
        if not message.text.isdigit() or not (16 <= int(message.text) <= 99):
            await message.answer("❗ Введи число от 16 до 99")
            return
        await update_user(uid, age=int(message.text))
        await state.clear()
        await message.answer("✅ Возраст обновлён!", reply_markup=kb_main())

# ====================== ПОМОЩЬ ======================
@dp.message(F.text == "❓ Помощь", StateFilter("*"))
@dp.message(Command("help"), StateFilter("*"))
async def show_help(message: types.Message, state: FSMContext):
    await message.answer(
        "🆘 Помощь:\n\n"
        "⚡ Анонимный поиск — быстрый поиск без анкеты\n"
        "🔍 Поиск по анкете — поиск по режиму и интересам\n"
        "⚙️ Настройки — фильтры поиска\n"
        "👤 Профиль — твоя анкета\n\n"
        "В чате:\n"
        "⏭ Следующий — другой собеседник\n"
        "❌ Стоп — завершить чат\n"
        "🚩 Жалоба — пожаловаться\n"
        "👍 Лайк — лайк собеседнику\n\n"
        "Если что-то сломалось — /start",
        reply_markup=kb_main()
    )

# ====================== ПЕРЕЗАПУСК ======================
@dp.message(F.text.contains("Перезапустить"), StateFilter("*"))
async def cmd_restart(message: types.Message, state: FSMContext):
    await cmd_start(message, state)

# ====================== ТАЙМЕР НЕАКТИВНОСТИ ======================
async def inactivity_checker():
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        to_end = []
        for uid, partner in list(active_chats.items()):
            if uid < partner:
                last = max(last_msg_time.get(uid, now), last_msg_time.get(partner, now))
                if (now - last).total_seconds() > 420:
                    to_end.append((uid, partner))
        for uid, partner in to_end:
            active_chats.pop(uid, None)
            active_chats.pop(partner, None)
            try: await bot.send_message(uid, "⏰ Чат завершён из-за неактивности.", reply_markup=kb_main())
            except: pass
            try: await bot.send_message(partner, "⏰ Чат завершён из-за неактивности.", reply_markup=kb_main())
            except: pass

# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    await set_commands()
    asyncio.create_task(inactivity_checker())
    print("🚀 MatchMe с PostgreSQL запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
