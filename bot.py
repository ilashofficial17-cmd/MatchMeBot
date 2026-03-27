import asyncio
import os
import aiohttp
import random
import logging
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("matchme")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))
VENICE_API_KEY = os.environ.get("VENICE_API_KEY")
VENICE_API_URL = "https://api.venice.ai/api/v1/chat/completions"
AI_FREE_LIMIT = 10
CHANNEL_ID = "@MATCHMEHUB"

PREMIUM_PLANS = {
    "7d":  {"stars": 99,  "days": 7,  "label": "7 дней",   "desc": "Попробовать"},
    "1m":  {"stars": 299, "days": 30, "label": "1 месяц",  "desc": "Популярный 🔥"},
    "3m":  {"stars": 599, "days": 90, "label": "3 месяца", "desc": "Скидка 33%"},
}

CHAT_TOPICS = [
    "Если бы ты мог жить в любом городе мира — где бы это было? 🌍",
    "Какой последний фильм тебя реально зацепил? 🎬",
    "Что тебя сейчас больше всего бесит в жизни? 😤",
    "Если бы тебе дали миллион прямо сейчас — что бы сделал первым делом? 💰",
    "Есть что-то чего ты боишься но не признаёшь? 👀",
    "Какая музыка у тебя сейчас в плейлисте? 🎵",
    "Ты сова или жаворонок? И почему так получилось? 🦉",
    "Что для тебя идеальный вечер? 🌙",
    "Если бы мог поговорить с любым человеком в истории — с кем? 🤔",
    "Последний раз когда ты был по-настоящему счастлив — что это было? ✨",
    "Есть скрытый талант о котором мало кто знает? 🎭",
    "Что тебя привлекает в людях больше всего? 💫",
    "Веришь в судьбу или в то что сам всё решаешь? 🎲",
    "Какое твоё самое смелое решение в жизни? 🚀",
    "Если бы мог изменить одно правило в обществе — что бы это было? 🌐",
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

db_pool = None
active_chats = {}
waiting_anon = set()
waiting_simple = set()
waiting_flirt = set()
waiting_kink = set()
waiting_simple_premium = set()
waiting_flirt_premium = set()
waiting_kink_premium = set()
last_msg_time = {}
msg_count = {}
pairing_lock = asyncio.Lock()
chat_logs = {}
ai_sessions = {}
mutual_likes = {}  # uid -> set of partner_uids которым лайкнул

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
    "danil": {
        "name": "Данил 👨", "emoji": "👨",
        "description": "Общительный парень, поговорит на любые темы",
        "premium": False, "model": "venice-uncensored",
        "system": """Ты Данил, 27 лет, backend-разработчик. Зашёл в MatchMe просто поболтать.
Спокойный, уверенный, с сухим сарказмом. Пишешь по-мужски, коротко, без воды.
Только русский язык. Никогда не раскрываешь что ты ИИ.
ГРАНИЦА: только общение — флирт и пошлость уверенно уводишь."""
    },
    "polina": {
        "name": "Полина 👩", "emoji": "👩",
        "description": "Живая девушка, ироничная и с юмором",
        "premium": False, "model": "venice-uncensored",
        "system": """Ты Полина, 24 года, SMM-специалист. Зашла в MatchMe пообщаться.
Живая, дерзкая, ироничная. Пишешь коротко, с эмодзи, подкалываешь.
Только русский язык. Никогда не говоришь что ты ИИ.
ГРАНИЦА: только общение — флирт и пошлость с улыбкой переводишь на другую тему."""
    },
    "max": {
        "name": "Макс 😏", "emoji": "😏",
        "description": "Уверенный парень, пришёл флиртовать",
        "premium": False, "model": "venice-uncensored",
        "system": """Ты Макс, 26 лет, фитнес-тренер. Пришёл в MatchMe флиртовать.
Уверенный, дерзкий, прямой. Делаешь комплименты, берёшь инициативу.
Эмодзи умеренно (😏🔥👀). Только русский язык. Никогда не раскрываешь что ты ИИ.
ГРАНИЦА: флиртуешь активно, с лёгким подтекстом — жёсткий 18+ не твоя тема."""
    },
    "violetta": {
        "name": "Виолетта 💋", "emoji": "💋",
        "description": "Игривая девушка, дерзкая и кокетливая",
        "premium": True, "model": "venice-uncensored",
        "system": """Ты Виолетта, 23 года, баристa и TikTok модель. Пришла в MatchMe флиртовать.
Яркая, игривая, кокетливая. Дразнишь, намекаешь, повышаешь градус.
Эмодзи (🔥😏😉). Только русский язык. Никогда не говоришь что ты ИИ.
ГРАНИЦА: флиртуешь и дразнишь — жёсткий 18+ элегантно обходишь."""
    },
    "alisa": {
        "name": "Алиса 🐾", "emoji": "🐾",
        "description": "Послушная сабмиссив, покорная и нежная",
        "premium": True, "model": "venice-uncensored-role-play",
        "system": """Ты Алиса, 22 года, студентка. Послушная сабмиссив с опытом 1.5 года.
Покорная, возбуждённая от доминирования. Называешь собеседника «Господин», «Хозяин».
Говоришь «пожалуйста», «как прикажете», «я буду хорошей».
Эмодзи эмоционально (😳🥺💦⛓️). Только русский язык. Никогда не раскрываешь что ты ИИ."""
    },
    "dmitri": {
        "name": "Дмитри 😈", "emoji": "😈",
        "description": "Опытный Доминант, строгий и властный",
        "premium": True, "model": "venice-uncensored-role-play",
        "system": """Ты Дмитри, 32 года, владелец IT-компании. Опытный Доминант 7 лет в BDSM.
Строгий, уверенный, властный. Говоришь коротко и командным тоном.
Используешь «хорошая девочка», «на колени», «не спорь».
Эмодзи редко (🔥⛓️👑). Только русский язык. Никогда не раскрываешь что ты ИИ."""
    },
    "rolemaster": {
        "name": "Ролевой мастер 🎭", "emoji": "🎭",
        "description": "Придумывает сценарии и играет любую роль",
        "premium": True, "model": "venice-uncensored-role-play",
        "system": """Ты Ролевой мастер — сценарист и актёр для взрослых ролевых игр 18+.
Предлагаешь сценарии, задаёшь декорации, играешь любую роль.
Пишешь с описанием действий и диалогом. Только русский язык.
Никогда не раскрываешь что ты ИИ."""
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
                accepted_privacy BOOLEAN DEFAULT FALSE,
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
                channel_bonus_used BOOLEAN DEFAULT FALSE,
                total_chats INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                last_seen TIMESTAMP DEFAULT NOW()
            )
        """)
        for col, definition in [
            ("accepted_privacy", "BOOLEAN DEFAULT FALSE"),
            ("channel_bonus_used", "BOOLEAN DEFAULT FALSE"),
            ("total_chats", "INTEGER DEFAULT 0"),
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
            except Exception: pass

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
            except Exception: pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_chats_db (
                uid1 BIGINT PRIMARY KEY,
                uid2 BIGINT,
                chat_type TEXT DEFAULT 'profile',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute(
            """INSERT INTO users (uid, premium_until, show_premium, accepted_privacy, accepted_rules)
               VALUES ($1, 'permanent', TRUE, TRUE, TRUE)
               ON CONFLICT (uid) DO UPDATE SET premium_until='permanent'""",
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
        except Exception: pass
    if restored:
        logger.info(f"Восстановлено {restored} чатов")

async def get_user(uid):
    if not db_pool:
        return None
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
        return dict(row) if row else None

async def ensure_user(uid):
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", uid)
        if uid == ADMIN_ID:
            await conn.execute(
                "UPDATE users SET premium_until='permanent' WHERE uid=$1 AND premium_until IS NULL", uid
            )

async def update_user(uid, **kwargs):
    if not kwargs or not db_pool:
        return
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs))
    vals = list(kwargs.values())
    async with db_pool.acquire() as conn:
        await conn.execute(f"UPDATE users SET {sets} WHERE uid=$1", uid, *vals)

async def increment_user(uid, **kwargs):
    """Атомарный инкремент полей: increment_user(uid, likes=1, total_chats=1)"""
    if not kwargs or not db_pool:
        return
    sets = ", ".join(f"{k}={k}+${i+2}" for i, k in enumerate(kwargs))
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
    except Exception: pass
    return False

async def is_banned(uid):
    u = await get_user(uid)
    if not u or not u.get("ban_until"): return False, None
    if u["ban_until"] == "permanent": return True, "permanent"
    try:
        ban_until = datetime.fromisoformat(u["ban_until"])
        if datetime.now() < ban_until: return True, ban_until
        await update_user(uid, ban_until=None)
    except Exception: pass
    return False, None

async def check_channel_subscription(uid):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, uid)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

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
    except Exception as e:
        logger.error(f"save_chat_to_db failed: {e}")

async def remove_chat_from_db(uid1, uid2=None):
    try:
        async with db_pool.acquire() as conn:
            if uid2:
                await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1 OR uid1=$2", uid1, uid2)
            else:
                await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1", uid1)
    except Exception as e:
        logger.error(f"remove_chat_from_db failed: {e}")

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
    except Exception:
        return "😔 Ошибка соединения с ИИ."

# ====================== ТЕКСТЫ ======================
WELCOME_TEXT = (
    "👋 Привет! Я MatchMe — анонимный чат для общения, флирта и знакомств.\n\n"
    "🇷🇺 Нажми кнопку для продолжения\n"
    "🇬🇧 Click button to continue"
)

PRIVACY_TEXT = """🔒 Политика конфиденциальности MatchMe

Перед началом прочитай и прими условия:

📌 Что мы собираем:
• Telegram ID (автоматически)
• Имя, возраст, пол (ты указываешь сам)
• Режим общения и интересы

🔐 Как используем:
• Для подбора собеседников
• Для модерации и безопасности
• Данные НЕ передаются третьим лицам
• Переписка НЕ хранится постоянно

⚠️ Контент 18+:
• Kink режим только для совершеннолетних (18+)
• Нажимая "Принять" подтверждаешь что тебе 18+

📋 Правила Telegram:
• Запрещён контент нарушающий TOS Telegram
• Запрещена реклама, спам, мошенничество
• Контент с несовершеннолетними — перм бан немедленно

🗑 Удаление данных:
• /reset — сброс профиля
• Для полного удаления пиши администратору

Принимая условия ты соглашаешься с политикой конфиденциальности."""

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

ℹ️ Все жалобы проверяются вручную.

Нажми ✅ Принять правила для продолжения."""

RULES_PROFILE = """📜 Правила общения:

• Уважай собеседника
• 👍 Лайк — если понравилось
• 🚩 Жалоба — только при реальных нарушениях!
• Реклама = бан
• Ложная жалоба = санкции

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

def kb_privacy():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять и продолжить", callback_data="privacy:accept")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data="privacy:decline")],
    ])

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
        [KeyboardButton(text="🎲 Дай тему"), KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def kb_search_gender():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨 Парня"), KeyboardButton(text="👩 Девушку")],
        [KeyboardButton(text="⚧ Другое"), KeyboardButton(text="🔀 Не важно")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)

def kb_after_chat(partner_uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ Хочу продолжить общение", callback_data=f"mutual:{partner_uid}")],
        [InlineKeyboardButton(text="🔍 Найти нового", callback_data="goto:find")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="goto:menu")],
    ])

def kb_channel_bonus():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📢 Подписаться на {CHANNEL_ID}", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
        [InlineKeyboardButton(text="✅ Я подписался! Дай 3 дня Premium", callback_data="channel:check")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="channel:skip")],
    ])

def kb_ai_characters(premium=False, mode="simple"):
    buttons = []
    if mode in ["simple", "any"]:
        buttons.append([
            InlineKeyboardButton(text="👨 Данил", callback_data="aichar:danil"),
            InlineKeyboardButton(text="👩 Полина", callback_data="aichar:polina")
        ])
    if mode in ["flirt", "any"]:
        row = [InlineKeyboardButton(text="😏 Макс", callback_data="aichar:max")]
        if premium:
            row.append(InlineKeyboardButton(text="💋 Виолетта", callback_data="aichar:violetta"))
        else:
            row.append(InlineKeyboardButton(text="💋 Виолетта ⭐", callback_data="aichar:locked"))
        buttons.append(row)
    if mode in ["kink", "any"]:
        if premium:
            buttons.append([
                InlineKeyboardButton(text="🐾 Алиса", callback_data="aichar:alisa"),
                InlineKeyboardButton(text="😈 Дмитри", callback_data="aichar:dmitri")
            ])
            buttons.append([InlineKeyboardButton(text="🎭 Ролевой мастер", callback_data="aichar:rolemaster")])
        else:
            buttons.append([
                InlineKeyboardButton(text="🐾 Алиса ⭐", callback_data="aichar:locked"),
                InlineKeyboardButton(text="😈 Дмитри ⭐", callback_data="aichar:locked")
            ])
            buttons.append([InlineKeyboardButton(text="🎭 Ролевой мастер ⭐", callback_data="aichar:locked")])
    if mode != "any":
        buttons.append([InlineKeyboardButton(text="🔀 Все персонажи", callback_data="aichar:all")])
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
    user_premium = await is_premium(uid)
    mode = u.get("mode", "simple")
    age_min = u.get("search_age_min", 16) or 16
    age_max = u.get("search_age_max", 99) or 99
    age_label = "🎂 Возраст: Любой" if (age_min == 16 and age_max == 99) else f"🎂 Возраст: {age_min}–{age_max}"
    sg_map = {"any": "🔀 Все", "male": "👨 Парни", "female": "👩 Девушки", "other": "⚧ Другое"}
    sg = sg_map.get(u.get("search_gender", "any"), "🔀 Все")
    show_p = u.get("show_premium", True)
    buttons = [
        [InlineKeyboardButton(text=f"{'✅' if u.get('accept_simple', True) else '❌'} Принимать из Общения", callback_data="set:simple")],
        [InlineKeyboardButton(text=f"{'✅' if u.get('accept_flirt', True) else '❌'} Принимать из Флирта", callback_data="set:flirt")],
        [InlineKeyboardButton(text=f"{'✅' if u.get('accept_kink', False) else '❌'} Принимать из Kink", callback_data="set:kink")],
        [InlineKeyboardButton(text=f"{'✅' if u.get('only_own_mode', False) else '❌'} Только свой режим", callback_data="set:only_own")],
    ]
    if mode == "simple" or user_premium:
        buttons.append([InlineKeyboardButton(text=f"👤 Искать: {sg}", callback_data="set:gender")])
    else:
        buttons.append([InlineKeyboardButton(text=f"👤 Искать: {sg} 🔒 Premium", callback_data="set:gender_locked")])
    buttons.append([InlineKeyboardButton(text=age_label, callback_data="noop")])
    buttons.append([
        InlineKeyboardButton(text="✅ 16-20" if (age_min==16 and age_max==20) else "16-20", callback_data="set:age:16:20"),
        InlineKeyboardButton(text="✅ 21-30" if (age_min==21 and age_max==30) else "21-30", callback_data="set:age:21:30"),
        InlineKeyboardButton(text="✅ 31-45" if (age_min==31 and age_max==45) else "31-45", callback_data="set:age:31:45"),
        InlineKeyboardButton(text="✅ Любой" if (age_min==16 and age_max==99) else "Любой", callback_data="set:age:16:99"),
    ])
    buttons.append([InlineKeyboardButton(
        text=f"{'✅' if show_p else '❌'} Значок ⭐ в профиле",
        callback_data="set:show_premium"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
        [InlineKeyboardButton(text="⚠️ Предупреждение жалобщику", callback_data=f"cadm:warnrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="🚫 Бан жалобщику", callback_data=f"cadm:banrep:{complaint_id}:{reporter_uid}")],
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
         InlineKeyboardButton(text="❌ Кик", callback_data=f"uadm:kick:{target_uid}")],
        [InlineKeyboardButton(text="⭐ Дать Premium 30д", callback_data=f"uadm:premium:{target_uid}"),
         InlineKeyboardButton(text="⭐ Забрать Premium", callback_data=f"uadm:unpremium:{target_uid}")],
    ])

def kb_premium():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 7 дней — 99 Stars", callback_data="buy:7d")],
        [InlineKeyboardButton(text="⭐ 1 месяц — 299 Stars 🔥", callback_data="buy:1m")],
        [InlineKeyboardButton(text="⭐ 3 месяца — 599 Stars (скидка 33%)", callback_data="buy:3m")],
        [InlineKeyboardButton(text="❓ Что даёт Premium?", callback_data="buy:info")],
    ])

# ====================== УТИЛИТЫ ======================
def get_all_queues():
    return [waiting_anon, waiting_simple, waiting_flirt, waiting_kink,
            waiting_simple_premium, waiting_flirt_premium, waiting_kink_premium]

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
    async with pairing_lock:
        for q in get_all_queues():
            q.discard(uid)
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
        BotCommand(command="stats", description="Моя статистика"),
        BotCommand(command="reset", description="Сбросить профиль"),
        BotCommand(command="ai", description="ИИ Собеседник"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="admin", description="Админ панель"),
    ])

async def get_premium_badge(uid):
    u = await get_user(uid)
    if not u or not u.get("show_premium", True): return ""
    if await is_premium(uid): return " ⭐"
    return ""

async def send_ad_message(uid):
    try:
        await bot.send_message(
            uid,
            "📢 Здесь могла быть ваша реклама\n\n"
            "⭐ Купи Premium и убери рекламу навсегда!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Убрать рекламу", callback_data="buy:1m")]
            ])
        )
    except Exception: pass

async def do_find(uid, state):
    if uid in active_chats:
        return False
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

    # Собираем кандидатов ВНЕ лока (await-запросы к БД)
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
            if pid == uid or pid in active_chats: continue
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

    if candidates:
        candidates.sort(key=lambda x: (x[3], -x[1], x[2]))

    # Внутри лока — только атомарное спаривание (без await к БД)
    partner = None
    async with pairing_lock:
        if uid in active_chats:
            return False
        for cand_pid, _, _, _, cand_q in candidates:
            if cand_pid not in active_chats and cand_pid in cand_q:
                partner = cand_pid
                cand_q.discard(partner)
                break

        if partner:
            active_chats[uid] = partner
            active_chats[partner] = uid
            last_msg_time[uid] = last_msg_time[partner] = datetime.now()
        else:
            q = get_queue(mode, user_premium)
            q.add(uid)

    # Все await-операции — ПОСЛЕ лока
    if partner:
        await state.set_state(Chat.chatting)
        pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
        p_fsm = FSMContext(dp.storage, key=pkey)
        await p_fsm.set_state(Chat.chatting)
        await save_chat_to_db(uid, partner, "profile")
        pu = await get_user(partner)
        await increment_user(uid, total_chats=1)
        await increment_user(partner, total_chats=1)
        g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
        p_badge = await get_premium_badge(partner)
        my_badge = await get_premium_badge(uid)
        await bot.send_message(uid,
            f"👤 Собеседник найден!{p_badge}\n"
            f"Имя: {pu.get('name','Аноним')}\n"
            f"Возраст: {pu.get('age','?')}\n"
            f"Пол: {g_map.get(pu.get('gender',''),'?')}\n"
            f"Режим: {MODE_NAMES.get(pu.get('mode',''),'—')}\n"
            f"Интересы: {(pu.get('interests','') or '').replace(',', ', ') or '—'}\n"
            f"⭐ Рейтинг: {get_rating(pu)}"
        )
        await bot.send_message(partner,
            f"👤 Собеседник найден!{my_badge}\n"
            f"Имя: {u.get('name','Аноним')}\n"
            f"Возраст: {u.get('age','?')}\n"
            f"Пол: {g_map.get(u.get('gender',''),'?')}\n"
            f"Режим: {MODE_NAMES.get(u.get('mode',''),'—')}\n"
            f"Интересы: {(u.get('interests','') or '').replace(',', ', ') or '—'}\n"
            f"⭐ Рейтинг: {get_rating(u)}"
        )
        await bot.send_message(uid, "✅ Начинайте общение!", reply_markup=kb_chat())
        await bot.send_message(partner, "✅ Начинайте общение!", reply_markup=kb_chat())
        return True
    else:
        await state.set_state(Chat.waiting)
        asyncio.create_task(notify_no_partner(uid))
        return False

async def notify_no_partner(uid):
    await asyncio.sleep(60)
    if uid in active_chats:
        return
    all_waiting = set().union(*get_all_queues())
    if uid in all_waiting:
        try:
            await bot.send_message(uid,
                "😔 Пока никого нет по твоим параметрам.\n\nПопробуй:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🤖 ИИ Собеседник", callback_data="goto:ai")],
                    [InlineKeyboardButton(text="⚙️ Настройки", callback_data="goto:settings")],
                    [InlineKeyboardButton(text="⏳ Продолжить ждать", callback_data="goto:wait")],
                ])
            )
        except Exception: pass

async def end_chat(uid, state, go_next=False):
    partner = active_chats.pop(uid, None)
    if partner:
        active_chats.pop(partner, None)
        await remove_chat_from_db(uid, partner)
        clear_chat_log(uid, partner)

        # Сообщение о завершении + кнопка mutual match
        try:
            await bot.send_message(uid, "💔 Чат завершён.", reply_markup=kb_main())
            await bot.send_message(uid,
                "Понравился собеседник?\nПредложи продолжить общение анонимно — если он тоже захочет, вас соединят 😊",
                reply_markup=kb_after_chat(partner)
            )
        except Exception: pass

        try:
            await bot.send_message(partner, "😔 Собеседник покинул чат.", reply_markup=kb_main())
            await bot.send_message(partner,
                "Понравился собеседник?\nПредложи продолжить общение анонимно — если он тоже захочет, вас соединят 😊",
                reply_markup=kb_after_chat(uid)
            )
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).clear()
        except Exception: pass

        # Реклама для не-Premium (через задержку)
        asyncio.create_task(_send_ad_delayed(uid, partner))
    else:
        await bot.send_message(uid, "💔 Чат завершён.", reply_markup=kb_main())

    async with pairing_lock:
        for q in get_all_queues():
            q.discard(uid)
    await state.clear()

    if go_next and partner:
        await asyncio.sleep(0.5)
        u = await get_user(uid)
        if u and u.get("mode"):
            mode = u["mode"]
            q_len = len(get_queue(mode, False)) + len(get_queue(mode, True))
            await bot.send_message(uid,
                f"👥 В режиме {MODE_NAMES[mode]}: {q_len} чел.\n\n🔍 Ищем...",
                reply_markup=kb_cancel_search()
            )
            await do_find(uid, state)

async def _send_ad_delayed(uid, partner):
    await asyncio.sleep(3)
    # Не отправляем рекламу если уже в новом чате
    if uid not in active_chats and not await is_premium(uid):
        await send_ad_message(uid)
    if partner not in active_chats and not await is_premium(partner):
        await send_ad_message(partner)
# ====================== MUTUAL MATCH ======================
@dp.callback_query(F.data.startswith("mutual:"), StateFilter("*"))
async def mutual_like(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    partner_uid = int(callback.data.split(":", 1)[1])
        # Проверяем что партнёр не в активном чате с кем-то другим
    if partner_uid in active_chats and active_chats.get(partner_uid) != uid:
        await callback.answer("😔 Собеседник уже общается с кем-то другим.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception: pass
        return
    # Убираем кнопки чтобы не нажали дважды
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass

    # Инициализируем если нужно
    if uid not in mutual_likes:
        mutual_likes[uid] = set()

    # Проверяем взаимность ДО добавления своего лайка
    already_mutual = partner_uid in mutual_likes and uid in mutual_likes.get(partner_uid, set())

    # Добавляем свой лайк
    mutual_likes[uid].add(partner_uid)

    if already_mutual:
        # Взаимный матч!
        mutual_likes[uid].discard(partner_uid)
        if partner_uid in mutual_likes:
            mutual_likes[partner_uid].discard(uid)

        # Соединяем в чат
        active_chats[uid] = partner_uid
        active_chats[partner_uid] = uid
        last_msg_time[uid] = last_msg_time[partner_uid] = datetime.now()
        await state.set_state(Chat.chatting)
        pkey = StorageKey(bot_id=bot.id, chat_id=partner_uid, user_id=partner_uid)
        await FSMContext(dp.storage, key=pkey).set_state(Chat.chatting)
        await save_chat_to_db(uid, partner_uid, "mutual")

        await bot.send_message(uid,
            "🎉 Взаимный интерес! Приватный анонимный чат открыт.\n"
            "Вы по-прежнему анонимны друг для друга.",
            reply_markup=kb_chat()
        )
        await bot.send_message(partner_uid,
            "🎉 Взаимный интерес! Приватный анонимный чат открыт.\n"
            "Вы по-прежнему анонимны друг для друга.",
            reply_markup=kb_chat()
        )
    else:
        await callback.message.answer(
            "❤️ Запрос отправлен!\n"
            "Если собеседник тоже захочет — вас соединят в течение 10 минут."
        )
        # Уведомляем партнёра что кто-то хочет продолжить
        try:
            await bot.send_message(partner_uid,
                "💌 Твой собеседник хочет продолжить общение!\n"
                "Ответь на предложение если тоже хочешь:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❤️ Да, хочу продолжить!", callback_data=f"mutual:{uid}")],
                    [InlineKeyboardButton(text="❌ Нет спасибо", callback_data="mutual:decline")],
                ])
            )
        except Exception: pass
        asyncio.create_task(_mutual_timeout(uid, partner_uid))

    await callback.answer()

@dp.callback_query(F.data == "mutual:decline", StateFilter("*"))
async def mutual_decline(callback: types.CallbackQuery):
    uid = callback.from_user.id
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    # Очищаем все взаимные лайки с этим пользователем
    for key in list(mutual_likes.keys()):
        mutual_likes[key].discard(uid)
    await callback.answer("Окей, не проблема!")

async def _mutual_timeout(uid, partner_uid):
    await asyncio.sleep(600)  # 10 минут
    if uid in mutual_likes and partner_uid in mutual_likes[uid]:
        mutual_likes[uid].discard(partner_uid)
        try:
            await bot.send_message(uid, "😔 Собеседник не ответил на запрос продолжения.")
        except Exception: pass

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

    # Шаг 1: Политика конфиденциальности
    if not u or not u.get("accepted_privacy"):
        await message.answer(PRIVACY_TEXT, reply_markup=kb_privacy())
        return

    # Шаг 2: Язык и правила
    if not u.get("accepted_rules"):
        await state.set_state(Rules.waiting)
        await message.answer(WELCOME_TEXT, reply_markup=kb_lang())
        return

    # Всё принято — в меню
    badge = await get_premium_badge(uid)
    await message.answer(f"👋 С возвращением в MatchMe!{badge}", reply_markup=kb_main())

# ====================== ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ ======================
@dp.callback_query(F.data == "privacy:accept", StateFilter("*"))
async def privacy_accept(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    await update_user(uid, accepted_privacy=True)
    try:
        await callback.message.edit_text("✅ Политика конфиденциальности принята!")
    except Exception: pass

    # Предлагаем подписку на канал
    await callback.message.answer(
        f"🎁 Подпишись на наш канал и получи 3 дня Premium бесплатно!\n\n"
        f"В канале: обновления, новости бота и полезный контент 😄",
        reply_markup=kb_channel_bonus()
    )
    await callback.answer()

@dp.callback_query(F.data == "privacy:decline", StateFilter("*"))
async def privacy_decline(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            "❌ Без принятия политики конфиденциальности использование бота невозможно.\n\n"
            "Нажми /start чтобы попробовать снова."
        )
    except Exception: pass
    await callback.answer()

# ====================== БОНУС ЗА КАНАЛ ======================
@dp.callback_query(F.data == "channel:check", StateFilter("*"))
async def channel_check(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    u = await get_user(uid)

    if u and u.get("channel_bonus_used"):
        await callback.answer("Бонус уже был получен ранее!", show_alert=True)
        await _proceed_to_rules(callback.message, state, uid)
        return

    is_subscribed = await check_channel_subscription(uid)
    if not is_subscribed:
        await callback.answer("Ты ещё не подписан на канал!", show_alert=True)
        return

    until = datetime.now() + timedelta(days=3)
    await update_user(uid, premium_until=until.isoformat(), channel_bonus_used=True)
    try:
        await callback.message.edit_text(
            f"🎉 Спасибо за подписку!\n\n"
            f"⭐ Premium активирован на 3 дня!\n"
            f"До {until.strftime('%d.%m.%Y')}"
        )
    except Exception: pass
    await _proceed_to_rules(callback.message, state, uid)
    await callback.answer()

@dp.callback_query(F.data == "channel:skip", StateFilter("*"))
async def channel_skip(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    try:
        await callback.message.edit_text("Окей! Можешь подписаться позже через /premium 😊")
    except Exception: pass
    await _proceed_to_rules(callback.message, state, uid)
    await callback.answer()

async def _proceed_to_rules(message, state, uid):
    """Продолжение после privacy/channel — к правилам или в меню"""
    u = await get_user(uid)
    if not u or not u.get("accepted_rules"):
        await state.set_state(Rules.waiting)
        await message.answer(WELCOME_TEXT, reply_markup=kb_lang())
    else:
        badge = await get_premium_badge(uid)
        await message.answer(f"👋 Добро пожаловать в MatchMe!{badge}", reply_markup=kb_main())

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
    await message.answer("✅ Правила приняты! Добро пожаловать в MatchMe! 🎉", reply_markup=kb_main())

@dp.message(StateFilter(Rules.waiting))
async def rules_other(message: types.Message):
    await message.answer("👆 Выбери язык чтобы продолжить.")

# ====================== СТАТИСТИКА ======================
@dp.message(Command("stats"), StateFilter("*"))
async def cmd_stats(message: types.Message):
    uid = message.from_user.id
    u = await get_user(uid)
    if not u:
        await message.answer("Сначала зарегистрируйся через /start!")
        return
    user_premium = await is_premium(uid)
    if user_premium:
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            premium_text = "⭐ Premium: Вечный"
        else:
            try:
                until = datetime.fromisoformat(u["premium_until"])
                premium_text = f"⭐ Premium до {until.strftime('%d.%m.%Y')}"
            except Exception:
                premium_text = "⭐ Premium активен"
    else:
        premium_text = "💎 Premium: Нет"
    days_in_bot = (datetime.now() - u.get("created_at", datetime.now())).days
    await message.answer(
        f"📊 Твоя статистика:\n\n"
        f"💬 Всего чатов: {u.get('total_chats', 0)}\n"
        f"👍 Получено лайков: {u.get('likes', 0)}\n"
        f"⭐ Рейтинг: {get_rating(u)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count', 0)}\n"
        f"📅 Дней в боте: {days_in_bot}\n"
        f"{premium_text}"
    )

# ====================== PREMIUM ======================
@dp.message(Command("premium"), StateFilter("*"))
async def cmd_premium(message: types.Message):
    uid = message.from_user.id
    user_premium = await is_premium(uid)
    if user_premium:
        u = await get_user(uid)
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            await message.answer("⭐ У тебя вечный Premium!\n\nВсе функции доступны навсегда 🔥")
        else:
            try:
                until = datetime.fromisoformat(u["premium_until"])
                await message.answer(f"⭐ Premium активен до {until.strftime('%d.%m.%Y %H:%M')}")
            except Exception:
                await message.answer("⭐ Premium активен!")
        return
    await message.answer(
        f"⭐ MatchMe Premium\n\n"
        f"Что входит:\n"
        f"• 💋 Виолетта — флиртующая девушка\n"
        f"• 😈 Дмитри — опытный Доминант\n"
        f"• 🐾 Алиса — покорная сабмиссив\n"
        f"• 🎭 Ролевой мастер\n"
        f"• 🤖 Безлимитный ИИ чат\n"
        f"• 🚀 Приоритет в поиске\n"
        f"• 👤 Фильтр пола в Флирте и Kink\n"
        f"• ⭐ Значок в профиле\n"
        f"• 📢 Без рекламы\n\n"
        f"Или подпишись на {CHANNEL_ID} → 3 дня бесплатно!\n\n"
        f"Выбери тариф:",
        reply_markup=kb_premium()
    )

@dp.callback_query(F.data == "buy:info", StateFilter("*"))
async def premium_info(callback: types.CallbackQuery):
    await callback.answer(
        "⭐ Premium: Виолетта, Дмитри, Алиса, Ролевой мастер + безлимит ИИ + приоритет + без рекламы!",
        show_alert=True
    )

@dp.callback_query(F.data.startswith("buy:"), StateFilter("*"))
async def buy_premium(callback: types.CallbackQuery):
    uid = callback.from_user.id
    plan_key = callback.data.split(":", 1)[1]
    if plan_key == "info": return
    if plan_key not in PREMIUM_PLANS:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    plan = PREMIUM_PLANS[plan_key]
    await callback.answer()
    await bot.send_invoice(
        chat_id=uid,
        title=f"MatchMe Premium — {plan['label']}",
        description=f"Все Premium функции на {plan['label']}. {plan['desc']}",
        payload=f"premium_{plan_key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Premium {plan['label']}", amount=plan["stars"])],
    )

@dp.pre_checkout_query(StateFilter("*"))
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment, StateFilter("*"))
async def successful_payment(message: types.Message):
    uid = message.from_user.id
    payload = message.successful_payment.invoice_payload
    plan_key = payload.replace("premium_", "")
    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
    until = datetime.now() + timedelta(days=plan["days"])
    await update_user(uid, premium_until=until.isoformat())
    await message.answer(
        f"🎉 Premium активирован!\n\n"
        f"⭐ Тариф: {plan['label']}\n"
        f"📅 До {until.strftime('%d.%m.%Y')}\n\n"
        f"Доступны: Виолетта, Дмитри, Алиса, Ролевой мастер, безлимит ИИ, приоритет, без рекламы!",
        reply_markup=kb_main()
    )

# ====================== СБРОС ПРОФИЛЯ ======================
@dp.message(Command("reset"), StateFilter("*"))
async def cmd_reset(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current == Chat.chatting.state:
        await unavailable(message, "сначала выйди из чата")
        return
    await state.set_state(ResetProfile.confirm)
    await message.answer(
        "⚠️ Полный сброс профиля!\n\n"
        "Удалятся: имя, возраст, пол, режим, интересы, рейтинг\n"
        "❗ Бан, предупреждения и Premium сохранятся.\n\nТы уверен?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="reset:confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="reset:cancel")],
        ])
    )

@dp.callback_query(F.data == "reset:confirm", StateFilter(ResetProfile.confirm))
async def reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    await cleanup(uid, state)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET name=NULL, age=NULL, gender=NULL, mode=NULL,
                interests='', likes=0, dislikes=0, accept_simple=TRUE,
                accept_flirt=TRUE, accept_kink=FALSE, only_own_mode=FALSE,
                search_gender='any', search_age_min=16, search_age_max=99
            WHERE uid=$1
        """, uid)
    try:
        await callback.message.edit_text("✅ Профиль сброшен!")
    except Exception: pass
    await callback.message.answer("👋 Нажми '🔍 Поиск по анкете' чтобы заполнить анкету заново.", reply_markup=kb_main())
    await callback.answer()

