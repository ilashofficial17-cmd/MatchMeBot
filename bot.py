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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))

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
    search_gender = State()
    search_age = State()

class AdminState(StatesGroup):
    waiting_user_id = State()

class ResetProfile(StatesGroup):
    confirm = State()

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
                warn_count INTEGER DEFAULT 0,
                ban_until TEXT DEFAULT NULL,
                accept_simple BOOLEAN DEFAULT TRUE,
                accept_flirt BOOLEAN DEFAULT TRUE,
                accept_kink BOOLEAN DEFAULT FALSE,
                only_own_mode BOOLEAN DEFAULT FALSE,
                search_gender TEXT DEFAULT 'any',
                search_age_min INTEGER DEFAULT 16,
                search_age_max INTEGER DEFAULT 99,
                created_at TIMESTAMP DEFAULT NOW(),
                last_seen TIMESTAMP DEFAULT NOW()
            )
        """)
        for col, definition in [
            ("last_seen", "TIMESTAMP DEFAULT NOW()"),
            ("warn_count", "INTEGER DEFAULT 0"),
            ("search_gender", "TEXT DEFAULT 'any'"),
            ("search_age_min", "INTEGER DEFAULT 16"),
            ("search_age_max", "INTEGER DEFAULT 99"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}")
            except: pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS complaints_log (
                id SERIAL PRIMARY KEY,
                from_uid BIGINT,
                to_uid BIGINT,
                reason TEXT,
                reviewed BOOLEAN DEFAULT FALSE,
                admin_action TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            await conn.execute("ALTER TABLE complaints_log ADD COLUMN IF NOT EXISTS reviewed BOOLEAN DEFAULT FALSE")
            await conn.execute("ALTER TABLE complaints_log ADD COLUMN IF NOT EXISTS admin_action TEXT DEFAULT NULL")
        except: pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_chats_db (
                uid1 BIGINT PRIMARY KEY,
                uid2 BIGINT,
                chat_type TEXT DEFAULT 'profile',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

    await restore_chats()

async def restore_chats():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT uid1, uid2 FROM active_chats_db")
    restored = 0
    for r in rows:
        uid1, uid2 = r["uid1"], r["uid2"]
        active_chats[uid1] = uid2
        active_chats[uid2] = uid1
        restored += 1
        try:
            await bot.send_message(uid1, "🔄 Бот обновлён. Твой чат восстановлен!", reply_markup=kb_chat())
            await bot.send_message(uid2, "🔄 Бот обновлён. Твой чат восстановлен!", reply_markup=kb_chat())
        except: pass
    if restored:
        print(f"✅ Восстановлено {restored} чатов")

async def get_user(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
        return dict(row) if row else None

async def ensure_user(uid):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", uid)

async def update_user(uid, **kwargs):
    if not kwargs: return
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs))
    vals = list(kwargs.values())
    async with db_pool.acquire() as conn:
        await conn.execute(f"UPDATE users SET {sets} WHERE uid=$1", uid, *vals)

async def is_banned(uid):
    u = await get_user(uid)
    if not u or not u.get("ban_until"): return False, None
    if u["ban_until"] == "permanent": return True, "permanent"
    try:
        ban_until = datetime.fromisoformat(u["ban_until"])
        if datetime.now() < ban_until: return True, ban_until
        await update_user(uid, ban_until=None)
    except: pass
    return False, None

async def apply_ban(uid):
    u = await get_user(uid)
    count = u.get("complaints", 0)
    if count >= 3:
        await update_user(uid, ban_until="permanent")
        return "навсегда"
    elif count == 2:
        until = datetime.now() + timedelta(hours=24)
        await update_user(uid, ban_until=until.isoformat())
        return "24 часа"
    elif count == 1:
        until = datetime.now() + timedelta(hours=3)
        await update_user(uid, ban_until=until.isoformat())
        return "3 часа"
    return None

async def save_chat_to_db(uid1, uid2, chat_type="profile"):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO active_chats_db (uid1, uid2, chat_type) VALUES ($1,$2,$3) ON CONFLICT (uid1) DO UPDATE SET uid2=$2",
                uid1, uid2, chat_type
            )
            await conn.execute(
                "INSERT INTO active_chats_db (uid1, uid2, chat_type) VALUES ($1,$2,$3) ON CONFLICT (uid1) DO UPDATE SET uid2=$2",
                uid2, uid1, chat_type
            )
    except: pass

async def remove_chat_from_db(uid1, uid2=None):
    try:
        async with db_pool.acquire() as conn:
            if uid2:
                await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1 OR uid1=$2", uid1, uid2)
            else:
                await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1", uid1)
    except: pass

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
• Лайки собеседникам
• Жалобы при реальных нарушениях

❌ Запрещено:
• Спам, реклама, продажа
• Контент с несовершеннолетними — бан навсегда
• Угрозы, оскорбления, травля
• Необоснованные жалобы — бан за злоупотребление

⚠️ Система модерации:
• 1-я жалоба: бан 3 часа
• 2-я жалоба: бан 24 часа
• 3-я жалоба: перманентный бан
• Ложные жалобы = предупреждение или бан

ℹ️ Все жалобы проверяются администратором вручную.

Нажми ✅ Принять правила для продолжения."""

RULES_PROFILE = """📜 Правила общения:

• Уважай собеседника
• 👍 Лайк — если понравилось общение
• 🚩 Жалоба — только при реальных нарушениях
• Ложная жалоба = санкции против тебя
• Администратор проверяет каждую жалобу вручную

Нажми ✅ Понятно для продолжения."""

