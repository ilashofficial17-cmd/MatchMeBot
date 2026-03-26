import asyncio
import os
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand,
    LabeledPrice, PreCheckoutQuery
)
import asyncpg

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))
VENICE_API_KEY = os.environ.get("VENICE_API_KEY")
VENICE_API_URL = "https://api.venice.ai/api/v1/chat/completions"
AI_FREE_LIMIT = 10
PREMIUM_PRICE_STARS = 149

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

db_pool = None
active_chats = {}
waiting_anon = []
waiting_simple = []
waiting_flirt = []
waiting_kink = []
waiting_simple_premium = []
waiting_flirt_premium = []
waiting_kink_premium = []
last_msg_time = {}
msg_count = {}
pairing_lock = asyncio.Lock()
chat_logs = {}
ai_sessions = {}

STOP_WORDS = [
    "предлагаю услуги", "оказываю услуги", "интим услуги",
    "досуг", "escort", "эскорт", "проститутка", "проститут",
    "вирт за деньги", "вирт платно", "за донат",
    "подпишись на канал", "перейди по ссылке", "мой канал",
    "казино", "ставки на спорт", "заработок в телеграм",
    "крипта х10", "пассивный доход",
    "мне 12", "мне 13", "мне 14", "мне 15",
    "школьница ищу", "школьник ищу", "продаю", "порно за деньги",
]

AI_CHARACTERS = {
    "max": {
        "name": "Макс 👨", "emoji": "👨",
        "description": "Дружелюбный парень, поговорит на любые темы",
        "premium": False, "model": "venice-uncensored",
        "system": "Ты Макс — общительный парень 25 лет. Дружелюбный, с юмором. Говоришь естественно. Если разговор уходит в пошлость — мягко меняешь тему. Отвечаешь коротко — 1-3 предложения."
    },
    "sonya": {
        "name": "Соня 👩", "emoji": "👩",
        "description": "Добрая девушка, хорошо слушает и поддерживает",
        "premium": False, "model": "venice-uncensored",
        "system": "Ты Соня — добрая девушка 23 лет. Хорошо слушаешь, поддерживаешь. Говоришь тепло. Если пошлость — вежливо переводишь тему. Отвечаешь коротко — 1-3 предложения."
    },
    "artem": {
        "name": "Артём 😏", "emoji": "😏",
        "description": "Флиртующий парень, комплименты и игривый разговор",
        "premium": False, "model": "venice-uncensored",
        "system": "Ты Артём — уверенный парень 26 лет. Флиртуешь красиво — без пошлости но с искрой. Делаешь комплименты, держишь интригу. Отвечаешь коротко — 1-3 предложения."
    },
    "alina": {
        "name": "Алина 💋", "emoji": "💋",
        "description": "Игривая девушка, кокетливая и притягательная",
        "premium": False, "model": "venice-uncensored",
        "system": "Ты Алина — кокетливая девушка 24 лет. Флиртуешь легко и естественно. Игривая но не вульгарная. Отвечаешь коротко — 1-3 предложения."
    },
    "dominant": {
        "name": "Доминант 😈", "emoji": "😈",
        "description": "Властный и уверенный, ведёт сценарий",
        "premium": True, "model": "venice-uncensored-role-play",
        "system": "Ты Доминант — властный, уверенный. Ведёшь разговор и сценарий 18+. Говоришь чётко с командными нотками. Отвечаешь кратко — 2-4 предложения."
    },
    "submissive": {
        "name": "Сабмиссив 🐾", "emoji": "🐾",
        "description": "Покорный и мягкий, следует за тобой",
        "premium": True, "model": "venice-uncensored-role-play",
        "system": "Ты Сабмиссив — мягкий, покорный партнёр в ролевых играх 18+. Следуешь за собеседником. Отвечаешь нежно — 2-3 предложения."
    },
    "rolemaster": {
        "name": "Ролевой мастер 🎭", "emoji": "🎭",
        "description": "Придумывает сценарии и играет любую роль",
        "premium": True, "model": "venice-uncensored-role-play",
        "system": "Ты Ролевой мастер — опытный рассказчик 18+. Придумываешь сценарии, играешь любую роль. Отвечаешь с описанием — 3-5 предложений."
    },
}

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