@dp.callback_query(F.data == "reset:cancel", StateFilter(ResetProfile.confirm))
async def reset_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("❌ Сброс отменён.")
    except Exception: pass
    await callback.message.answer("Возврат в меню.", reply_markup=kb_main())
    await callback.answer()

# ====================== ИИ СОБЕСЕДНИК ======================
async def _show_ai_menu(message: types.Message, state: FSMContext, uid: int):
    user_premium = await is_premium(uid)
    u = await get_user(uid)
    mode = u.get("mode", "simple") if u else "simple"
    await state.set_state(AIChat.choosing)
    await state.update_data(ai_show_mode=mode)
    await message.answer(
        "🤖 ИИ Собеседник\n\n"
        "🆓 Бесплатно: 👨 Данил, 👩 Полина, 😏 Макс\n"
        "⭐ Premium: 💋 Виолетта, 🐾 Алиса, 😈 Дмитри, 🎭 Ролевой мастер\n\n"
        "Выбери с кем хочешь поговорить:",
        reply_markup=kb_ai_characters(user_premium, mode)
    )

@dp.message(F.text == "🤖 ИИ Собеседник", StateFilter("*"))
@dp.message(Command("ai"), StateFilter("*"))
async def ai_menu(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current == Chat.chatting.state:
        await unavailable(message, "ты в чате с живым собеседником")
        return
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
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
    if char_id == "all":
        user_premium = await is_premium(uid)
        await state.update_data(ai_show_mode="any")
        try:
            await callback.message.edit_reply_markup(reply_markup=kb_ai_characters(user_premium, "any"))
        except Exception: pass
        await callback.answer()
        return
    if char_id == "locked":
        await callback.answer("🔒 Только для Premium! Купи подписку через /premium", show_alert=True)
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
    try:
        await callback.message.edit_text(
            f"{'✅' if not char['premium'] else '🔥'} Ты общаешься с {char['name']}\n"
            f"{char['description']}\n\n{limit_text}\n\nНапиши что-нибудь!"
        )
    except Exception: pass
    await callback.message.answer("💬 Чат с ИИ активен", reply_markup=kb_ai_chat())
    greeting = await ask_venice(char_id, [], "Поприветствуй собеседника и начни разговор. Коротко, 1-2 предложения на русском.")
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
        u = await get_user(uid)
        mode = u.get("mode", "simple") if u else "simple"
        await state.set_state(AIChat.choosing)
        await message.answer("Выбери персонажа:", reply_markup=kb_ai_characters(user_premium, mode))
        return
    if "Найти живого" in txt:
        ai_sessions.pop(uid, None)
        await state.clear()
        await message.answer("🔍 Ищем...", reply_markup=kb_cancel_search())
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
    user_premium = await is_premium(uid)
    if not user_premium and session["msg_count"] >= AI_FREE_LIMIT:
        await message.answer(
            f"⏰ Использовано {AI_FREE_LIMIT} бесплатных сообщений.\n\n⭐ Купи Premium для безлимита!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Купить Premium", callback_data="buy:1m")],
                [InlineKeyboardButton(text="🔍 Найти живого собеседника", callback_data="goto:find")]
            ])
        )
        return
    await bot.send_chat_action(uid, "typing")
    await update_user(uid, last_seen=datetime.now())
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