MODE_NAMES = {"simple": "Просто общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}
INTERESTS_MAP = {
    "simple": ["Разговор по душам 🗣", "Юмор и мемы 😂", "Советы по жизни 💡", "Музыка 🎵", "Игры 🎮"],
    "flirt":  ["Лёгкий флирт 😏", "Комплименты 💌", "Секстинг 🔥", "Виртуальные свидания 💑", "Флирт и игры 🎭"],
    "kink":   ["BDSM 🖤", "Bondage 🔗", "Roleplay 🎭", "Dom/Sub ⛓", "Pet play 🐾", "Другой фетиш ✨"],
}

# ====================== КЛАВИАТУРЫ ======================
def kb_main():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡ Анонимный поиск")],
        [KeyboardButton(text="🔍 Поиск по анкете")],
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)

def kb_lang():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]
    ], resize_keyboard=True)

def kb_rules():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Принять правила")]
    ], resize_keyboard=True)

def kb_rules_profile():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Понятно, начать анкету")]
    ], resize_keyboard=True)

def kb_cancel_reg():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Отменить анкету")]
    ], resize_keyboard=True)

def kb_gender():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨 Парень"), KeyboardButton(text="👩 Девушка")],
        [KeyboardButton(text="⚧ Другое")],
        [KeyboardButton(text="❌ Отменить анкету")]
    ], resize_keyboard=True)

def kb_mode():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💬 Просто общение")],
        [KeyboardButton(text="💋 Флирт")],
        [KeyboardButton(text="🔥 Kink / ролевые (18+)")],
        [KeyboardButton(text="❌ Отменить анкету")]
    ], resize_keyboard=True)

def kb_cancel_search():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Отменить поиск")]
    ], resize_keyboard=True)

def kb_chat():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ Следующий"), KeyboardButton(text="❌ Стоп")],
        [KeyboardButton(text="👍 Лайк"), KeyboardButton(text="🚩 Жалоба")],
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def kb_search_gender():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨 Парня"), KeyboardButton(text="👩 Девушку")],
        [KeyboardButton(text="⚧ Другое"), KeyboardButton(text="🔀 Не важно")],
        [KeyboardButton(text="◀️ Назад")]
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
    buttons.append([InlineKeyboardButton(text="✅ Готово — сохранить", callback_data="int:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_complaint():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔞 Несовершеннолетние", callback_data="rep:minor")],
        [InlineKeyboardButton(text="💰 Спам / Реклама", callback_data="rep:spam")],
        [InlineKeyboardButton(text="😡 Угрозы / Оскорбления", callback_data="rep:abuse")],
        [InlineKeyboardButton(text="🔄 Другое", callback_data="rep:other")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="rep:cancel")],
    ])

async def kb_settings(uid):
    u = await get_user(uid)
    if not u: return InlineKeyboardMarkup(inline_keyboard=[])
    sg_map = {"any": "🔀 Все", "male": "👨 Парни", "female": "👩 Девушки", "other": "⚧ Другое"}
    sg = sg_map.get(u.get("search_gender", "any"), "🔀 Все")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅' if u.get('accept_simple', True) else '❌'} Принимать из Общения",
            callback_data="set:simple")],
        [InlineKeyboardButton(
            text=f"{'✅' if u.get('accept_flirt', True) else '❌'} Принимать из Флирта",
            callback_data="set:flirt")],
        [InlineKeyboardButton(
            text=f"{'✅' if u.get('accept_kink', False) else '❌'} Принимать из Kink",
            callback_data="set:kink")],
        [InlineKeyboardButton(
            text=f"{'✅' if u.get('only_own_mode', False) else '❌'} Только свой режим",
            callback_data="set:only_own")],
        [InlineKeyboardButton(text=f"👤 Искать: {sg}", callback_data="set:gender")],
        [InlineKeyboardButton(
            text=f"🎂 Возраст: {u.get('search_age_min',16)}–{u.get('search_age_max',99)}",
            callback_data="set:age")],
    ])

def kb_edit():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Имя", callback_data="edit:name"),
         InlineKeyboardButton(text="🎂 Возраст", callback_data="edit:age")],
        [InlineKeyboardButton(text="⚧ Пол", callback_data="edit:gender"),
         InlineKeyboardButton(text="💬 Режим", callback_data="edit:mode")],
        [InlineKeyboardButton(text="🎯 Интересы", callback_data="edit:interests")],
    ])

def kb_admin_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="🚩 Жалобы на рассмотрение", callback_data="admin:complaints")],
        [InlineKeyboardButton(text="👥 Онлайн", callback_data="admin:online")],
        [InlineKeyboardButton(text="🔍 Найти пользователя по ID", callback_data="admin:find")],
        [InlineKeyboardButton(text="🔧 Уведомить об обновлении", callback_data="admin:notify_update")],
    ])

def kb_complaint_action(complaint_id, accused_uid, reporter_uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Бан 3ч нарушителю", callback_data=f"cadm:ban3:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="🚫 Бан 24ч нарушителю", callback_data=f"cadm:ban24:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан нарушителю", callback_data=f"cadm:banperm:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение нарушителю", callback_data=f"cadm:warn:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение жалобщику (ложная)", callback_data=f"cadm:warnrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="🚫 Бан жалобщику (ложная)", callback_data=f"cadm:banrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="✅ Отклонить жалобу", callback_data=f"cadm:dismiss:{complaint_id}:0")],
    ])

def kb_user_actions(target_uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Бан 3ч", callback_data=f"uadm:ban3:{target_uid}"),
         InlineKeyboardButton(text="🚫 Бан 24ч", callback_data=f"uadm:ban24:{target_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан", callback_data=f"uadm:banperm:{target_uid}"),
         InlineKeyboardButton(text="✅ Разбан", callback_data=f"uadm:unban:{target_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение", callback_data=f"uadm:warn:{target_uid}"),
         InlineKeyboardButton(text="❌ Кик из чата", callback_data=f"uadm:kick:{target_uid}")],
    ])