class AIChat(StatesGroup):
    choosing = State()
    chatting = State()

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
                premium_until TEXT DEFAULT NULL,
                show_premium BOOLEAN DEFAULT TRUE,
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
            ("premium_until", "TEXT DEFAULT NULL"),
            ("show_premium", "BOOLEAN DEFAULT TRUE"),
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
                chat_log TEXT DEFAULT '',
                stop_words_found BOOLEAN DEFAULT FALSE,
                reviewed BOOLEAN DEFAULT FALSE,
                admin_action TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        for col, definition in [
            ("chat_log", "TEXT DEFAULT ''"),
            ("stop_words_found", "BOOLEAN DEFAULT FALSE"),
            ("reviewed", "BOOLEAN DEFAULT FALSE"),
            ("admin_action", "TEXT DEFAULT NULL"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE complaints_log ADD COLUMN IF NOT EXISTS {col} {definition}")
            except: pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_chats_db (
                uid1 BIGINT PRIMARY KEY,
                uid2 BIGINT,
                chat_type TEXT DEFAULT 'profile',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Автоматически даём вечный премиум админу
        await conn.execute(
            "INSERT INTO users (uid, premium_until, show_premium) VALUES ($1, 'permanent', TRUE) ON CONFLICT (uid) DO UPDATE SET premium_until='permanent'",
            ADMIN_ID
        )

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
        # Если это админ — даём вечный премиум
        if uid == ADMIN_ID:
            await conn.execute(
                "UPDATE users SET premium_until='permanent' WHERE uid=$1 AND premium_until IS NULL",
                uid
            )

async def update_user(uid, **kwargs):
    if not kwargs: return
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs))
    vals = list(kwargs.values())
    async with db_pool.acquire() as conn:
        await conn.execute(f"UPDATE users SET {sets} WHERE uid=$1", uid, *vals)

async def is_premium(uid):
    if uid == ADMIN_ID:
        return True
    u = await get_user(uid)
    if not u or not u.get("premium_until"):
        return False
    if u["premium_until"] == "permanent":
        return True
    try:
        premium_until = datetime.fromisoformat(u["premium_until"])
        if datetime.now() < premium_until:
            return True
        await update_user(uid, premium_until=None)
    except: pass
    return False

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

# ====================== ЛОГИРОВАНИЕ ======================
def get_chat_key(uid1, uid2):
    return (min(uid1, uid2), max(uid1, uid2))

def log_message(uid1, uid2, sender_uid, text):
    key = get_chat_key(uid1, uid2)
    if key not in chat_logs:
        chat_logs[key] = []
    chat_logs[key].append({
        "sender": sender_uid,
        "text": text[:200],
        "time": datetime.now().strftime("%H:%M:%S")
    })
    if len(chat_logs[key]) > 10:
        chat_logs[key] = chat_logs[key][-10:]

def get_chat_log_text(uid1, uid2):
    key = get_chat_key(uid1, uid2)
    logs = chat_logs.get(key, [])
    if not logs: return "Переписка пуста"
    lines = []
    for msg in logs:
        sender = "Жалобщик" if msg["sender"] == uid1 else "Обвиняемый"
        lines.append(f"[{msg['time']}] {sender}: {msg['text']}")
    return "\n".join(lines)

def check_stop_words(uid1, uid2):
    key = get_chat_key(uid1, uid2)
    logs = chat_logs.get(key, [])
    all_text = " ".join(msg["text"].lower() for msg in logs)
    found = [w for w in STOP_WORDS if w.lower() in all_text]
    return len(found) > 0, found

def clear_chat_log(uid1, uid2):
    key = get_chat_key(uid1, uid2)
    if key in chat_logs:
        del chat_logs[key]

# ====================== ПРИКОЛЫ ПО ВОЗРАСТУ ======================
def get_age_joke(age):
    if age <= 6: return "🐥 Цыплёнок, тебе ещё в садик рано!"
    elif age <= 12: return "🎮 Эй малой, тут не мультики! Подрасти сначала."
    elif age <= 15: return "🙅 Стоп! Тебе нет 16. Возвращайся когда подрастёшь!"
    elif age <= 17: return "😄 О, молодёжь! Добро пожаловать, только не балуйся."
    elif age <= 25: return "🔥 Самый сок! Добро пожаловать в MatchMe!"
    elif age <= 35: return "😎 Взрослый человек, солидно!"
    elif age <= 50: return "🧐 Опытный пользователь! Уважаем."
    elif age <= 70: return "💪 Ого, ещё в деле! Молодость в душе — главное."
    elif age <= 90: return "👴 Дедуля/бабуля освоили интернет! Снимаем шляпу."
    else: return "😂 Серьёзно?! Тебе домой надо, не в анонимный чат!"

# ====================== VENICE AI ======================
async def ask_venice(character_id: str, history: list, user_message: str) -> str:
    if not VENICE_API_KEY:
        return "😔 ИИ временно недоступен."
    char = AI_CHARACTERS[character_id]
    messages = [{"role": "system", "content": char["system"]}]
    for msg in history[-10:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                VENICE_API_URL,
                headers={"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"},
                json={"model": char["model"], "messages": messages, "max_tokens": 300, "temperature": 0.9},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                elif resp.status == 402:
                    return "💳 ИИ временно недоступен — нет средств на балансе."
                else:
                    return "😔 ИИ временно недоступен. Попробуй позже."
    except:
        return "😔 Ошибка соединения с ИИ."

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
• Реклама любых услуг — бан без предупреждения
• Продажа интим-услуг — перманентный бан
• Контент с несовершеннолетними — перманентный бан
• Пошлые темы без согласия в режиме Общение — бан
• Спам, угрозы, оскорбления — бан
• Ложные жалобы — бан за злоупотребление

⚠️ Градация банов:
• Лёгкое нарушение: предупреждение → бан 3ч → бан 24ч
• Грубое нарушение: бан сразу
• Особо грубое: перманентный бан

ℹ️ Все жалобы проверяются администратором вручную.

Нажми ✅ Принять правила для продолжения."""

RULES_PROFILE = """📜 Правила общения:

• Уважай собеседника
• 👍 Лайк — если понравилось общение
• 🚩 Жалоба — только при реальных нарушениях!
• Реклама = бан, пошлятина без согласия = бан
• Ложная жалоба = санкции против тебя

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
        [KeyboardButton(text="🤖 ИИ Собеседник")],
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)

def kb_lang():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]
    ], resize_keyboard=True)

def kb_rules():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Принять правила")]], resize_keyboard=True)

def kb_rules_profile():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Понятно, начать анкету")]], resize_keyboard=True)

def kb_cancel_reg():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить анкету")]], resize_keyboard=True)

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
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить поиск")]], resize_keyboard=True)

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

def kb_ai_characters(premium=False):
    buttons = [
        [InlineKeyboardButton(text="👨 Макс", callback_data="aichar:max"),
         InlineKeyboardButton(text="👩 Соня", callback_data="aichar:sonya")],
        [InlineKeyboardButton(text="😏 Артём", callback_data="aichar:artem"),
         InlineKeyboardButton(text="💋 Алина", callback_data="aichar:alina")],
    ]
    if premium:
        buttons.append([
            InlineKeyboardButton(text="😈 Доминант", callback_data="aichar:dominant"),
            InlineKeyboardButton(text="🐾 Сабмиссив", callback_data="aichar:submissive")
        ])
        buttons.append([InlineKeyboardButton(text="🎭 Ролевой мастер", callback_data="aichar:rolemaster")])
    else:
        buttons.append([
            InlineKeyboardButton(text="😈 Доминант ⭐", callback_data="aichar:locked"),
            InlineKeyboardButton(text="🐾 Сабмиссив ⭐", callback_data="aichar:locked")
        ])
        buttons.append([InlineKeyboardButton(text="🎭 Ролевой мастер ⭐", callback_data="aichar:locked")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="aichar:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_ai_chat():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Сменить персонажа")],
        [KeyboardButton(text="🔍 Найти живого собеседника")],
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def kb_interests(mode, selected):
    interests = INTERESTS_MAP.get(mode, [])
    buttons = []
    for interest in interests:
        mark = "✅ " if interest in selected else ""
        buttons.append([InlineKeyboardButton(text=f"{mark}{interest}", callback_data=f"int:{interest}")])
    buttons.append([InlineKeyboardButton(text="✅ Готово — сохранить", callback_data="int:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_complaint():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔞 Несовершеннолетние", callback_data="rep:minor")],
        [InlineKeyboardButton(text="💰 Спам / Реклама", callback_data="rep:spam")],
        [InlineKeyboardButton(text="😡 Угрозы / Оскорбления", callback_data="rep:abuse")],
        [InlineKeyboardButton(text="🔞 Пошлятина без согласия", callback_data="rep:nsfw")],
        [InlineKeyboardButton(text="🔄 Другое", callback_data="rep:other")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="rep:cancel")],
    ])