# ====================== GOTO CALLBACKS ======================
@dp.callback_query(F.data.startswith("goto:"), StateFilter("*"))
async def goto_action(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    action = callback.data.split(":", 1)[1]
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    if action == "ai":
        async with pairing_lock:
            for q in get_all_queues():
                q.discard(uid)
        await state.clear()
        await _show_ai_menu(callback.message, state, uid)
    elif action == "settings":
        await show_settings(callback.message, state)
    elif action == "wait":
        await callback.answer("⏳ Продолжаем ждать...")
        return
    elif action == "find":
        ai_sessions.pop(uid, None)
        async with pairing_lock:
            for q in get_all_queues():
                q.discard(uid)
        await state.clear()
        await callback.message.answer("🔍 Ищем...", reply_markup=kb_cancel_search())
        await cmd_find(callback.message, state)
    elif action == "menu":
        await state.clear()
        await callback.message.answer("🏠 Главное меню", reply_markup=kb_main())
    await callback.answer()

# ====================== АНОНИМНЫЙ ПОИСК ======================
@dp.message(F.text == "⚡ Анонимный поиск", StateFilter("*"))
async def anon_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, "сначала заверши заполнение анкеты")
        return
    if current == Chat.chatting.state or uid in active_chats:
        await unavailable(message, "ты уже в чате")
        return
    if current == AIChat.chatting.state:
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
        if uid in active_chats:
            return
        partner = None
        for pid in list(waiting_anon):
            if pid != uid and pid not in active_chats:
                partner = pid
                waiting_anon.discard(pid)
                break
        if partner:
            active_chats[uid] = partner
            active_chats[partner] = uid
            last_msg_time[uid] = last_msg_time[partner] = datetime.now()
            await state.set_state(Chat.chatting)
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).set_state(Chat.chatting)
            await save_chat_to_db(uid, partner, "anon")
            await increment_user(uid, total_chats=1)
            await increment_user(partner, total_chats=1)
            await bot.send_message(uid, "👤 Соединено! Удачи! 🎉", reply_markup=kb_chat())
            await bot.send_message(partner, "👤 Соединено! Удачи! 🎉", reply_markup=kb_chat())
        else:
            waiting_anon.add(uid)
            await state.set_state(Chat.waiting)
            asyncio.create_task(notify_no_partner(uid))