# ====================== УТИЛИТЫ ======================
def get_queue(mode):
    if mode == "simple": return waiting_simple
    if mode == "flirt": return waiting_flirt
    if mode == "kink": return waiting_kink
    return waiting_anon

def get_rating(u):
    return u.get("likes", 0) - u.get("dislikes", 0)

async def cleanup(uid, state=None):
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink]:
        if uid in q: q.remove(uid)
    partner = active_chats.pop(uid, None)
    if partner:
        active_chats.pop(partner, None)
        await remove_chat_from_db(uid, partner)
    if state: await state.clear()
    return partner

async def unavailable(message: types.Message, reason="сначала заверши текущее действие"):
    await message.answer(f"⚠️ Сейчас недоступно — {reason}.")

async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать / перезапустить"),
        BotCommand(command="find", description="Найти собеседника"),
        BotCommand(command="stop", description="Завершить чат"),
        BotCommand(command="next", description="Следующий собеседник"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="reset", description="Сбросить профиль полностью"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="admin", description="Админ панель"),
    ])

async def do_find(uid, state):
    u = await get_user(uid)
    if not u or not u.get("name") or not u.get("mode"): return False

    mode = u["mode"]
    my_interests = set(u.get("interests", "").split(",")) if u.get("interests") else set()
    my_rating = get_rating(u)
    only_own = u.get("only_own_mode", False)
    search_gender = u.get("search_gender", "any")
    search_age_min = u.get("search_age_min", 16) or 16
    search_age_max = u.get("search_age_max", 99) or 99

    queues = [get_queue(mode)]
    if not only_own:
        if mode == "flirt" and u.get("accept_kink"): queues.append(waiting_kink)
        if mode == "kink" and u.get("accept_flirt"): queues.append(waiting_flirt)

    candidates = []
    for q in queues:
        for pid in list(q):
            if pid == uid: continue
            pu = await get_user(pid)
            if not pu: continue
            if search_gender != "any" and pu.get("gender") != search_gender: continue
            p_age = pu.get("age", 0) or 0
            if p_age < search_age_min or p_age > search_age_max: continue
            if mode == "simple" and not pu.get("accept_simple", True): continue
            if mode == "flirt" and not pu.get("accept_flirt", True): continue
            if mode == "kink" and not pu.get("accept_kink", False): continue
            p_interests = set(pu.get("interests", "").split(",")) if pu.get("interests") else set()
            common = len(my_interests & p_interests)
            rating_diff = abs(get_rating(pu) - my_rating)
            candidates.append((pid, common, rating_diff, q))

    partner = None
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
        await save_chat_to_db(uid, partner, "profile")

        pu = await get_user(partner)
        g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
        p_text = (
            f"👤 Собеседник найден!\n"
            f"Имя: {pu.get('name','Аноним')}\n"
            f"Возраст: {pu.get('age','?')}\n"
            f"Пол: {g_map.get(pu.get('gender',''),'?')}\n"
            f"Режим: {MODE_NAMES.get(pu.get('mode',''),'—')}\n"
            f"Интересы: {(pu.get('interests','') or '').replace(',', ', ') or '—'}\n"
            f"⭐ Рейтинг: {get_rating(pu)}"
        )
        my_text = (
            f"👤 Собеседник найден!\n"
            f"Имя: {u.get('name','Аноним')}\n"
            f"Возраст: {u.get('age','?')}\n"
            f"Пол: {g_map.get(u.get('gender',''),'?')}\n"
            f"Режим: {MODE_NAMES.get(u.get('mode',''),'—')}\n"
            f"Интересы: {(u.get('interests','') or '').replace(',', ', ') or '—'}\n"
            f"⭐ Рейтинг: {get_rating(u)}"
        )
        await bot.send_message(uid, p_text)
        await bot.send_message(partner, my_text)
        await bot.send_message(uid, "✅ Начинайте общение!", reply_markup=kb_chat())
        await bot.send_message(partner, "✅ Начинайте общение!", reply_markup=kb_chat())
        return True
    else:
        q = get_queue(mode)
        if uid not in q: q.append(uid)
        await state.set_state(Chat.waiting)
        asyncio.create_task(notify_no_partner(uid))
        return False

async def notify_no_partner(uid):
    await asyncio.sleep(60)
    if uid in (waiting_simple + waiting_flirt + waiting_kink + waiting_anon):
        try:
            await bot.send_message(uid,
                "😔 Пока никого нет по твоим параметрам.\n\n"
                "Можешь подождать или изменить настройки (/settings)",
                reply_markup=kb_cancel_search()
            )
        except: pass

async def end_chat(uid, state, go_next=False):
    partner = active_chats.pop(uid, None)
    if partner:
        active_chats.pop(partner, None)
        await remove_chat_from_db(uid, partner)
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
        u = await get_user(uid)
        if u and u.get("mode"):
            mode = u["mode"]
            online = len(get_queue(mode))
            await bot.send_message(uid,
                f"👥 В режиме {MODE_NAMES[mode]}: {online} чел.\n\n🔍 Ищем...",
                reply_markup=kb_cancel_search()
            )
            await do_find(uid, state)

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
    if not u or not u.get("accepted_rules"):
        await state.set_state(Rules.waiting)
        await message.answer(WELCOME_TEXT, reply_markup=kb_lang())
    else:
        await message.answer("👋 С возвращением в MatchMe!", reply_markup=kb_main())

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

@dp.message(StateFilter(Rules.waiting))
async def rules_other(message: types.Message):
    await message.answer("👆 Выбери язык чтобы продолжить.")