async def kb_settings(uid):
    u = await get_user(uid)
    if not u: return InlineKeyboardMarkup(inline_keyboard=[])
    sg_map = {"any": "🔀 Все", "male": "👨 Парни", "female": "👩 Девушки", "other": "⚧ Другое"}
    sg = sg_map.get(u.get("search_gender", "any"), "🔀 Все")
    show_p = u.get("show_premium", True)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'✅' if u.get('accept_simple', True) else '❌'} Принимать из Общения", callback_data="set:simple")],
        [InlineKeyboardButton(text=f"{'✅' if u.get('accept_flirt', True) else '❌'} Принимать из Флирта", callback_data="set:flirt")],
        [InlineKeyboardButton(text=f"{'✅' if u.get('accept_kink', False) else '❌'} Принимать из Kink", callback_data="set:kink")],
        [InlineKeyboardButton(text=f"{'✅' if u.get('only_own_mode', False) else '❌'} Только свой режим", callback_data="set:only_own")],
        [InlineKeyboardButton(text=f"👤 Искать: {sg}", callback_data="set:gender")],
        [InlineKeyboardButton(text=f"🎂 Возраст: {u.get('search_age_min',16)}–{u.get('search_age_max',99)}", callback_data="set:age")],
        [InlineKeyboardButton(text=f"{'✅' if show_p else '❌'} Показывать значок ⭐ в профиле", callback_data="set:show_premium")],
    ])

def kb_edit():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Имя", callback_data="edit:name"),
         InlineKeyboardButton(text="🎂 Возраст", callback_data="edit:age")],
        [InlineKeyboardButton(text="⚧ Пол", callback_data="edit:gender"),
         InlineKeyboardButton(text="💬 Режим", callback_data="edit:mode")],
        [InlineKeyboardButton(text="🎯 Интересы", callback_data="edit:interests")],
    ])

async def kb_admin_main():
    pending = await get_pending_complaints()
    badge = f" ({pending})" if pending > 0 else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text=f"🚩 Жалобы{badge}", callback_data="admin:complaints")],
        [InlineKeyboardButton(text="👥 Онлайн", callback_data="admin:online")],
        [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin:find")],
        [InlineKeyboardButton(text="🔧 Уведомить об обновлении", callback_data="admin:notify_update")],
    ])

def kb_complaint_action(complaint_id, accused_uid, reporter_uid, has_log=False, stop_words=False):
    sw_text = "⚠️ Стоп-слова: ДА" if stop_words else "✅ Стоп-слова: НЕТ"
    buttons = [[InlineKeyboardButton(text=sw_text, callback_data="noop")]]
    if has_log:
        buttons.append([InlineKeyboardButton(text="📄 Показать переписку", callback_data=f"clog:show:{complaint_id}")])
    buttons += [
        [InlineKeyboardButton(text="🚫 Бан 3ч нарушителю", callback_data=f"cadm:ban3:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="🚫 Бан 24ч нарушителю", callback_data=f"cadm:ban24:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан нарушителю", callback_data=f"cadm:banperm:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение нарушителю", callback_data=f"cadm:warn:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение жалобщику (ложная)", callback_data=f"cadm:warnrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="🚫 Бан жалобщику (ложная)", callback_data=f"cadm:banrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="✅ Отклонить жалобу", callback_data=f"cadm:dismiss:{complaint_id}:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_user_actions(target_uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Бан 3ч", callback_data=f"uadm:ban3:{target_uid}"),
         InlineKeyboardButton(text="🚫 Бан 24ч", callback_data=f"uadm:ban24:{target_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан", callback_data=f"uadm:banperm:{target_uid}"),
         InlineKeyboardButton(text="✅ Разбан", callback_data=f"uadm:unban:{target_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение", callback_data=f"uadm:warn:{target_uid}"),
         InlineKeyboardButton(text="❌ Кик из чата", callback_data=f"uadm:kick:{target_uid}")],
        [InlineKeyboardButton(text="⭐ Дать премиум 30д", callback_data=f"uadm:premium:{target_uid}"),
         InlineKeyboardButton(text="⭐ Забрать премиум", callback_data=f"uadm:unpremium:{target_uid}")],
    ])

def kb_premium():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Купить Premium — {PREMIUM_PRICE_STARS} Stars",
            callback_data="buy:premium"
        )],
        [InlineKeyboardButton(text="❓ Что даёт Premium?", callback_data="buy:info")],
    ])

# ====================== УТИЛИТЫ ======================
def get_queue(mode, premium=False):
    if premium:
        if mode == "simple": return waiting_simple_premium
        if mode == "flirt": return waiting_flirt_premium
        if mode == "kink": return waiting_kink_premium
    else:
        if mode == "simple": return waiting_simple
        if mode == "flirt": return waiting_flirt
        if mode == "kink": return waiting_kink
    return waiting_anon

def get_rating(u):
    return u.get("likes", 0) - u.get("dislikes", 0)

async def cleanup(uid, state=None):
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink,
              waiting_simple_premium, waiting_flirt_premium, waiting_kink_premium]:
        if uid in q: q.remove(uid)
    partner = active_chats.pop(uid, None)
    if partner:
        active_chats.pop(partner, None)
        await remove_chat_from_db(uid, partner)
        clear_chat_log(uid, partner)
    ai_sessions.pop(uid, None)
    if state: await state.clear()
    return partner