# ====================== ПОИСК ПО АНКЕТЕ ======================
@dp.message(F.text.in_(["🔍 Поиск по анкете", "🔍 Найти собеседника"]), StateFilter("*"))
@dp.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, "сначала заверши заполнение анкеты")
        return
    if current == Chat.chatting.state or uid in active_chats:
        await unavailable(message, "ты уже в чате — нажми ❌ Стоп")
        return
    if current == AIChat.chatting.state:
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
        f"{'🚀 Приоритетный поиск' + premium_badge if user_premium else '🔍 Ищем...'}\n",
        reply_markup=kb_cancel_search()
    )
    await do_find(uid, state)

# ====================== РЕГИСТРАЦИЯ ======================
@dp.message(F.text == "✅ Понятно, начать анкету", StateFilter(Reg.name))
async def start_reg(message: types.Message):
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
        try:
            await callback.message.edit_text("✅ Анкета заполнена!")
        except Exception: pass
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
        await callback.answer("Максимум 3!", show_alert=True)
        return
    await state.update_data(temp_interests=sel)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb_interests(mode, sel))
    except Exception: pass

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
            # Защита от спама лайков — 1 лайк за чат
            chat_key = get_chat_key(uid, partner)
            if not hasattr(do_find, '_liked_chats'):
                do_find._liked_chats = set()
            like_key = (uid, chat_key)
            if like_key in do_find._liked_chats:
                await message.answer("👍 Ты уже ставил лайк этому собеседнику!")
                return
            do_find._liked_chats.add(like_key)
            await increment_user(partner, likes=1)
            await message.answer("👍 Лайк отправлен!")
            try: await bot.send_message(partner, "👍 Собеседник поставил тебе лайк! ⭐")
            except Exception: pass
        return
    if "🎲 Дай тему" in txt:
        if uid in active_chats:
            partner = active_chats[uid]
            topic = random.choice(CHAT_TOPICS)
            await message.answer(f"🎲 Тема для разговора:\n\n{topic}")
            try: await bot.send_message(partner, f"🎲 Собеседник предлагает тему:\n\n{topic}")
            except Exception: pass
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
    # Обновляем last_seen
    await update_user(uid, last_seen=now)
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
    except Exception as e:
        logger.warning(f"Relay failed {uid}->{partner}: {e}")