# ====================== СБРОС ПРОФИЛЯ ======================
@dp.message(Command("reset"), StateFilter("*"))
async def cmd_reset(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current == str(Chat.chatting):
        await unavailable(message, "сначала выйди из чата")
        return
    await state.set_state(ResetProfile.confirm)
    await message.answer(
        "⚠️ Полный сброс профиля!\n\n"
        "Будут удалены:\n"
        "• Имя, возраст, пол\n"
        "• Режим и интересы\n"
        "• Настройки поиска\n"
        "• Рейтинг и лайки\n\n"
        "❗ Бан и предупреждения сохранятся.\n\n"
        "Ты уверен?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, сбросить всё", callback_data="reset:confirm")],
            [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="reset:cancel")],
        ])
    )

@dp.callback_query(F.data == "reset:confirm", StateFilter(ResetProfile.confirm))
async def reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    await cleanup(uid, state)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET
                name=NULL, age=NULL, gender=NULL, mode=NULL,
                interests='', likes=0, dislikes=0,
                accept_simple=TRUE, accept_flirt=TRUE, accept_kink=FALSE,
                only_own_mode=FALSE, search_gender='any',
                search_age_min=16, search_age_max=99
            WHERE uid=$1
        """, uid)
    await callback.message.edit_text("✅ Профиль полностью сброшен!")
    await callback.message.answer(
        "👋 Добро пожаловать снова!\nНажми '🔍 Поиск по анкете' чтобы заполнить анкету заново.",
        reply_markup=kb_main()
    )
    await callback.answer()

@dp.callback_query(F.data == "reset:cancel", StateFilter(ResetProfile.confirm))
async def reset_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Сброс отменён.")
    await callback.message.answer("Возврат в меню.", reply_markup=kb_main())
    await callback.answer()

# ====================== АНОНИМНЫЙ ПОИСК ======================
@dp.message(F.text == "⚡ Анонимный поиск", StateFilter("*"))
async def anon_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current in [str(Reg.name), str(Reg.age), str(Reg.gender), str(Reg.mode), str(Reg.interests)]:
        await unavailable(message, "сначала заверши заполнение анкеты")
        return
    if current == str(Chat.chatting):
        await unavailable(message, "ты уже в чате")
        return
    await cleanup(uid, state)
    banned, until = await is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer("🚫 Ты заблокирован навсегда.")
        else:
            await message.answer(f"🚫 Ты заблокирован до {until.strftime('%H:%M %d.%m.%Y')}")
        return
    await ensure_user(uid)
    await message.answer("⚡ Ищем анонимного собеседника...", reply_markup=kb_cancel_search())

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
            await save_chat_to_db(uid, partner, "anon")
            await bot.send_message(uid, "👤 Соединено с анонимным собеседником! Удачи! 🎉", reply_markup=kb_chat())
            await bot.send_message(partner, "👤 Соединено с анонимным собеседником! Удачи! 🎉", reply_markup=kb_chat())
        else:
            waiting_anon.append(uid)
            await state.set_state(Chat.waiting)

# ====================== ПОИСК ПО АНКЕТЕ ======================
@dp.message(F.text.in_(["🔍 Поиск по анкете", "🔍 Найти собеседника"]), StateFilter("*"))
@dp.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current in [str(Reg.name), str(Reg.age), str(Reg.gender), str(Reg.mode), str(Reg.interests)]:
        await unavailable(message, "сначала заверши заполнение анкеты")
        return
    if current == str(Chat.chatting):
        await unavailable(message, "ты уже в чате — нажми ❌ Стоп")
        return
    await cleanup(uid, state)
    await ensure_user(uid)
    banned, until = await is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer("🚫 Ты заблокирован навсегда.")
        else:
            await message.answer(f"🚫 Ты заблокирован до {until.strftime('%H:%M %d.%m.%Y')}")
        return
    u = await get_user(uid)
    if not u or not u.get("name") or not u.get("mode"):
        await state.set_state(Reg.name)
        await message.answer(RULES_PROFILE, reply_markup=kb_rules_profile())
        return
    mode = u["mode"]
    online = len(get_queue(mode))
    await message.answer(
        f"👥 В режиме {MODE_NAMES[mode]}: {online} чел.\n\n🔍 Ищем...",
        reply_markup=kb_cancel_search()
    )
    await do_find(uid, state)

# ====================== РЕГИСТРАЦИЯ ======================
@dp.message(F.text == "✅ Понятно, начать анкету", StateFilter(Reg.name))
async def start_reg(message: types.Message, state: FSMContext):
    await message.answer("📝 Как тебя зовут?", reply_markup=kb_cancel_reg())

@dp.message(F.text == "❌ Отменить анкету", StateFilter("*"))
async def cancel_reg(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Анкета отменена.", reply_markup=kb_main())

BLOCKED_TEXTS = ["⚡ Анонимный поиск", "🔍 Поиск по анкете", "👤 Мой профиль", "⚙️ Настройки", "❓ Помощь"]

@dp.message(StateFilter(Reg.name))
async def reg_name(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await unavailable(message, "сначала введи имя")
        return
    if txt == "✅ Понятно, начать анкету":
        await message.answer("📝 Как тебя зовут?", reply_markup=kb_cancel_reg())
        return
    await ensure_user(uid)
    await update_user(uid, name=txt.strip()[:20])
    await state.set_state(Reg.age)
    await message.answer("🎂 Сколько тебе лет?", reply_markup=kb_cancel_reg())

@dp.message(StateFilter(Reg.age))
async def reg_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await unavailable(message, "сначала введи возраст")
        return
    if not txt.isdigit():
        await message.answer("❗ Введи число.")
        return
    age = int(txt)
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
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await unavailable(message, "сначала выбери пол")
        return
    if "Парень" in txt: gender = "male"
    elif "Девушка" in txt: gender = "female"
    elif "Другое" in txt: gender = "other"
    else:
        await message.answer("Выбери пол из кнопок 👇", reply_markup=kb_gender())
        return
    await update_user(uid, gender=gender)
    await state.set_state(Reg.mode)
    await message.answer("💬 Выбери режим общения:", reply_markup=kb_mode())

@dp.message(StateFilter(Reg.mode))
async def reg_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await unavailable(message, "сначала выбери режим")
        return
    txt_lower = txt.lower()
    if "общение" in txt_lower: mode = "simple"
    elif "флирт" in txt_lower: mode = "flirt"
    elif "kink" in txt_lower or "ролевые" in txt_lower: mode = "kink"
    else:
        await message.answer("Выбери режим из кнопок 👇", reply_markup=kb_mode())
        return
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
        await callback.answer()
        u = await get_user(uid)
        mode = u.get("mode", "simple")
        online = len(get_queue(mode))
        await callback.message.answer(
            f"👥 В режиме {MODE_NAMES[mode]}: {online} чел.\n\n🔍 Ищем...",
            reply_markup=kb_cancel_search()
        )
        await do_find(uid, state)
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
    if "⏭" in txt or txt == "⏭ Следующий":
        await end_chat(uid, state, go_next=True)
        return
    if txt == "❌ Стоп":
        await end_chat(uid, state, go_next=False)
        return
    if "🚩" in txt or txt == "🚩 Жалоба":
        await state.set_state(Complaint.reason)
        await message.answer("🚩 Укажи причину жалобы:", reply_markup=kb_complaint())
        return
    if "👍" in txt or txt == "👍 Лайк":
        if uid in active_chats:
            partner = active_chats[uid]
            pu = await get_user(partner)
            await update_user(partner, likes=pu.get("likes", 0) + 1)
            await message.answer("👍 Лайк отправлен!")
            try: await bot.send_message(partner, "👍 Собеседник поставил тебе лайк! ⭐")
            except: pass
        return
    if "🏠" in txt or txt == "🏠 Главное меню":
        await end_chat(uid, state, go_next=False)
        return
    if txt.startswith("/start"):
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
        await message.answer("⚠️ Не спамь! Подожди немного.")
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

# ====================== ЖАЛОБА ======================
@dp.callback_query(F.data == "rep:cancel", StateFilter(Complaint.reason))
async def complaint_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Chat.chatting)
    await callback.message.edit_text("↩️ Жалоба отменена.")
    await callback.answer()

@dp.callback_query(F.data.startswith("rep:"), StateFilter(Complaint.reason))
async def handle_complaint(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    reason_map = {
        "minor": "Несовершеннолетние",
        "spam": "Спам/Реклама",
        "abuse": "Угрозы/Оскорбления",
        "other": "Другое"
    }
    reason = reason_map.get(callback.data.split(":", 1)[1], "Другое")
    partner = active_chats.get(uid)
    if not partner:
        await callback.message.edit_text("Ты не в чате.")
        await state.clear()
        return
    async with db_pool.acquire() as conn:
        complaint_id = await conn.fetchval(
            "INSERT INTO complaints_log (from_uid, to_uid, reason) VALUES ($1,$2,$3) RETURNING id",
            uid, partner, reason
        )
        pu = await get_user(partner)
        await update_user(partner, complaints=pu.get("complaints", 0) + 1)
    active_chats.pop(uid, None)
    active_chats.pop(partner, None)
    await remove_chat_from_db(uid, partner)
    await state.clear()
    await callback.message.edit_text(
        f"🚩 Жалоба #{complaint_id} отправлена.\nПричина: {reason}\n\nАдминистратор рассмотрит её вручную."
    )
    await bot.send_message(uid, "Чат завершён.", reply_markup=kb_main())
    try:
        await bot.send_message(partner, "⚠️ На тебя подана жалоба. Администратор рассматривает её.", reply_markup=kb_main())
        pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
        await FSMContext(dp.storage, key=pkey).clear()
    except: pass
    pu = await get_user(partner)
    ru = await get_user(uid)
    g_map = {"male": "Парень", "female": "Девушка", "other": "Другое"}
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🚩 Новая жалоба #{complaint_id}!\n\n"
            f"👤 Жалобщик: {uid}\n"
            f"Имя: {ru.get('name','?') if ru else '?'} | Возраст: {ru.get('age','?') if ru else '?'} | {g_map.get(ru.get('gender',''),'?') if ru else '?'}\n\n"
            f"👤 Обвиняемый: {partner}\n"
            f"Имя: {pu.get('name','?') if pu else '?'} | Возраст: {pu.get('age','?') if pu else '?'} | {g_map.get(pu.get('gender',''),'?') if pu else '?'}\n"
            f"Жалоб на нём: {pu.get('complaints', 0) if pu else '?'}\n\n"
            f"📋 Причина: {reason}\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            reply_markup=kb_complaint_action(complaint_id, partner, uid)
        )
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
    uid = message.from_user.id
    current = await state.get_state()
    if current in [str(Reg.name), str(Reg.age), str(Reg.gender), str(Reg.mode), str(Reg.interests)]:
        await unavailable(message, "сначала заверши анкету или нажми '❌ Отменить анкету'")
        return
    await end_chat(uid, state, go_next=False)

@dp.message(Command("next"), StateFilter("*"))
async def cmd_next(message: types.Message, state: FSMContext):
    await end_chat(message.from_user.id, state, go_next=True)

# ====================== ПРОФИЛЬ ======================
@dp.message(F.text == "👤 Мой профиль", StateFilter("*"))
@dp.message(Command("profile"), StateFilter("*"))
async def show_profile(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current in [str(Reg.name), str(Reg.age), str(Reg.gender), str(Reg.mode), str(Reg.interests)]:
        await unavailable(message, "сначала заверши заполнение анкеты")
        return
    if current == str(Chat.chatting):
        await unavailable(message, "ты в чате — нажми ❌ Стоп")
        return
    await ensure_user(uid)
    u = await get_user(uid)
    if not u or not u.get("name"):
        await message.answer("Анкета не заполнена. Нажми '🔍 Поиск по анкете'", reply_markup=kb_main())
        return
    g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
    await message.answer(
        f"👤 Профиль:\n"
        f"Имя: {u['name']}\n"
        f"Возраст: {u.get('age', '—')}\n"
        f"Пол: {g_map.get(u.get('gender',''), '—')}\n"
        f"Режим: {MODE_NAMES.get(u.get('mode',''), '—')}\n"
        f"Интересы: {(u.get('interests','') or '').replace(',', ', ') or '—'}\n"
        f"⭐ Рейтинг: {get_rating(u)}\n"
        f"👍 Лайков: {u.get('likes',0)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count',0)}",
        reply_markup=kb_edit()
    )

# ====================== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ======================
@dp.callback_query(F.data.startswith("edit:"))
async def edit_profile_cb(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    await callback.answer()
    if field == "name":
        await state.set_state(EditProfile.name)
        await callback.message.answer("✏️ Новое имя:", reply_markup=kb_cancel_reg())
    elif field == "age":
        await state.set_state(EditProfile.age)
        await callback.message.answer("🎂 Новый возраст:", reply_markup=kb_cancel_reg())
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
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("↩️ Возврат в меню.", reply_markup=kb_main())
        return
    await update_user(message.from_user.id, name=message.text.strip()[:20])
    await state.clear()
    await message.answer("✅ Имя обновлено!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.age))
async def edit_age(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("↩️ Возврат в меню.", reply_markup=kb_main())
        return
    if not message.text or not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer("❗ Введи число от 16 до 99")
        return
    await update_user(message.from_user.id, age=int(message.text))
    await state.clear()
    await message.answer("✅ Возраст обновлён!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.gender))
async def edit_gender(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("↩️ Возврат в меню.", reply_markup=kb_main())
        return
    uid = message.from_user.id
    txt = message.text or ""
    if "Парень" in txt: g = "male"
    elif "Девушка" in txt: g = "female"
    else: g = "other"
    await update_user(uid, gender=g)
    await state.clear()
    await message.answer("✅ Пол обновлён!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.mode))
async def edit_mode(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("↩️ Возврат в меню.", reply_markup=kb_main())
        return
    uid = message.from_user.id
    txt = (message.text or "").lower()
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
    current = await state.get_state()
    if current in [str(Reg.name), str(Reg.age), str(Reg.gender), str(Reg.mode), str(Reg.interests)]:
        await unavailable(message, "сначала заверши анкету")
        return
    if current == str(Chat.chatting):
        await unavailable(message, "ты в чате")
        return
    await ensure_user(uid)
    await message.answer("⚙️ Настройки поиска:", reply_markup=await kb_settings(uid))

@dp.callback_query(F.data.startswith("set:"))
async def toggle_setting(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    key = callback.data.split(":", 1)[1]
    u = await get_user(uid)
    if key == "gender":
        await state.set_state(EditProfile.search_gender)
        await callback.message.answer("👤 Кого хочешь искать?", reply_markup=kb_search_gender())
        await callback.answer()
        return
    elif key == "age":
        await state.set_state(EditProfile.search_age)
        await callback.message.answer("🎂 Введи диапазон возраста (например: 18-25):", reply_markup=kb_cancel_reg())
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

@dp.message(StateFilter(EditProfile.search_gender))
async def set_search_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""
    if txt == "◀️ Назад":
        await state.clear()
        await message.answer("⚙️ Настройки:", reply_markup=await kb_settings(uid))
        return
    if "Парня" in txt: sg = "male"
    elif "Девушку" in txt: sg = "female"
    elif "Другое" in txt: sg = "other"
    else: sg = "any"
    await update_user(uid, search_gender=sg)
    await state.clear()
    await message.answer("✅ Фильтр по полу сохранён!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.search_age))
async def set_search_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("↩️ Возврат.", reply_markup=kb_main())
        return
    try:
        parts = message.text.split("-")
        min_age = int(parts[0].strip())
        max_age = int(parts[1].strip())
        if 16 <= min_age <= max_age <= 99:
            await update_user(uid, search_age_min=min_age, search_age_max=max_age)
            await state.clear()
            await message.answer(f"✅ Возраст поиска: {min_age}–{max_age}", reply_markup=kb_main())
        else:
            await message.answer("❗ Диапазон должен быть в пределах 16–99, например: 18-25")
    except:
        await message.answer("❗ Формат: 18-25")

# ====================== ПОМОЩЬ ======================
@dp.message(F.text == "❓ Помощь", StateFilter("*"))
@dp.message(Command("help"), StateFilter("*"))
async def show_help(message: types.Message, state: FSMContext):
    await message.answer(
        "🆘 Помощь MatchMe:\n\n"
        "⚡ Анонимный поиск — быстрый поиск без анкеты\n"
        "🔍 Поиск по анкете — поиск по режиму и интересам\n"
        "⚙️ Настройки — фильтры по полу, возрасту, режиму\n"
        "👤 Профиль — твоя анкета и рейтинг\n\n"
        "В чате:\n"
        "⏭ Следующий — другой собеседник\n"
        "❌ Стоп — завершить чат\n"
        "🚩 Жалоба — только при реальных нарушениях!\n"
        "👍 Лайк — поднять рейтинг собеседнику\n\n"
        "/reset — полный сброс профиля\n"
        "Если что-то сломалось — /start",
        reply_markup=kb_main()
    )

# ====================== ПЕРЕЗАПУСК ======================
@dp.message(F.text.contains("Перезапустить"), StateFilter("*"))
async def cmd_restart(message: types.Message, state: FSMContext):
    await cmd_start(message, state)

# ====================== АДМИН ПАНЕЛЬ ======================
@dp.message(Command("admin"), StateFilter("*"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛡 Админ панель MatchMe", reply_markup=kb_admin_main())

@dp.callback_query(F.data.startswith("admin:"))
async def admin_actions(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]

    if action == "stats":
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE ban_until IS NOT NULL")
            total_complaints = await conn.fetchval("SELECT COUNT(*) FROM complaints_log")
            pending = await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE")
        online_now = len(active_chats) // 2
        in_search = len(waiting_anon) + len(waiting_simple) + len(waiting_flirt) + len(waiting_kink)
        await callback.message.answer(
            f"📊 Статистика MatchMe:\n\n"
            f"👥 Всего пользователей: {total}\n"
            f"🟢 Активны за 24ч: {today}\n"
            f"💬 В чатах сейчас: {online_now} пар\n"
            f"🔍 В поиске: {in_search}\n"
            f"🚫 Заблокировано: {banned}\n"
            f"🚩 Всего жалоб: {total_complaints}\n"
            f"⏳ Не рассмотрено: {pending}"
        )

    elif action == "complaints":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM complaints_log WHERE reviewed=FALSE ORDER BY created_at ASC LIMIT 5"
            )
        if not rows:
            await callback.message.answer("✅ Нет жалоб на рассмотрении.")
        else:
            for r in rows:
                ru = await get_user(r["from_uid"])
                pu = await get_user(r["to_uid"])
                g_map = {"male": "Парень", "female": "Девушка", "other": "Другое"}
                await callback.message.answer(
                    f"🚩 Жалоба #{r['id']}\n\n"
                    f"👤 Жалобщик: {r['from_uid']}\n"
                    f"Имя: {ru.get('name','?') if ru else '?'} | Возраст: {ru.get('age','?') if ru else '?'}\n\n"
                    f"👤 Обвиняемый: {r['to_uid']}\n"
                    f"Имя: {pu.get('name','?') if pu else '?'} | Возраст: {pu.get('age','?') if pu else '?'}\n"
                    f"Жалоб на нём: {pu.get('complaints',0) if pu else '?'}\n\n"
                    f"📋 Причина: {r['reason']}\n"
                    f"🕐 {r['created_at'].strftime('%d.%m %H:%M')}",
                    reply_markup=kb_complaint_action(r["id"], r["to_uid"], r["from_uid"])
                )

    elif action == "online":
        await callback.message.answer(
            f"👥 Онлайн сейчас:\n\n"
            f"💬 В чатах: {len(active_chats) // 2} пар\n"
            f"⚡ Анонимный поиск: {len(waiting_anon)}\n"
            f"💬 Поиск Общение: {len(waiting_simple)}\n"
            f"💋 Поиск Флирт: {len(waiting_flirt)}\n"
            f"🔥 Поиск Kink: {len(waiting_kink)}"
        )

    elif action == "find":
        await state.set_state(AdminState.waiting_user_id)
        await callback.message.answer("🔍 Введи Telegram ID пользователя:")

    elif action == "notify_update":
        await callback.message.answer(
            "Через сколько минут обновление?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="1 мин", callback_data="upd:1"),
                 InlineKeyboardButton(text="2 мин", callback_data="upd:2")],
                [InlineKeyboardButton(text="5 мин", callback_data="upd:5"),
                 InlineKeyboardButton(text="🔴 Сейчас", callback_data="upd:0")],
            ])
        )
    await callback.answer()

@dp.callback_query(F.data.startswith("upd:"))
async def handle_update_notify(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    minutes = int(callback.data.split(":")[1])
    if minutes == 0:
        text = "🔧 Бот обновляется прямо сейчас. Активные чаты восстановятся автоматически!"
    else:
        text = f"🔧 Через {minutes} мин. бот будет обновлён. Активные чаты восстановятся автоматически!"

    notified = 0
    for uid, partner in list(active_chats.items()):
        if uid < partner:
            try:
                await bot.send_message(uid, text, reply_markup=kb_main())
                await bot.send_message(partner, text, reply_markup=kb_main())
                notified += 2
            except: pass

    async with db_pool.acquire() as conn:
        all_users = await conn.fetch(
            "SELECT uid FROM users WHERE last_seen > NOW() - INTERVAL '7 days'"
        )
    active_uids = set(active_chats.keys())
    sent = 0
    for row in all_users:
        if row["uid"] in active_uids: continue
        try:
            await bot.send_message(row["uid"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except: pass

    await callback.message.answer(f"✅ Уведомление отправлено {notified + sent} пользователям.")
    await callback.answer()

@dp.message(StateFilter(AdminState.waiting_user_id))
async def admin_find_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("❗ ID должен быть числом.")
        return
    target_uid = int(txt)
    u = await get_user(target_uid)
    if not u:
        await message.answer(f"❌ Пользователь {target_uid} не найден.")
        return
    g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
    ban_status = "Нет"
    if u.get("ban_until"):
        ban_status = "Навсегда 🚫" if u["ban_until"] == "permanent" else f"до {u['ban_until'][:16]}"
    in_chat = "✅ Да" if target_uid in active_chats else "❌ Нет"
    in_queue = "✅ Да" if any(target_uid in q for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink]) else "❌ Нет"
    await message.answer(
        f"👤 Пользователь {target_uid}:\n\n"
        f"Имя: {u.get('name','—')}\n"
        f"Возраст: {u.get('age','—')}\n"
        f"Пол: {g_map.get(u.get('gender',''), '—')}\n"
        f"Режим: {MODE_NAMES.get(u.get('mode',''), '—')}\n"
        f"Интересы: {(u.get('interests','') or '').replace(',', ', ') or '—'}\n"
        f"⭐ Рейтинг: {get_rating(u)}\n"
        f"👍 Лайков: {u.get('likes',0)}\n"
        f"🚩 Жалоб: {u.get('complaints',0)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count',0)}\n"
        f"🚫 Бан: {ban_status}\n"
        f"💬 В чате: {in_chat}\n"
        f"🔍 В поиске: {in_queue}",
        reply_markup=kb_user_actions(target_uid)
    )

# ====================== ДЕЙСТВИЯ С ЖАЛОБОЙ ======================
@dp.callback_query(F.data.startswith("cadm:"))
async def admin_complaint_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    complaint_id = int(parts[2])
    target_uid = int(parts[3]) if parts[3] != "0" else None

    async def mark_reviewed(action_text):
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE complaints_log SET reviewed=TRUE, admin_action=$1 WHERE id=$2",
                action_text, complaint_id
            )

    if action == "ban3" and target_uid:
        until = datetime.now() + timedelta(hours=3)
        await update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан 3ч")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}. Бан 3ч → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Тебя заблокировали на 3 часа по жалобе.")
        except: pass

    elif action == "ban24" and target_uid:
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан 24ч")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}. Бан 24ч → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Тебя заблокировали на 24 часа по жалобе.")
        except: pass

    elif action == "banperm" and target_uid:
        await update_user(target_uid, ban_until="permanent")
        await mark_reviewed("Перм бан")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}. Перм бан → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Ты заблокирован навсегда.")
        except: pass

    elif action == "warn" and target_uid:
        u = await get_user(target_uid)
        await update_user(target_uid, warn_count=u.get("warn_count", 0) + 1)
        await mark_reviewed("Предупреждение нарушителю")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}. Предупреждение → {target_uid}")
        try: await bot.send_message(target_uid, "⚠️ Предупреждение от администратора. Следующее нарушение — бан.")
        except: pass

    elif action == "warnrep" and target_uid:
        u = await get_user(target_uid)
        await update_user(target_uid, warn_count=u.get("warn_count", 0) + 1)
        await mark_reviewed("Предупреждение жалобщику (ложная)")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}: ложная. Предупреждение → {target_uid}")
        try: await bot.send_message(target_uid, "⚠️ Твоя жалоба признана необоснованной. Предупреждение. Злоупотребление = бан.")
        except: pass

    elif action == "banrep" and target_uid:
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан жалобщику (ложная)")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}: ложная. Бан 24ч → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Заблокирован на 24ч за злоупотребление жалобами.")
        except: pass

    elif action == "dismiss":
        await mark_reviewed("Отклонена")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id} отклонена.")

    await callback.answer()

# ====================== ДЕЙСТВИЯ С ПОЛЬЗОВАТЕЛЕМ ======================
@dp.callback_query(F.data.startswith("uadm:"))
async def admin_user_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    target_uid = int(parts[2])

    if action == "ban3":
        until = datetime.now() + timedelta(hours=3)
        await update_user(target_uid, ban_until=until.isoformat())
        await callback.answer("✅ Бан 3ч")
        await callback.message.answer(f"🚫 {target_uid} заблокирован на 3 часа")
        try: await bot.send_message(target_uid, "🚫 Тебя заблокировал администратор на 3 часа.")
        except: pass

    elif action == "ban24":
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await callback.answer("✅ Бан 24ч")
        await callback.message.answer(f"🚫 {target_uid} заблокирован на 24 часа")
        try: await bot.send_message(target_uid, "🚫 Тебя заблокировал администратор на 24 часа.")
        except: pass

    elif action == "banperm":
        await update_user(target_uid, ban_until="permanent")
        await callback.answer("✅ Перм бан")
        await callback.message.answer(f"🚫 {target_uid} заблокирован навсегда")
        try: await bot.send_message(target_uid, "🚫 Ты заблокирован навсегда администратором.")
        except: pass

    elif action == "unban":
        await update_user(target_uid, ban_until=None)
        await callback.answer("✅ Разбан")
        await callback.message.answer(f"✅ {target_uid} разблокирован")
        try: await bot.send_message(target_uid, "✅ Ты разблокирован! Добро пожаловать обратно в MatchMe.")
        except: pass

    elif action == "warn":
        u = await get_user(target_uid)
        await update_user(target_uid, warn_count=u.get("warn_count", 0) + 1)
        await callback.answer("✅ Предупреждение")
        await callback.message.answer(f"⚠️ {target_uid} получил предупреждение")
        try: await bot.send_message(target_uid, "⚠️ Тебе вынесено предупреждение от администратора.")
        except: pass

    elif action == "kick":
        if target_uid in active_chats:
            partner = active_chats.pop(target_uid, None)
            if partner: active_chats.pop(partner, None)
            await remove_chat_from_db(target_uid, partner)
            try: await bot.send_message(target_uid, "❌ Тебя кикнул администратор.", reply_markup=kb_main())
            except: pass
            if partner:
                try: await bot.send_message(partner, "😔 Собеседник покинул чат.", reply_markup=kb_main())
                except: pass
            await callback.answer("✅ Кикнут")
            await callback.message.answer(f"✅ {target_uid} кикнут из чата")
        else:
            await callback.answer("Пользователь не в чате", show_alert=True)

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
            await remove_chat_from_db(uid, partner)
            try: await bot.send_message(uid, "⏰ Чат завершён из-за неактивности (7 мин).", reply_markup=kb_main())
            except: pass
            try: await bot.send_message(partner, "⏰ Чат завершён из-за неактивности (7 мин).", reply_markup=kb_main())
            except: pass

# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    await set_commands()
    asyncio.create_task(inactivity_checker())
    print("🚀 MatchMe запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