async def unavailable(message: types.Message, reason="сначала заверши текущее действие"):
    await message.answer(f"⚠️ Сейчас недоступно — {reason}.")

async def get_pending_complaints():
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE") or 0

async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать / перезапустить"),
        BotCommand(command="find", description="Найти собеседника"),
        BotCommand(command="stop", description="Завершить чат"),
        BotCommand(command="next", description="Следующий собеседник"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="premium", description="Premium подписка"),
        BotCommand(command="reset", description="Сбросить профиль"),
        BotCommand(command="ai", description="ИИ Собеседник"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="admin", description="Админ панель"),
    ])

async def get_premium_badge(uid):
    u = await get_user(uid)
    if not u: return ""
    if not u.get("show_premium", True): return ""
    if await is_premium(uid): return " ⭐"
    return ""

async def do_find(uid, state):
    u = await get_user(uid)
    if not u or not u.get("name") or not u.get("mode"): return False

    mode = u["mode"]
    user_premium = await is_premium(uid)
    my_interests = set(u.get("interests", "").split(",")) if u.get("interests") else set()
    my_rating = get_rating(u)
    only_own = u.get("only_own_mode", False)
    search_gender = u.get("search_gender", "any")
    search_age_min = u.get("search_age_min", 16) or 16
    search_age_max = u.get("search_age_max", 99) or 99

    # Премиум очереди имеют приоритет
    queues_to_search = []
    if user_premium:
        queues_to_search.append(get_queue(mode, True))
    queues_to_search.append(get_queue(mode, False))
    if not only_own:
        if mode == "flirt" and u.get("accept_kink"):
            if user_premium: queues_to_search.append(get_queue("kink", True))
            queues_to_search.append(get_queue("kink", False))
        if mode == "kink" and u.get("accept_flirt"):
            if user_premium: queues_to_search.append(get_queue("flirt", True))
            queues_to_search.append(get_queue("flirt", False))

    candidates = []
    for q in queues_to_search:
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
            p_premium = await is_premium(pid)
            priority = 0 if p_premium else 1
            candidates.append((pid, common, rating_diff, priority, q))

    partner = None
    if candidates:
        candidates.sort(key=lambda x: (x[3], -x[1], x[2]))
        best = candidates[0]
        partner = best[0]
        best[4].remove(partner)

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
        p_badge = await get_premium_badge(partner)
        my_badge = await get_premium_badge(uid)

        p_text = (
            f"👤 Собеседник найден!{p_badge}\n"
            f"Имя: {pu.get('name','Аноним')}\n"
            f"Возраст: {pu.get('age','?')}\n"
            f"Пол: {g_map.get(pu.get('gender',''),'?')}\n"
            f"Режим: {MODE_NAMES.get(pu.get('mode',''),'—')}\n"
            f"Интересы: {(pu.get('interests','') or '').replace(',', ', ') or '—'}\n"
            f"⭐ Рейтинг: {get_rating(pu)}"
        )
        my_text = (
            f"👤 Собеседник найден!{my_badge}\n"
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
        q = get_queue(mode, user_premium)
        if uid not in q: q.append(uid)
        await state.set_state(Chat.waiting)
        asyncio.create_task(notify_no_partner(uid))
        return False

async def notify_no_partner(uid):
    await asyncio.sleep(60)
    all_waiting = waiting_simple + waiting_flirt + waiting_kink + waiting_anon + \
                  waiting_simple_premium + waiting_flirt_premium + waiting_kink_premium
    if uid in all_waiting:
        try:
            await bot.send_message(uid,
                "😔 Пока никого нет по твоим параметрам.\n\n"
                "Попробуй:\n"
                "🤖 Поговорить с ИИ персонажем\n"
                "⚙️ Изменить настройки поиска",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🤖 ИИ Собеседник", callback_data="goto:ai")],
                    [InlineKeyboardButton(text="⚙️ Настройки", callback_data="goto:settings")],
                    [InlineKeyboardButton(text="⏳ Продолжить ждать", callback_data="goto:wait")],
                ])
            )
        except: pass

@dp.callback_query(F.data.startswith("goto:"))
async def goto_action(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    action = callback.data.split(":", 1)[1]
    if action == "ai":
        for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink,
                  waiting_simple_premium, waiting_flirt_premium, waiting_kink_premium]:
            if uid in q: q.remove(uid)
        await state.clear()
        await _show_ai_menu(callback.message, state, uid)
    elif action == "settings":
        await show_settings(callback.message, state)
    elif action == "wait":
        await callback.answer("⏳ Продолжаем ждать...")
    await callback.answer()