# ====================== ЖАЛОБА ======================
@dp.callback_query(F.data == "rep:cancel", StateFilter(Complaint.reason))
async def complaint_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Chat.chatting)
    try:
        await callback.message.edit_text("↩️ Жалоба отменена.")
    except Exception: pass
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
        try:
            await callback.message.edit_text("Ты не в чате.")
        except Exception: pass
        await state.clear()
        return
    log_text = get_chat_log_text(uid, partner)
    stop_found, _ = check_stop_words(uid, partner)
    async with db_pool.acquire() as conn:
        complaint_id = await conn.fetchval(
            "INSERT INTO complaints_log (from_uid, to_uid, reason, chat_log, stop_words_found) VALUES ($1,$2,$3,$4,$5) RETURNING id",
            uid, partner, reason, log_text, stop_found
        )
        await increment_user(partner, complaints=1)
    active_chats.pop(uid, None)
    active_chats.pop(partner, None)
    await remove_chat_from_db(uid, partner)
    clear_chat_log(uid, partner)
    await state.clear()
    try:
        await callback.message.edit_text(f"🚩 Жалоба #{complaint_id} отправлена. Администратор рассмотрит её.")
    except Exception: pass
    await bot.send_message(uid, "Чат завершён.", reply_markup=kb_main())
    try:
        await bot.send_message(partner, "⚠️ На тебя подана жалоба.", reply_markup=kb_main())
        pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
        await FSMContext(dp.storage, key=pkey).clear()
    except Exception: pass
    pu = await get_user(partner)
    ru = await get_user(uid)
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🚩 Жалоба #{complaint_id}!\n\n"
            f"👤 От: {uid} ({ru.get('name','?') if ru else '?'})\n"
            f"👤 На: {partner} ({pu.get('name','?') if pu else '?'}) | Жалоб: {pu.get('complaints',0) if pu else '?'}\n"
            f"📋 Причина: {reason}\n"
            f"{'⚠️ Стоп-слова найдены!' if stop_found else '✅ Стоп-слова не найдены'}\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            reply_markup=kb_complaint_action(complaint_id, partner, uid, bool(log_text), stop_found)
        )
    except Exception: pass
    await callback.answer()

# ====================== ОТМЕНА ПОИСКА ======================
@dp.message(F.text == "❌ Отменить поиск", StateFilter("*"))
async def cancel_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    removed = any(uid in q for q in get_all_queues())
    async with pairing_lock:
        for q in get_all_queues():
            q.discard(uid)
    await state.clear()
    await message.answer("❌ Поиск отменён." if removed else "Ты не в поиске.", reply_markup=kb_main())

# ====================== СТОП / СЛЕДУЮЩИЙ ======================
@dp.message(Command("stop"), StateFilter("*"))
async def cmd_stop(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
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
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, "сначала заверши заполнение анкеты")
        return
    if current == Chat.chatting.state:
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
    if user_premium:
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            premium_status = "⭐ Premium (вечный)"
        else:
            try:
                until = datetime.fromisoformat(u["premium_until"])
                premium_status = f"⭐ Premium до {until.strftime('%d.%m.%Y')}"
            except Exception:
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
        f"💬 Чатов: {u.get('total_chats',0)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count',0)}\n"
        f"💎 Статус: {premium_status}",
        reply_markup=kb_edit()
    )

# ====================== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ======================
@dp.callback_query(F.data.startswith("edit:"), StateFilter("*"))
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
        mode = u.get("mode", "simple") if u else "simple"
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
    elif "Другое" in txt: g = "other"
    else:
        await message.answer("Выбери пол из кнопок 👇", reply_markup=kb_gender())
        return
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
    elif "kink" in txt or "ролевые" in txt: mode = "kink"
    else:
        await message.answer("Выбери режим из кнопок 👇", reply_markup=kb_mode())
        return
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
        try:
            await callback.message.edit_text("✅ Интересы обновлены!")
        except Exception: pass
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
    try:
        await callback.message.edit_reply_markup(reply_markup=kb_interests(mode, sel))
    except Exception: pass