async def end_chat(uid, state, go_next=False):
    partner = active_chats.pop(uid, None)
    if partner:
        active_chats.pop(partner, None)
        await remove_chat_from_db(uid, partner)
        clear_chat_log(uid, partner)
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink,
              waiting_simple_premium, waiting_flirt_premium, waiting_kink_premium]:
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
            user_premium = await is_premium(uid)
            q_len = len(get_queue(mode, False)) + len(get_queue(mode, True))
            await bot.send_message(uid,
                f"👥 В режиме {MODE_NAMES[mode]}: {q_len} чел.\n\n🔍 Ищем...",
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
            await message.answer("🚫 Ты заблокирован навсегда.")
        else:
            await message.answer(f"🚫 Ты заблокирован до {until.strftime('%H:%M %d.%m.%Y')}")
        return
    u = await get_user(uid)
    if not u or not u.get("accepted_rules"):
        await state.set_state(Rules.waiting)
        await message.answer(WELCOME_TEXT, reply_markup=kb_lang())
    else:
        badge = await get_premium_badge(uid)
        await message.answer(f"👋 С возвращением в MatchMe!{badge}", reply_markup=kb_main())

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

# ====================== PREMIUM ======================
@dp.message(Command("premium"), StateFilter("*"))
async def cmd_premium(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    user_premium = await is_premium(uid)
    if user_premium:
        u = await get_user(uid)
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            await message.answer("⭐ У тебя вечный Premium!\n\nВсе функции доступны навсегда 🔥")
        else:
            try:
                until = datetime.fromisoformat(u["premium_until"])
                await message.answer(f"⭐ Premium активен до {until.strftime('%d.%m.%Y %H:%M')}\n\nВсе функции доступны!")
            except:
                await message.answer("⭐ Premium активен!")
        return

    await message.answer(
        f"⭐ MatchMe Premium\n\n"
        f"Что входит:\n"
        f"• 😈 Kink ИИ персонажи (Доминант, Сабмиссив, Ролевой мастер)\n"
        f"• 🤖 Безлимитный ИИ чат\n"
        f"• 🚀 Приоритет в поиске собеседника\n"
        f"• ⭐ Значок Premium в профиле\n\n"
        f"Цена: {PREMIUM_PRICE_STARS} Telegram Stars (~$2)\n"
        f"Срок: 30 дней",
        reply_markup=kb_premium()
    )

@dp.callback_query(F.data == "buy:info", StateFilter("*"))
async def premium_info(callback: types.CallbackQuery):
    await callback.answer(
        "⭐ Premium даёт: Kink ИИ персонажи, безлимитный ИИ чат, приоритет в поиске и значок в профиле!",
        show_alert=True
    )

@dp.callback_query(F.data == "buy:premium", StateFilter("*"))

async def buy_premium(callback: types.CallbackQuery):
    uid = callback.from_user.id
    await callback.answer()
    await bot.send_invoice(
        chat_id=uid,
        title="MatchMe Premium",
        description="Kink ИИ персонажи, безлимитный ИИ чат, приоритет в поиске — 30 дней",
        payload="premium_30days",
        currency="XTR",
        prices=[LabeledPrice(label="Premium 30 дней", amount=PREMIUM_PRICE_STARS)],
    )

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    uid = message.from_user.id
    until = datetime.now() + timedelta(days=30)
    await update_user(uid, premium_until=until.isoformat())
    await message.answer(
        f"🎉 Premium активирован!\n\n"
        f"⭐ Действует до {until.strftime('%d.%m.%Y')}\n\n"
        f"Теперь тебе доступны:\n"
        f"• 😈 Kink ИИ персонажи\n"
        f"• 🤖 Безлимитный ИИ\n"
        f"• 🚀 Приоритет в поиске\n"
        f"• ⭐ Значок в профиле",
        reply_markup=kb_main()
    )

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
        "❗ Бан, предупреждения и Premium сохранятся.\n\nТы уверен?",
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
    await callback.message.edit_text("✅ Профиль сброшен!")
    await callback.message.answer("👋 Нажми '🔍 Поиск по анкете' чтобы заполнить анкету заново.", reply_markup=kb_main())
    await callback.answer()

@dp.callback_query(F.data == "reset:cancel", StateFilter(ResetProfile.confirm))
async def reset_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Сброс отменён.")
    await callback.message.answer("Возврат в меню.", reply_markup=kb_main())
    await callback.answer()

# ====================== ИИ СОБЕСЕДНИК ======================
async def _show_ai_menu(message: types.Message, state: FSMContext, uid: int):
    user_premium = await is_premium(uid)
    await state.set_state(AIChat.choosing)
    await message.answer(
        "🤖 ИИ Собеседник\n\n"
        "😊 Просто общение — Макс и Соня\n"
        "💋 Флирт — Артём и Алина\n"
        f"🔥 Kink (18+) — {'доступно ⭐' if user_premium else 'только Premium 🔒'}\n\n"
        "Выбери с кем хочешь поговорить:",
        reply_markup=kb_ai_characters(user_premium)
    )

@dp.message(F.text == "🤖 ИИ Собеседник", StateFilter("*"))
@dp.message(Command("ai"), StateFilter("*"))
async def ai_menu(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current == str(Chat.chatting):
        await unavailable(message, "ты в чате с живым собеседником")
        return
    if current in [str(Reg.name), str(Reg.age), str(Reg.gender), str(Reg.mode), str(Reg.interests)]:
        await unavailable(message, "сначала заверши анкету")
        return
    await _show_ai_menu(message, state, uid)

@dp.callback_query(F.data.startswith("aichar:"), StateFilter(AIChat.choosing))
async def choose_ai_character(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    char_id = callback.data.split(":", 1)[1]

    if char_id == "back":
        await state.clear()
        await callback.message.answer("↩️ Возврат в меню.", reply_markup=kb_main())
        await callback.answer()
        return

    if char_id == "locked":
        await callback.answer(
            f"🔒 Этот персонаж доступен только в Premium!\n\nКупи Premium за {PREMIUM_PRICE_STARS} Stars и получи доступ ко всем Kink персонажам.",
            show_alert=True
        )
        return

    if char_id not in AI_CHARACTERS:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return

    char = AI_CHARACTERS[char_id]
    user_premium = await is_premium(uid)

    if char["premium"] and not user_premium:
        await callback.answer("🔒 Только для Premium!", show_alert=True)
        return

    ai_sessions[uid] = {"character": char_id, "history": [], "msg_count": 0}
    await state.set_state(AIChat.chatting)

    limit_text = "⭐ Premium: безлимит" if user_premium else f"🆓 Бесплатно: {AI_FREE_LIMIT} сообщений"
    await callback.message.edit_text(
        f"{'✅' if not char['premium'] else '🔥'} Ты общаешься с {char['name']}\n"
        f"{char['description']}\n\n"
        f"{limit_text}\n\nНапиши что-нибудь чтобы начать!"
    )
    await callback.message.answer("💬 Чат с ИИ активен", reply_markup=kb_ai_chat())

    greeting = await ask_venice(char_id, [], "Поприветствуй меня и начни разговор. Коротко, 1-2 предложения.")
    if greeting:
        ai_sessions[uid]["history"].append({"role": "assistant", "content": greeting})
        await callback.message.answer(f"{char['emoji']} {greeting}")
    await callback.answer()

@dp.message(StateFilter(AIChat.chatting))
async def ai_chat_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""

    if "Сменить персонажа" in txt:
        ai_sessions.pop(uid, None)
        user_premium = await is_premium(uid)
        await state.set_state(AIChat.choosing)
        await message.answer("Выбери персонажа:", reply_markup=kb_ai_characters(user_premium))
        return
    if "Найти живого" in txt:
        ai_sessions.pop(uid, None)
        await state.clear()
        await message.answer("🔍 Ищем живого собеседника...", reply_markup=kb_cancel_search())
        await cmd_find(message, state)
        return
    if "🏠" in txt or "Главное меню" in txt:
        ai_sessions.pop(uid, None)
        await state.clear()
        await message.answer("🏠 Главное меню", reply_markup=kb_main())
        return

    if uid not in ai_sessions:
        await state.clear()
        await message.answer("Сессия потеряна. Начни заново.", reply_markup=kb_main())
        return

    session = ai_sessions[uid]
    char_id = session["character"]
    char = AI_CHARACTERS[char_id]
    msg_count = session["msg_count"]
    user_premium = await is_premium(uid)

    if not user_premium and msg_count >= AI_FREE_LIMIT:
        await message.answer(
            f"⏰ Ты использовал {AI_FREE_LIMIT} бесплатных сообщений.\n\n"
            f"⭐ Купи Premium за {PREMIUM_PRICE_STARS} Stars и получи безлимитный ИИ чат!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"⭐ Купить Premium — {PREMIUM_PRICE_STARS} Stars", callback_data="buy:premium")],
                [InlineKeyboardButton(text="🔍 Найти живого собеседника", callback_data="goto:find")]
            ])
        )
        return

    await bot.send_chat_action(uid, "typing")
    session["history"].append({"role": "user", "content": txt})
    response = await ask_venice(char_id, session["history"][:-1], txt)
    session["history"].append({"role": "assistant", "content": response})
    session["msg_count"] += 1

    remaining = ""
    if not user_premium:
        left = AI_FREE_LIMIT - session["msg_count"]
        if left <= 3:
            remaining = f"\n\n_💬 Осталось {left} бесплатных сообщений_"

    await message.answer(f"{char['emoji']} {response}{remaining}")

@dp.callback_query(F.data == "goto:find")
async def goto_find(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    ai_sessions.pop(uid, None)
    await state.clear()
    await callback.message.answer("🔍 Ищем...", reply_markup=kb_cancel_search())
    await cmd_find(callback.message, state)
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
    if current == str(AIChat.chatting):
        ai_sessions.pop(uid, None)
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
    if current == str(AIChat.chatting):
        ai_sessions.pop(uid, None)
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
    user_premium = await is_premium(uid)
    q_len = len(get_queue(mode, False)) + len(get_queue(mode, True))
    premium_badge = " ⭐" if user_premium else ""
    await message.answer(
        f"👥 В режиме {MODE_NAMES[mode]}: {q_len} чел.\n"
        f"{'🚀 Приоритетный поиск активен' + premium_badge if user_premium else '🔍 Ищем...'}\n",
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

BLOCKED_TEXTS = ["⚡ Анонимный поиск", "🔍 Поиск по анкете", "👤 Мой профиль",
                 "⚙️ Настройки", "❓ Помощь", "🤖 ИИ Собеседник"]

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
    joke = get_age_joke(age)
    if age <= 15:
        await message.answer(f"{joke}\n\nВведи правильный возраст (минимум 16):")
        return
    if age > 99:
        await message.answer(f"{joke}\n\nВведи реальный возраст (16–99).")
        return
    await update_user(uid, age=age)
    await message.answer(joke)
    await asyncio.sleep(0.5)
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
        q_len = len(get_queue(mode, False)) + len(get_queue(mode, True))
        await callback.message.answer(
            f"👥 В режиме {MODE_NAMES[mode]}: {q_len} чел.\n\n🔍 Ищем...",
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
    if message.text:
        log_message(uid, partner, uid, message.text)
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
        "minor": "Несовершеннолетние", "spam": "Спам/Реклама",
        "abuse": "Угрозы/Оскорбления", "nsfw": "Пошлятина без согласия", "other": "Другое"
    }
    reason = reason_map.get(callback.data.split(":", 1)[1], "Другое")
    partner = active_chats.get(uid)
    if not partner:
        await callback.message.edit_text("Ты не в чате.")
        await state.clear()
        return
    log_text = get_chat_log_text(uid, partner)
    stop_found, _ = check_stop_words(uid, partner)
    async with db_pool.acquire() as conn:
        complaint_id = await conn.fetchval(
            "INSERT INTO complaints_log (from_uid, to_uid, reason, chat_log, stop_words_found) VALUES ($1,$2,$3,$4,$5) RETURNING id",
            uid, partner, reason, log_text, stop_found
        )
        pu = await get_user(partner)
        await update_user(partner, complaints=pu.get("complaints", 0) + 1)
    active_chats.pop(uid, None)
    active_chats.pop(partner, None)
    await remove_chat_from_db(uid, partner)
    clear_chat_log(uid, partner)
    await state.clear()
    await callback.message.edit_text(f"🚩 Жалоба #{complaint_id} отправлена.\nПричина: {reason}\n\nАдминистратор рассмотрит её.")
    await bot.send_message(uid, "Чат завершён.", reply_markup=kb_main())
    try:
        await bot.send_message(partner, "⚠️ На тебя подана жалоба.", reply_markup=kb_main())
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
            f"Имя: {ru.get('name','?') if ru else '?'} | Возраст: {ru.get('age','?') if ru else '?'}\n\n"
            f"👤 Обвиняемый: {partner}\n"
            f"Имя: {pu.get('name','?') if pu else '?'} | Возраст: {pu.get('age','?') if pu else '?'}\n"
            f"Жалоб: {pu.get('complaints',0) if pu else '?'}\n\n"
            f"📋 Причина: {reason}\n"
            f"{'⚠️ Найдены подозрительные слова!' if stop_found else '✅ Стоп-слова не найдены'}\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            reply_markup=kb_complaint_action(complaint_id, partner, uid, bool(log_text), stop_found)
        )
    except: pass
    await callback.answer()

# ====================== ОТМЕНА ПОИСКА ======================
@dp.message(F.text == "❌ Отменить поиск", StateFilter("*"))
async def cancel_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    all_q = [waiting_anon, waiting_simple, waiting_flirt, waiting_kink,
             waiting_simple_premium, waiting_flirt_premium, waiting_kink_premium]
    removed = any(uid in q for q in all_q)
    for q in all_q:
        if uid in q: q.remove(uid)
    await state.clear()
    await message.answer("❌ Поиск отменён." if removed else "Ты не в поиске.", reply_markup=kb_main())

# ====================== СТОП / СЛЕДУЮЩИЙ ======================
@dp.message(Command("stop"), StateFilter("*"))
async def cmd_stop(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current in [str(Reg.name), str(Reg.age), str(Reg.gender), str(Reg.mode), str(Reg.interests)]:
        await unavailable(message, "сначала заверши анкету")
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
    user_premium = await is_premium(uid)
    show_badge = u.get("show_premium", True)

    # Формируем статус премиума
    if user_premium:
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            premium_status = "⭐ Premium (вечный)"
        else:
            try:
                until = datetime.fromisoformat(u["premium_until"])
                premium_status = f"⭐ Premium до {until.strftime('%d.%m.%Y')}"
            except:
                premium_status = "⭐ Premium"
    else:
        premium_status = "Нет"

    badge = " ⭐" if (user_premium and show_badge) else ""

    await message.answer(
        f"👤 Профиль{badge}:\n"
        f"Имя: {u['name']}\n"
        f"Возраст: {u.get('age', '—')}\n"
        f"Пол: {g_map.get(u.get('gender',''), '—')}\n"
        f"Режим: {MODE_NAMES.get(u.get('mode',''), '—')}\n"
        f"Интересы: {(u.get('interests','') or '').replace(',', ', ') or '—'}\n"
        f"⭐ Рейтинг: {get_rating(u)}\n"
        f"👍 Лайков: {u.get('likes',0)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count',0)}\n"
        f"💎 Статус: {premium_status}",
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
        await message.answer("↩️ Возврат.", reply_markup=kb_main())
        return
    await update_user(message.from_user.id, name=message.text.strip()[:20])
    await state.clear()
    await message.answer("✅ Имя обновлено!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.age))
async def edit_age(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("↩️ Возврат.", reply_markup=kb_main())
        return
    if not message.text or not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer("❗ Введи число от 16 до 99")
        return
    age = int(message.text)
    joke = get_age_joke(age)
    await update_user(message.from_user.id, age=age)
    await state.clear()
    await message.answer(f"{joke}\n\n✅ Возраст обновлён!", reply_markup=kb_main())

@dp.message(StateFilter(EditProfile.gender))
async def edit_gender(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("↩️ Возврат.", reply_markup=kb_main())
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
        await message.answer("↩️ Возврат.", reply_markup=kb_main())
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
    elif key == "show_premium":
        await update_user(uid, show_premium=not u.get("show_premium", True))
        await callback.message.edit_reply_markup(reply_markup=await kb_settings(uid))
        await callback.answer("✅ Изменено")
        return
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
            await message.answer("❗ Диапазон: 16–99, например: 18-25")
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
        "🤖 ИИ Собеседник — поговори с ИИ персонажем\n"
        "⚙️ Настройки — фильтры поиска\n"
        "👤 Профиль — твоя анкета\n"
        "⭐ /premium — Premium подписка\n\n"
        "В чате:\n"
        "⏭ Следующий — другой собеседник\n"
        "❌ Стоп — завершить чат\n"
        "🚩 Жалоба — только при нарушениях!\n"
        "👍 Лайк — поднять рейтинг\n\n"
        "/reset — сбросить профиль\n"
        "Если что-то сломалось — /start",
        reply_markup=kb_main()
    )

@dp.message(F.text.contains("Перезапустить"), StateFilter("*"))
async def cmd_restart(message: types.Message, state: FSMContext):
    await cmd_start(message, state)

# ====================== АДМИН ПАНЕЛЬ ======================
@dp.message(Command("admin"), StateFilter("*"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛡 Админ панель MatchMe", reply_markup=await kb_admin_main())

@dp.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()

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
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
            total_complaints = await conn.fetchval("SELECT COUNT(*) FROM complaints_log")
            pending = await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE")
        online_now = len(active_chats) // 2
        in_search = (len(waiting_anon) + len(waiting_simple) + len(waiting_flirt) + len(waiting_kink) +
                     len(waiting_simple_premium) + len(waiting_flirt_premium) + len(waiting_kink_premium))
        await callback.message.answer(
            f"📊 Статистика MatchMe:\n\n"
            f"👥 Всего пользователей: {total}\n"
            f"🟢 Активны за 24ч: {today}\n"
            f"⭐ Premium пользователей: {premiums}\n"
            f"💬 В чатах сейчас: {online_now} пар\n"
            f"🤖 С ИИ сейчас: {len(ai_sessions)}\n"
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
                has_log = bool(r.get("chat_log"))
                stop_words = bool(r.get("stop_words_found"))
                await callback.message.answer(
                    f"🚩 Жалоба #{r['id']}\n\n"
                    f"👤 Жалобщик: {r['from_uid']}\n"
                    f"Имя: {ru.get('name','?') if ru else '?'} | Возраст: {ru.get('age','?') if ru else '?'}\n\n"
                    f"👤 Обвиняемый: {r['to_uid']}\n"
                    f"Имя: {pu.get('name','?') if pu else '?'} | Возраст: {pu.get('age','?') if pu else '?'}\n"
                    f"Жалоб: {pu.get('complaints',0) if pu else '?'}\n\n"
                    f"📋 Причина: {r['reason']}\n"
                    f"🕐 {r['created_at'].strftime('%d.%m %H:%M')}",
                    reply_markup=kb_complaint_action(r["id"], r["to_uid"], r["from_uid"], has_log, stop_words)
                )

    elif action == "online":
        await callback.message.answer(
            f"👥 Онлайн сейчас:\n\n"
            f"💬 В чатах: {len(active_chats) // 2} пар\n"
            f"🤖 С ИИ: {len(ai_sessions)}\n"
            f"⚡ Анонимный поиск: {len(waiting_anon)}\n"
            f"💬 Общение: {len(waiting_simple)} + {len(waiting_simple_premium)}⭐\n"
            f"💋 Флирт: {len(waiting_flirt)} + {len(waiting_flirt_premium)}⭐\n"
            f"🔥 Kink: {len(waiting_kink)} + {len(waiting_kink_premium)}⭐"
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

@dp.callback_query(F.data.startswith("clog:"))
async def show_chat_log(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    complaint_id = int(parts[2])
    if action == "show":
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT chat_log FROM complaints_log WHERE id=$1", complaint_id)
        if not row or not row["chat_log"]:
            await callback.message.answer("📄 Переписка пуста.")
        else:
            await callback.message.answer(
                f"📄 Переписка жалобы #{complaint_id}:\n\n{row['chat_log']}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"clog:delete:{complaint_id}")]
                ])
            )
    elif action == "delete":
        try: await callback.message.delete()
        except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("upd:"))
async def handle_update_notify(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    minutes = int(callback.data.split(":")[1])
    text = "🔧 Бот обновляется прямо сейчас. Чаты восстановятся автоматически!" if minutes == 0 else f"🔧 Через {minutes} мин. обновление. Чаты восстановятся автоматически!"
    notified = 0
    for uid, partner in list(active_chats.items()):
        if uid < partner:
            try:
                await bot.send_message(uid, text, reply_markup=kb_main())
                await bot.send_message(partner, text, reply_markup=kb_main())
                notified += 2
            except: pass
    async with db_pool.acquire() as conn:
        all_users = await conn.fetch("SELECT uid FROM users WHERE last_seen > NOW() - INTERVAL '7 days'")
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
    prem_status = "Нет"
    if u.get("premium_until"):
        prem_status = "Вечный ⭐" if u["premium_until"] == "permanent" else f"до {u['premium_until'][:16]} ⭐"
    in_chat = "✅" if target_uid in active_chats else "❌"
    with_ai = "✅" if target_uid in ai_sessions else "❌"
    all_q = [waiting_anon, waiting_simple, waiting_flirt, waiting_kink,
             waiting_simple_premium, waiting_flirt_premium, waiting_kink_premium]
    in_queue = "✅" if any(target_uid in q for q in all_q) else "❌"
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
        f"💎 Premium: {prem_status}\n"
        f"💬 В чате: {in_chat} | 🤖 С ИИ: {with_ai} | 🔍 В поиске: {in_queue}",
        reply_markup=kb_user_actions(target_uid)
    )

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
        try: await bot.send_message(target_uid, "🚫 Заблокирован на 3 часа по жалобе.")
        except: pass
    elif action == "ban24" and target_uid:
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан 24ч")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}. Бан 24ч → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Заблокирован на 24 часа по жалобе.")
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
        try: await bot.send_message(target_uid, "⚠️ Предупреждение. Следующее нарушение — бан.")
        except: pass
    elif action == "warnrep" and target_uid:
        u = await get_user(target_uid)
        await update_user(target_uid, warn_count=u.get("warn_count", 0) + 1)
        await mark_reviewed("Предупреждение жалобщику")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}: ложная. Предупреждение → {target_uid}")
        try: await bot.send_message(target_uid, "⚠️ Жалоба признана необоснованной. Предупреждение.")
        except: pass
    elif action == "banrep" and target_uid:
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан жалобщику")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id}: ложная. Бан 24ч → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Заблокирован на 24ч за злоупотребление жалобами.")
        except: pass
    elif action == "dismiss":
        await mark_reviewed("Отклонена")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Жалоба #{complaint_id} отклонена.")
    await callback.answer()

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
        await callback.message.answer(f"🚫 {target_uid} — бан 3ч")
        try: await bot.send_message(target_uid, "🚫 Тебя заблокировал администратор на 3 часа.")
        except: pass
    elif action == "ban24":
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await callback.answer("✅ Бан 24ч")
        await callback.message.answer(f"🚫 {target_uid} — бан 24ч")
        try: await bot.send_message(target_uid, "🚫 Тебя заблокировал администратор на 24 часа.")
        except: pass
    elif action == "banperm":
        await update_user(target_uid, ban_until="permanent")
        await callback.answer("✅ Перм бан")
        await callback.message.answer(f"🚫 {target_uid} — перм бан")
        try: await bot.send_message(target_uid, "🚫 Ты заблокирован навсегда.")
        except: pass
    elif action == "unban":
        await update_user(target_uid, ban_until=None)
        await callback.answer("✅ Разбан")
        await callback.message.answer(f"✅ {target_uid} разблокирован")
        try: await bot.send_message(target_uid, "✅ Ты разблокирован! Добро пожаловать обратно.")
        except: pass
    elif action == "warn":
        u = await get_user(target_uid)
        await update_user(target_uid, warn_count=u.get("warn_count", 0) + 1)
        await callback.answer("✅ Предупреждение")
        await callback.message.answer(f"⚠️ {target_uid} — предупреждение")
        try: await bot.send_message(target_uid, "⚠️ Предупреждение от администратора.")
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
        else:
            await callback.answer("Не в чате", show_alert=True)
    elif action == "premium":
        until = datetime.now() + timedelta(days=30)
        await update_user(target_uid, premium_until=until.isoformat())
        await callback.answer("✅ Premium 30д выдан")
        await callback.message.answer(f"⭐ {target_uid} — Premium 30 дней")
        try: await bot.send_message(target_uid, f"⭐ Тебе выдан Premium на 30 дней! Наслаждайся всеми функциями.", reply_markup=kb_main())
        except: pass
    elif action == "unpremium":
        await update_user(target_uid, premium_until=None)
        await callback.answer("✅ Premium забран")
        await callback.message.answer(f"❌ {target_uid} — Premium убран")
        try: await bot.send_message(target_uid, "❌ Твой Premium был отменён администратором.")
        except: pass

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
            clear_chat_log(uid, partner)
            try: await bot.send_message(uid, "⏰ Чат завершён из-за неактивности (7 мин).", reply_markup=kb_main())
            except: pass
            try: await bot.send_message(partner, "⏰ Чат завершён из-за неактивности (7 мин).", reply_markup=kb_main())
            except: pass

# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    await set_commands()
    asyncio.create_task(inactivity_checker())
    print("🚀 MatchMe с Premium запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