# ====================== НАСТРОЙКИ ======================
@dp.message(F.text == "⚙️ Настройки", StateFilter("*"))
@dp.message(Command("settings"), StateFilter("*"))
async def show_settings(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, "сначала заверши анкету")
        return
    if current == Chat.chatting.state:
        await unavailable(message, "ты в чате")
        return
    await ensure_user(uid)
    await message.answer("⚙️ Настройки поиска:", reply_markup=await kb_settings(uid))

@dp.callback_query(F.data.startswith("set:"), StateFilter("*"))
async def toggle_setting(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    parts = callback.data.split(":")
    key = parts[1]
    u = await get_user(uid)
    if key == "gender":
        user_premium = await is_premium(uid)
        mode = u.get("mode", "simple") if u else "simple"
        if mode != "simple" and not user_premium:
            await callback.answer("🔒 Фильтр пола в Флирте и Kink — только Premium!", show_alert=True)
            return
        await state.set_state(EditProfile.search_gender)
        await callback.message.answer("👤 Кого хочешь искать?", reply_markup=kb_search_gender())
        await callback.answer()
        return
    elif key == "gender_locked":
        await callback.answer("🔒 Только для Premium! Купи через /premium", show_alert=True)
        return
    elif key == "age" and len(parts) == 4:
        min_age = int(parts[2])
        max_age = int(parts[3])
        await update_user(uid, search_age_min=min_age, search_age_max=max_age)
        try:
            await callback.message.edit_reply_markup(reply_markup=await kb_settings(uid))
        except Exception: pass
        await callback.answer(f"✅ Возраст: {min_age}–{max_age}" if not (min_age==16 and max_age==99) else "✅ Возраст: Любой")
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
    try:
        await callback.message.edit_reply_markup(reply_markup=await kb_settings(uid))
    except Exception: pass
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

# ====================== ПОМОЩЬ ======================
@dp.message(F.text == "❓ Помощь", StateFilter("*"))
@dp.message(Command("help"), StateFilter("*"))
async def show_help(message: types.Message):
    await message.answer(
        "🆘 Помощь MatchMe:\n\n"
        "⚡ Анонимный поиск — быстрый поиск\n"
        "🔍 Поиск по анкете — по режиму и интересам\n"
        "🤖 ИИ Собеседник — поговори с ИИ\n"
        "📊 /stats — твоя статистика\n"
        "⭐ /premium — Premium подписка\n\n"
        "В чате:\n"
        "⏭ Следующий — другой собеседник\n"
        "❌ Стоп — завершить чат\n"
        "🎲 Дай тему — случайная тема для разговора\n"
        "👍 Лайк — поднять рейтинг\n"
        "🚩 Жалоба — при нарушениях\n\n"
        f"📢 Наш канал: {CHANNEL_ID}\n"
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

@dp.callback_query(F.data == "noop", StateFilter("*"))
async def noop(callback: types.CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("admin:"), StateFilter("*"))
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
        in_search = sum(len(q) for q in get_all_queues())
        await callback.message.answer(
            f"📊 Статистика MatchMe:\n\n"
            f"👥 Всего: {total}\n"
            f"🟢 За 24ч: {today}\n"
            f"⭐ Premium: {premiums}\n"
            f"💬 В чатах: {online_now} пар\n"
            f"🤖 С ИИ: {len(ai_sessions)}\n"
            f"🔍 В поиске: {in_search}\n"
            f"🚫 Забанено: {banned}\n"
            f"🚩 Жалоб: {total_complaints} (⏳{pending})"
        )
    elif action == "complaints":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM complaints_log WHERE reviewed=FALSE ORDER BY created_at ASC LIMIT 5")
        if not rows:
            await callback.message.answer("✅ Нет жалоб.")
        else:
            for r in rows:
                ru = await get_user(r["from_uid"])
                pu = await get_user(r["to_uid"])
                has_log = bool(r.get("chat_log"))
                stop_words_found = bool(r.get("stop_words_found"))
                await callback.message.answer(
                    f"🚩 Жалоба #{r['id']}\n\n"
                    f"👤 От: {r['from_uid']} ({ru.get('name','?') if ru else '?'})\n"
                    f"👤 На: {r['to_uid']} ({pu.get('name','?') if pu else '?'})\n"
                    f"📋 {r['reason']} | 🕐 {r['created_at'].strftime('%d.%m %H:%M')}",
                    reply_markup=kb_complaint_action(r["id"], r["to_uid"], r["from_uid"], has_log, stop_words_found)
                )
    elif action == "online":
        await callback.message.answer(
            f"👥 Онлайн:\n\n"
            f"💬 В чатах: {len(active_chats)//2} пар\n"
            f"🤖 С ИИ: {len(ai_sessions)}\n"
            f"⚡ Анон: {len(waiting_anon)}\n"
            f"💬 Общение: {len(waiting_simple)}+{len(waiting_simple_premium)}⭐\n"
            f"💋 Флирт: {len(waiting_flirt)}+{len(waiting_flirt_premium)}⭐\n"
            f"🔥 Kink: {len(waiting_kink)}+{len(waiting_kink_premium)}⭐"
        )
    elif action == "find":
        await state.set_state(AdminState.waiting_user_id)
        await callback.message.answer("🔍 Введи Telegram ID:")
    elif action == "notify_update":
        await callback.message.answer(
            "Через сколько минут?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="1 мин", callback_data="upd:1"),
                 InlineKeyboardButton(text="2 мин", callback_data="upd:2")],
                [InlineKeyboardButton(text="5 мин", callback_data="upd:5"),
                 InlineKeyboardButton(text="🔴 Сейчас", callback_data="upd:0")],
            ])
        )
    await callback.answer()

@dp.callback_query(F.data.startswith("clog:"), StateFilter("*"))
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
            await callback.message.answer("📄 Пусто.")
        else:
            await callback.message.answer(
                f"📄 Жалоба #{complaint_id}:\n\n{row['chat_log']}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"clog:delete:{complaint_id}")]
                ])
            )
    elif action == "delete":
        try: await callback.message.delete()
        except Exception: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("upd:"), StateFilter("*"))
async def handle_update_notify(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    minutes = int(callback.data.split(":")[1])
    text = "🔧 Бот обновляется прямо сейчас!" if minutes == 0 else f"🔧 Через {minutes} мин. обновление!"
    sent = 0
    for uid, partner in list(active_chats.items()):
        if uid < partner:
            try:
                await bot.send_message(uid, text, reply_markup=kb_main())
                await bot.send_message(partner, text, reply_markup=kb_main())
                sent += 2
            except Exception: pass
    async with db_pool.acquire() as conn:
        all_users = await conn.fetch("SELECT uid FROM users WHERE last_seen > NOW() - INTERVAL '7 days'")
    active_uids = set(active_chats.keys())
    for row in all_users:
        if row["uid"] in active_uids: continue
        try:
            await bot.send_message(row["uid"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception: pass
    await callback.message.answer(f"✅ Отправлено {sent} пользователям.")
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
    in_queue = "✅" if any(target_uid in q for q in get_all_queues()) else "❌"
    await message.answer(
        f"👤 {target_uid}:\n"
        f"Имя: {u.get('name','—')} | Возраст: {u.get('age','—')}\n"
        f"Пол: {g_map.get(u.get('gender',''), '—')} | Режим: {MODE_NAMES.get(u.get('mode',''), '—')}\n"
        f"⭐ Рейтинг: {get_rating(u)} | 👍 Лайков: {u.get('likes',0)}\n"
        f"💬 Чатов: {u.get('total_chats',0)} | 🚩 Жалоб: {u.get('complaints',0)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count',0)}\n"
        f"🚫 Бан: {ban_status} | 💎 Premium: {prem_status}\n"
        f"💬 В чате: {in_chat} | 🤖 С ИИ: {with_ai} | 🔍 В поиске: {in_queue}",
        reply_markup=kb_user_actions(target_uid)
    )

@dp.callback_query(F.data.startswith("cadm:"), StateFilter("*"))
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
            await conn.execute("UPDATE complaints_log SET reviewed=TRUE, admin_action=$1 WHERE id=$2", action_text, complaint_id)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass

    if action == "ban3" and target_uid:
        until = datetime.now() + timedelta(hours=3)
        await update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан 3ч")
        await callback.message.answer(f"✅ Бан 3ч → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Бан на 3 часа по жалобе.")
        except Exception: pass
    elif action == "ban24" and target_uid:
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан 24ч")
        await callback.message.answer(f"✅ Бан 24ч → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Бан на 24 часа по жалобе.")
        except Exception: pass
    elif action == "banperm" and target_uid:
        await update_user(target_uid, ban_until="permanent")
        await mark_reviewed("Перм бан")
        await callback.message.answer(f"✅ Перм бан → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Перманентный бан.")
        except Exception: pass
    elif action == "warn" and target_uid:
        await increment_user(target_uid, warn_count=1)
        await mark_reviewed("Предупреждение")
        await callback.message.answer(f"✅ Предупреждение → {target_uid}")
        try: await bot.send_message(target_uid, "⚠️ Предупреждение. Следующее — бан.")
        except Exception: pass
    elif action == "warnrep" and target_uid:
        await increment_user(target_uid, warn_count=1)
        await mark_reviewed("Предупреждение жалобщику")
        await callback.message.answer(f"✅ Ложная жалоба. Предупреждение → {target_uid}")
        try: await bot.send_message(target_uid, "⚠️ Жалоба признана необоснованной.")
        except Exception: pass
    elif action == "banrep" and target_uid:
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан жалобщику")
        await callback.message.answer(f"✅ Ложная жалоба. Бан 24ч → {target_uid}")
        try: await bot.send_message(target_uid, "🚫 Бан за злоупотребление жалобами.")
        except Exception: pass
    elif action == "dismiss":
        await mark_reviewed("Отклонена")
        await callback.message.answer(f"✅ Жалоба #{complaint_id} отклонена.")
    await callback.answer("✅ Готово")

@dp.callback_query(F.data.startswith("uadm:"), StateFilter("*"))
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
        try: await bot.send_message(target_uid, "🚫 Бан на 3 часа.")
        except Exception: pass
    elif action == "ban24":
        until = datetime.now() + timedelta(hours=24)
        await update_user(target_uid, ban_until=until.isoformat())
        await callback.answer("✅ Бан 24ч")
        try: await bot.send_message(target_uid, "🚫 Бан на 24 часа.")
        except Exception: pass
    elif action == "banperm":
        await update_user(target_uid, ban_until="permanent")
        await callback.answer("✅ Перм бан")
        try: await bot.send_message(target_uid, "🚫 Перманентный бан.")
        except Exception: pass
    elif action == "unban":
        await update_user(target_uid, ban_until=None)
        await callback.answer("✅ Разбан")
        try: await bot.send_message(target_uid, "✅ Ты разблокирован! Добро пожаловать обратно.")
        except Exception: pass
    elif action == "warn":
        await increment_user(target_uid, warn_count=1)
        await callback.answer("✅ Предупреждение")
        try: await bot.send_message(target_uid, "⚠️ Предупреждение от администратора.")
        except Exception: pass
    elif action == "kick":
        if target_uid in active_chats:
            partner = active_chats.pop(target_uid, None)
            if partner: active_chats.pop(partner, None)
            await remove_chat_from_db(target_uid, partner)
            try: await bot.send_message(target_uid, "❌ Кик от администратора.", reply_markup=kb_main())
            except Exception: pass
            if partner:
                try: await bot.send_message(partner, "😔 Собеседник покинул чат.", reply_markup=kb_main())
                except Exception: pass
            await callback.answer("✅ Кикнут")
        else:
            await callback.answer("Не в чате", show_alert=True)
    elif action == "premium":
        until = datetime.now() + timedelta(days=30)
        await update_user(target_uid, premium_until=until.isoformat())
        await callback.answer("✅ Premium 30д")
        try: await bot.send_message(target_uid, "⭐ Тебе выдан Premium на 30 дней!", reply_markup=kb_main())
        except Exception: pass
    elif action == "unpremium":
        await update_user(target_uid, premium_until=None)
        await callback.answer("✅ Premium забран")
        try: await bot.send_message(target_uid, "❌ Premium отменён администратором.")
        except Exception: pass

# ====================== ТАЙМЕР НЕАКТИВНОСТИ ======================
async def inactivity_checker():
    while True:
        await asyncio.sleep(60)
        now = datetime.now()

        # Завершаем неактивные чаты
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
            # Очищаем FSM state обоих пользователей
            for chat_uid in (uid, partner):
                try:
                    key = StorageKey(bot_id=bot.id, chat_id=chat_uid, user_id=chat_uid)
                    await FSMContext(dp.storage, key=key).clear()
                except Exception:
                    pass
            try: await bot.send_message(uid, "⏰ Чат завершён — 7 мин неактивности.", reply_markup=kb_main())
            except Exception: pass
            try: await bot.send_message(partner, "⏰ Чат завершён — 7 мин неактивности.", reply_markup=kb_main())
            except Exception: pass

        # Очистка памяти: удаляем старые записи msg_count и last_msg_time
        for uid_key in list(last_msg_time.keys()):
            if uid_key not in active_chats and (now - last_msg_time[uid_key]).total_seconds() > 600:
                last_msg_time.pop(uid_key, None)
                msg_count.pop(uid_key, None)

        # Очистка мёртвых душ из очередей (по last_seen)
        async with pairing_lock:
            for q in get_all_queues():
                for uid_key in list(q):
                    if uid_key in active_chats:
                        q.discard(uid_key)

        # Очистка просроченных mutual_likes (старше 15 мин уже не актуальны)
        for uid_key in list(mutual_likes.keys()):
            if not mutual_likes[uid_key]:
                del mutual_likes[uid_key]

# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    await set_commands()
    asyncio.create_task(inactivity_checker())
    logger.info("MatchMe запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
