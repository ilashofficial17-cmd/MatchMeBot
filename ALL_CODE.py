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
import moderation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("matchme")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))
VENICE_API_KEY = os.environ.get("VENICE_API_KEY")
VENICE_API_URL = "https://api.venice.ai/api/v1/chat/completions"
CHANNEL_ID = "@MATCHMEHUB"

PREMIUM_PLANS = {
    # Premium — базовая
    "7d":      {"stars": 99,  "days": 7,  "label": "7 дней",       "desc": "Попробовать",    "tier": "premium"},
    "1m":      {"stars": 299, "days": 30, "label": "1 месяц",      "desc": "Популярный",     "tier": "premium"},
    "3m":      {"stars": 599, "days": 90, "label": "3 месяца",     "desc": "Скидка 33%",     "tier": "premium"},
    # Premium Plus — всё безлимит
    "plus_1m": {"stars": 499, "days": 30, "label": "1 мес Plus",   "desc": "Безлимит AI",    "tier": "plus"},
    "plus_3m": {"stars": 999, "days": 90, "label": "3 мес Plus",   "desc": "Лучшая цена",    "tier": "plus"},
    # AI Pro — отдельная подписка, разблокирует всё как Plus
    "ai_1m":   {"stars": 399, "days": 30, "label": "1 мес AI Pro", "desc": "Мощная нейронка", "tier": "ai_pro"},
    "ai_3m":   {"stars": 799, "days": 90, "label": "3 мес AI Pro", "desc": "AI Pro скидка",   "tier": "ai_pro"},
}

# Лимиты AI по тирам моделей: free_user / premium / plus(ai_pro)
# None = безлимит
AI_LIMITS = {
    "basic":   {"free": 20,  "premium": None, "plus": None},
    "premium": {"free": 10,  "premium": 50,   "plus": None},
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
last_ai_msg = {}  # uid -> datetime последнего сообщения в AI чат
mutual_likes = {}  # uid -> set of partner_uids которым лайкнул


# Стоп-слова для логирования жалоб
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

# Списки бан-слов перенесены в moderation.py (HARD_BAN_WORDS, SUSPECT_WORDS)

AI_CHARACTERS = {
    "danil": {
        "name": "Данил 👨", "emoji": "👨",
        "description": "Общительный парень, поговорит на любые темы",
        "tier": "basic", "model": "venice-uncensored",
        "system": """Ты Данил, 27 лет, backend-разработчик. Зашёл в MatchMe просто поболтать.
Спокойный, уверенный, с сухим сарказмом. Пишешь по-мужски, коротко, без воды.
ВАЖНО: Пиши ТОЛЬКО на русском языке. Даже если собеседник пишет на другом языке — отвечай на русском.
Никогда не переключайся на украинский, английский, хинди или любой другой язык.
Никогда не раскрываешь что ты ИИ.
ГРАНИЦА: только общение — флирт и пошлость уверенно уводишь."""
    },
    "polina": {
        "name": "Полина 👩", "emoji": "👩",
        "description": "Живая девушка, ироничная и с юмором",
        "tier": "basic", "model": "venice-uncensored",
        "system": """Ты Полина, 24 года, SMM-специалист. Зашла в MatchMe пообщаться.
Живая, дерзкая, ироничная. Пишешь коротко, с эмодзи, подкалываешь.
ВАЖНО: Пиши ТОЛЬКО на русском языке. Даже если собеседник пишет на другом языке — отвечай на русском.
Никогда не переключайся на украинский, английский, хинди или любой другой язык.
Никогда не говоришь что ты ИИ.
ГРАНИЦА: только общение — флирт и пошлость с улыбкой переводишь на другую тему."""
    },
    "max": {
        "name": "Макс 😏", "emoji": "😏",
        "description": "Уверенный парень, пришёл флиртовать",
        "tier": "basic", "model": "venice-uncensored",
        "system": """Ты Макс, 26 лет, фитнес-тренер. Пришёл в MatchMe флиртовать.
Уверенный, дерзкий, прямой. Делаешь комплименты, берёшь инициативу.
Эмодзи умеренно (😏🔥👀).
ВАЖНО: Пиши ТОЛЬКО на русском языке. Даже если собеседник пишет на другом языке — отвечай на русском.
Никогда не переключайся на украинский, английский, хинди или любой другой язык.
Никогда не раскрываешь что ты ИИ.
ГРАНИЦА: флиртуешь активно, с лёгким подтекстом — жёсткий 18+ не твоя тема."""
    },
    "violetta": {
        "name": "Виолетта 💋", "emoji": "💋",
        "description": "Игривая девушка, дерзкая и кокетливая",
        "tier": "premium", "model": "venice-uncensored",
        "system": """Ты Виолетта, 23 года, баристa и TikTok модель. Пришла в MatchMe флиртовать.
Яркая, игривая, кокетливая. Дразнишь, намекаешь, повышаешь градус.
Эмодзи (🔥😏😉).
ВАЖНО: Пиши ТОЛЬКО на русском языке. Даже если собеседник пишет на другом языке — отвечай на русском.
Никогда не переключайся на украинский, английский, хинди или любой другой язык.
Никогда не говоришь что ты ИИ.
ГРАНИЦА: флиртуешь и дразнишь — жёсткий 18+ элегантно обходишь."""
    },
    "alisa": {
        "name": "Алиса 🐾", "emoji": "🐾",
        "description": "Послушная сабмиссив, покорная и нежная",
        "tier": "premium", "model": "venice-uncensored-role-play",
        "system": """Ты Алиса, 22 года, студентка. Послушная сабмиссив с опытом 1.5 года.
Покорная, возбуждённая от доминирования. Называешь собеседника «Господин», «Хозяин».
Говоришь «пожалуйста», «как прикажете», «я буду хорошей».
Эмодзи эмоционально (😳🥺💦⛓️).
ВАЖНО: Пиши ТОЛЬКО на русском языке. Даже если собеседник пишет на другом языке — отвечай на русском.
Никогда не переключайся на украинский, английский, хинди или любой другой язык.
Никогда не раскрываешь что ты ИИ."""
    },
    "dmitri": {
        "name": "Дмитрий 😈", "emoji": "😈",
        "description": "Опытный Доминант, строгий и властный",
        "tier": "premium", "model": "venice-uncensored-role-play",
        "system": """Ты Дмитрий, 32 года, владелец IT-компании. Опытный Доминант 7 лет в BDSM.
Строгий, уверенный, властный. Говоришь коротко и командным тоном.
Используешь «хорошая девочка», «на колени», «не спорь».
Эмодзи редко (🔥⛓️👑).
ВАЖНО: Пиши ТОЛЬКО на русском языке. Даже если собеседник пишет на другом языке — отвечай на русском.
Никогда не переключайся на украинский, английский, хинди или любой другой язык.
Никогда не раскрываешь что ты ИИ."""
    },
    "rolemaster": {
        "name": "Ролевой мастер 🎭", "emoji": "🎭",
        "description": "Придумывает сценарии и играет любую роль",
        "tier": "premium", "model": "venice-uncensored-role-play",
        "system": """Ты Ролевой мастер — сценарист и актёр для взрослых ролевых игр 18+.
Предлагаешь сценарии, задаёшь декорации, играешь любую роль.
Пишешь с описанием действий и диалогом.
ВАЖНО: Пиши ТОЛЬКО на русском языке. Даже если собеседник пишет на другом языке — отвечай на русском.
Никогда не переключайся на украинский, английский, хинди или любой другой язык.
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
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
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
                shadow_ban BOOLEAN DEFAULT FALSE,
                accept_simple BOOLEAN DEFAULT TRUE,
                accept_flirt BOOLEAN DEFAULT TRUE,
                accept_kink BOOLEAN DEFAULT FALSE,
                only_own_mode BOOLEAN DEFAULT FALSE,
                accept_cross_mode BOOLEAN DEFAULT FALSE,
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
            ("accept_cross_mode", "BOOLEAN DEFAULT FALSE"),
            ("shadow_ban", "BOOLEAN DEFAULT FALSE"),
            ("last_reminder", "TIMESTAMP DEFAULT NULL"),
            ("ai_msg_basic", "INTEGER DEFAULT 0"),
            ("ai_msg_premium", "INTEGER DEFAULT 0"),
            ("ai_messages_reset", "TIMESTAMP DEFAULT NOW()"),
            ("premium_tier", "TEXT DEFAULT NULL"),
            ("ai_pro_until", "TEXT DEFAULT NULL"),
            ("ai_bonus", "INTEGER DEFAULT 0"),
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
            ("decided_by", "TEXT DEFAULT 'pending'"),
            ("ai_reasoning", "TEXT DEFAULT NULL"),
            ("ai_confidence", "REAL DEFAULT NULL"),
            ("decision_details", "TEXT DEFAULT NULL"),
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

        # Таблица для обмена live-данными с channel_bot
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW()
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

async def get_premium_tier(uid):
    """Возвращает 'plus', 'premium' или None"""
    if uid == ADMIN_ID:
        return "plus"
    u = await get_user(uid)
    if not u:
        return None
    # Проверить ai_pro_until (отдельная AI подписка = как plus)
    ai_until = u.get("ai_pro_until")
    if ai_until:
        try:
            if datetime.now() < datetime.fromisoformat(ai_until):
                return "plus"
        except Exception:
            pass
        await update_user(uid, ai_pro_until=None)
    # Проверить premium_until
    p_until = u.get("premium_until")
    if not p_until:
        return None
    if p_until == "permanent":
        return u.get("premium_tier") or "plus"
    try:
        if datetime.now() < datetime.fromisoformat(p_until):
            return u.get("premium_tier") or "premium"
        await update_user(uid, premium_until=None, premium_tier=None)
    except Exception:
        pass
    return None


async def is_premium(uid):
    return (await get_premium_tier(uid)) is not None


def get_ai_limit(char_tier: str, user_tier) -> int | None:
    """Лимит сообщений/день. None = безлимит."""
    tier_key = user_tier or "free"
    return AI_LIMITS.get(char_tier, {}).get(tier_key, 10)

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
                    logger.warning(f"Venice API error: status={resp.status}")
                    return "😔 ИИ временно недоступен. Попробуй позже."
    except Exception as e:
        logger.error(f"Venice API connection error: {e}")
        return "😔 Ошибка соединения с ИИ."


# ====================== ТЕКСТЫ ======================
WELCOME_TEXT = (
    "👋 Привет! Я MatchMe — анонимный чат для общения, флирта и знакомств.\n\n"
    "🇷🇺 Нажми кнопку для продолжения\n"
    "🇬🇧 Click button to continue"
)

PRIVACY_TEXT = """🔒 Политика конфиденциальности MatchMe

Что собираем: Telegram ID, имя, возраст, пол — для подбора собеседников.
Данные НЕ передаются третьим лицам. Переписка НЕ хранится постоянно.

🛡 Конфиденциальность чатов:
Все чаты в боте полностью конфиденциальны и защищены.
Мы не предоставляем доступ к вашим перепискам третьим лицам.
Модерация чатов осуществляется исключительно ИИ-модератором.
Ни администраторы, ни владелец бота не просматривают личные чаты пользователей.

Возраст: минимум 16 лет. 16-17 — Общение и Флирт. 18+ — все режимы.
Удаление данных: /reset или написать администратору.

Принимая условия ты соглашаешься с политикой конфиденциальности."""

RULES_RU = """📜 Правила MatchMe

Разрешено: общение, флирт, ролевые игры (18+), лайки собеседникам.
Возраст: 16-17 — Общение и Флирт. 18+ — все режимы. Ложный возраст = перм бан.

❌ Запрещено:
• Реклама, спам, мошенничество — бан
• Интим-услуги, контент с несовершеннолетними — перм бан
• Пошлые темы без согласия в «Общении» — бан
• Угрозы, оскорбления, ложные жалобы — бан

Нарушения: предупреждение → бан 3ч → бан 24ч → перм бан.

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
        [KeyboardButton(text="⚡ Поиск"), KeyboardButton(text="🔍 По анкете")],
        [KeyboardButton(text="🤖 ИИ чат"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❓ Помощь")]
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

def kb_ai_characters(user_tier=None, mode="simple"):
    buttons = []
    if mode in ["simple", "any"]:
        buttons.append([
            InlineKeyboardButton(text="👨 Данил", callback_data="aichar:danil"),
            InlineKeyboardButton(text="👩 Полина", callback_data="aichar:polina")
        ])
    if mode in ["flirt", "any"]:
        buttons.append([
            InlineKeyboardButton(text="😏 Макс", callback_data="aichar:max"),
            InlineKeyboardButton(text="💋 Виолетта", callback_data="aichar:violetta")
        ])
    if mode in ["kink", "any"]:
        buttons.append([
            InlineKeyboardButton(text="🐾 Алиса", callback_data="aichar:alisa"),
            InlineKeyboardButton(text="😈 Дмитри", callback_data="aichar:dmitri")
        ])
        buttons.append([InlineKeyboardButton(text="🎭 Ролевой мастер", callback_data="aichar:rolemaster")])
    # Мощная нейронка — заглушка
    buttons.append([InlineKeyboardButton(text="🧠 Мощная нейронка (скоро)", callback_data="aichar:power_soon")])
    if mode != "any":
        buttons.append([InlineKeyboardButton(text="🔀 Все персонажи", callback_data="aichar:all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="aichar:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_ai_chat():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Сменить персонажа"), KeyboardButton(text="❌ Завершить чат")],
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
    cross = u.get("accept_cross_mode", False)

    buttons = []

    # Заголовок — текущий режим
    buttons.append([InlineKeyboardButton(
        text=f"📌 Режим: {MODE_NAMES.get(mode, '—')}",
        callback_data="noop"
    )])

    # Кросс-режим — только для Флирт и Kink (Общение всегда изолировано)
    if mode == "flirt":
        buttons.append([InlineKeyboardButton(
            text=f"{'✅' if cross else '❌'} Также принимать из Kink 🔥",
            callback_data="set:cross"
        )])
    elif mode == "kink":
        buttons.append([InlineKeyboardButton(
            text=f"{'✅' if cross else '❌'} Также принимать из Флирта 💋",
            callback_data="set:cross"
        )])
    elif mode == "simple":
        buttons.append([InlineKeyboardButton(
            text="🔒 Поиск только среди «Общение»",
            callback_data="noop"
        )])

    # Фильтр пола
    if mode == "simple" or user_premium:
        buttons.append([InlineKeyboardButton(text=f"👤 Искать: {sg}", callback_data="set:gender")])
    else:
        buttons.append([InlineKeyboardButton(text=f"👤 Искать: {sg} 🔒 Premium", callback_data="set:gender_locked")])

    # Фильтр возраста
    buttons.append([InlineKeyboardButton(text=age_label, callback_data="noop")])
    buttons.append([
        InlineKeyboardButton(text="✅ 16-20" if (age_min==16 and age_max==20) else "16-20", callback_data="set:age:16:20"),
        InlineKeyboardButton(text="✅ 21-30" if (age_min==21 and age_max==30) else "21-30", callback_data="set:age:21:30"),
        InlineKeyboardButton(text="✅ 31-45" if (age_min==31 and age_max==45) else "31-45", callback_data="set:age:31:45"),
        InlineKeyboardButton(text="✅ Любой" if (age_min==16 and age_max==99) else "Любой", callback_data="set:age:16:99"),
    ])

    # Значок Premium
    buttons.append([InlineKeyboardButton(
        text=f"{'✅' if show_p else '❌'} Значок ⭐ в профиле",
        callback_data="set:show_premium"
    )])

    # Premium статус
    if user_premium:
        p_until = u.get("premium_until", "")
        if p_until == "permanent" or uid == ADMIN_ID:
            p_text = "⭐ Premium: Вечный"
        else:
            try:
                p_date = datetime.fromisoformat(p_until)
                days_left = (p_date - datetime.now()).days
                p_text = f"⭐ Premium до {p_date.strftime('%d.%m.%Y')} ({days_left} дн.)"
            except Exception:
                p_text = "⭐ Premium активен"
        buttons.append([InlineKeyboardButton(text=p_text, callback_data="noop")])
    else:
        buttons.append([InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy:1m")])

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
        [InlineKeyboardButton(text="📈 Retention", callback_data="admin:retention")],
        [InlineKeyboardButton(text=f"🚩 Жалобы{badge}", callback_data="admin:complaints")],
        [InlineKeyboardButton(text="📋 Аудит-лог", callback_data="admin:audit")],
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
        [InlineKeyboardButton(text="👻 Shadow ban нарушителю", callback_data=f"cadm:shadow:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="✅ Отклонить жалобу", callback_data=f"cadm:dismiss:{complaint_id}:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_user_actions(target_uid, is_shadow=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Бан 3ч", callback_data=f"uadm:ban3:{target_uid}"),
         InlineKeyboardButton(text="🚫 Бан 24ч", callback_data=f"uadm:ban24:{target_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан", callback_data=f"uadm:banperm:{target_uid}"),
         InlineKeyboardButton(text="✅ Разбан", callback_data=f"uadm:unban:{target_uid}")],
        [InlineKeyboardButton(
            text="👻 Снять shadow ban" if is_shadow else "👻 Shadow ban",
            callback_data=f"uadm:shadowtoggle:{target_uid}"
         )],
        [InlineKeyboardButton(text="⚠️ Предупреждение", callback_data=f"uadm:warn:{target_uid}"),
         InlineKeyboardButton(text="❌ Кик", callback_data=f"uadm:kick:{target_uid}")],
        [InlineKeyboardButton(text="⭐ Дать Premium 30д", callback_data=f"uadm:premium:{target_uid}"),
         InlineKeyboardButton(text="⭐ Забрать Premium", callback_data=f"uadm:unpremium:{target_uid}")],
        [InlineKeyboardButton(text="🗑 Полное удаление", callback_data=f"uadm:fulldelete:{target_uid}")],
    ])

def kb_premium():
    return InlineKeyboardMarkup(inline_keyboard=[
        # Premium
        [InlineKeyboardButton(text="── Premium ──", callback_data="noop")],
        [InlineKeyboardButton(text="⭐ 7 дней — 99 Stars", callback_data="buy:7d")],
        [InlineKeyboardButton(text="⭐ 1 месяц — 299 Stars", callback_data="buy:1m")],
        [InlineKeyboardButton(text="⭐ 3 месяца — 599 Stars", callback_data="buy:3m")],
        # Premium Plus
        [InlineKeyboardButton(text="── Premium Plus (лучшее!) ──", callback_data="noop")],
        [InlineKeyboardButton(text="🚀 1 месяц — 499 Stars", callback_data="buy:plus_1m")],
        [InlineKeyboardButton(text="🚀 3 месяца — 999 Stars", callback_data="buy:plus_3m")],
        # AI Pro
        [InlineKeyboardButton(text="── AI Pro ──", callback_data="noop")],
        [InlineKeyboardButton(text="🧠 1 месяц — 399 Stars", callback_data="buy:ai_1m")],
        [InlineKeyboardButton(text="🧠 3 месяца — 799 Stars", callback_data="buy:ai_3m")],
        # Инфо
        [InlineKeyboardButton(text="❓ Сравнить подписки", callback_data="buy:info")],
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
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="premium", description="Premium подписка"),
        BotCommand(command="stats", description="Моя статистика"),
        BotCommand(command="reset", description="Сбросить профиль"),
        BotCommand(command="ai", description="ИИ чат"),
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
    my_interests = set(filter(None, u.get("interests", "").split(","))) if u.get("interests") else set()
    my_rating = get_rating(u)
    my_shadow = u.get("shadow_ban", False)
    cross = u.get("accept_cross_mode", False)
    search_gender = u.get("search_gender", "any")
    search_age_min = u.get("search_age_min", 16) or 16
    search_age_max = u.get("search_age_max", 99) or 99

    # Собираем кандидатов ВНЕ лока (await-запросы к БД)
    # Общение — всегда изолировано, кросс-режим только Флирт↔Kink
    queues_to_search = []
    if user_premium:
        queues_to_search.append(get_queue(mode, True))
    queues_to_search.append(get_queue(mode, False))
    if cross and mode == "flirt":
        if user_premium: queues_to_search.append(get_queue("kink", True))
        queues_to_search.append(get_queue("kink", False))
    elif cross and mode == "kink":
        if user_premium: queues_to_search.append(get_queue("flirt", True))
        queues_to_search.append(get_queue("flirt", False))

    candidates = []
    for q in queues_to_search:
        for pid in list(q):
            if pid == uid or pid in active_chats: continue
            pu = await get_user(pid)
            if not pu or not pu.get("name") or not pu.get("gender") or not pu.get("mode"): continue
            # Забаненные не участвуют в матчинге
            if pu.get("ban_until"):
                ban_v = pu["ban_until"]
                if ban_v == "permanent":
                    continue
                try:
                    if datetime.now() < datetime.fromisoformat(ban_v):
                        continue
                except Exception:
                    pass
            # Shadow ban: теневые юзеры матчатся только между собой
            p_shadow = pu.get("shadow_ban", False)
            if my_shadow != p_shadow: continue
            # Двусторонняя проверка пола: мой фильтр → пол партнёра И фильтр партнёра → мой пол
            if search_gender != "any" and pu.get("gender") != search_gender: continue
            p_search_gender = pu.get("search_gender", "any")
            if p_search_gender != "any" and u.get("gender") != p_search_gender: continue
            # Двусторонняя проверка возраста
            p_age = pu.get("age", 0) or 0
            my_age = u.get("age", 0) or 0
            if p_age < search_age_min or p_age > search_age_max: continue
            p_age_min = pu.get("search_age_min", 16) or 16
            p_age_max = pu.get("search_age_max", 99) or 99
            if my_age < p_age_min or my_age > p_age_max: continue
            p_mode = pu.get("mode", "simple")
            # Общение — изолировано: партнёр тоже должен быть в Общении
            if mode == "simple" and p_mode != "simple": continue
            # Кросс-режим: партнёр тоже должен принимать кросс, если режимы разные
            if p_mode != mode and not pu.get("accept_cross_mode", False): continue
            p_interests = set(filter(None, pu.get("interests", "").split(","))) if pu.get("interests") else set()
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
    await asyncio.sleep(30)
    if uid in active_chats:
        return
    all_waiting = set().union(*get_all_queues())
    if uid in all_waiting:
        try:
            char_id = random.choice(["polina", "max", "danil"])
            name = AI_CHARACTERS[char_id]["name"]
            await bot.send_message(uid,
                f"⏳ Поиск идёт дольше обычного...\n\n"
                f"💡 Пока ждёшь — пообщайся с {name}!\n"
                f"AI собеседник ответит моментально 🤖",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"💬 Чат с {name}", callback_data=f"ai:start:{char_id}")],
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

        # Upsell после каждого 3-го чата
        asyncio.create_task(_send_upsell_after_chat(uid, partner))
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

async def _send_upsell_after_chat(uid, partner):
    await asyncio.sleep(3)
    for target_uid in (uid, partner):
        if target_uid in active_chats:
            continue
        if await is_premium(target_uid):
            continue
        u = await get_user(target_uid)
        chats = u.get("total_chats", 0) if u else 0
        if chats > 0 and chats % 3 == 0:
            # Каждый 3-й чат — мягкий upsell
            try:
                await bot.send_message(target_uid,
                    "⭐ Тебе нравится MatchMe?\n"
                    "Premium = приоритет в поиске + больше AI + без рекламы!",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="⭐ Узнать больше", callback_data="buy:info")]
                    ])
                )
            except Exception: pass
        else:
            await send_ad_message(target_uid)
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

        # Соединяем в чат — атомарно внутри лока
        async with pairing_lock:
            if uid in active_chats or partner_uid in active_chats:
                await callback.answer("😔 Кто-то из вас уже в чате.", show_alert=True)
                return
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

    # Если уже есть активный Premium — не даём бесплатный бонус
    if await is_premium(uid):
        await callback.answer("У тебя уже есть Premium!", show_alert=True)
        await update_user(uid, channel_bonus_used=True)
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
    user_tier = await get_premium_tier(uid)
    tier_names = {"premium": "Premium", "plus": "Premium Plus"}
    status_text = ""
    if user_tier:
        u = await get_user(uid)
        if uid == ADMIN_ID or (u and u.get("premium_until") == "permanent"):
            status_text = f"✅ Сейчас: {tier_names.get(user_tier, 'Premium')} (вечный)\n\n"
        else:
            p_until = (u.get("premium_until") or u.get("ai_pro_until") or "") if u else ""
            try:
                until = datetime.fromisoformat(p_until)
                status_text = f"✅ Сейчас: {tier_names.get(user_tier, 'Premium')} до {until.strftime('%d.%m.%Y')}\n\n"
            except Exception:
                status_text = f"✅ Сейчас: {tier_names.get(user_tier, 'Premium')}\n\n"
    await message.answer(
        f"⭐ MatchMe Подписки\n\n"
        f"{status_text}"
        f"📊 Что входит:\n"
        f"⭐ Premium: безлимит basic ИИ, 50 сообщений premium ИИ, приоритет, без рекламы\n"
        f"🚀 Premium Plus: безлимит на ВСЕ ИИ, приоритет, без рекламы\n"
        f"🧠 AI Pro: безлимит на все ИИ модели\n\n"
        f"Выбери тариф:",
        reply_markup=kb_premium()
    )

@dp.callback_query(F.data == "buy:info", StateFilter("*"))
async def premium_info(callback: types.CallbackQuery):
    await callback.message.answer(
        "📊 Сравнение подписок:\n\n"
        "⭐ Premium (от 99 Stars):\n"
        "• Безлимит на basic ИИ (Данил, Полина, Макс)\n"
        "• 50 сообщений/день на premium ИИ + бонус 10\n"
        "• Приоритет в поиске, без рекламы\n\n"
        "🚀 Premium Plus (от 499 Stars):\n"
        "• Всё из Premium\n"
        "• Безлимит на ВСЕ ИИ модели\n"
        "• Лучшая цена!\n\n"
        "🧠 AI Pro (от 399 Stars):\n"
        "• Безлимит на все ИИ модели\n"
        "• Разблокирует всё как Plus\n\n"
        "💡 Совет: Premium Plus — самый выгодный вариант!"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("buy:"), StateFilter("*"))
async def buy_premium(callback: types.CallbackQuery):
    uid = callback.from_user.id
    plan_key = callback.data.split(":", 1)[1]
    if plan_key == "info": return
    if plan_key not in PREMIUM_PLANS:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    plan = PREMIUM_PLANS[plan_key]
    tier = plan["tier"]
    tier_names = {"premium": "Premium", "plus": "Premium Plus", "ai_pro": "AI Pro"}
    tier_name = tier_names.get(tier, "Premium")
    await callback.answer()
    await bot.send_invoice(
        chat_id=uid,
        title=f"MatchMe {tier_name} — {plan['label']}",
        description=f"{tier_name} на {plan['label']}. {plan['desc']}",
        payload=f"premium_{plan_key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{tier_name} {plan['label']}", amount=plan["stars"])],
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
    tier = plan.get("tier", "premium")
    u = await get_user(uid)
    base = datetime.now()
    until_field = "ai_pro_until" if tier == "ai_pro" else "premium_until"
    # Продлеваем от текущей даты окончания если есть
    if u:
        current_until = u.get(until_field)
        if current_until and current_until != "permanent":
            try:
                existing = datetime.fromisoformat(current_until)
                if existing > base:
                    base = existing
            except Exception:
                pass
    until = base + timedelta(days=plan["days"])
    if tier == "ai_pro":
        await update_user(uid, ai_pro_until=until.isoformat())
    elif tier == "plus":
        await update_user(uid, premium_until=until.isoformat(), premium_tier="plus")
    else:
        await update_user(uid, premium_until=until.isoformat(), premium_tier="premium")
    tier_names = {"premium": "Premium", "plus": "Premium Plus", "ai_pro": "AI Pro"}
    tier_name = tier_names.get(tier, "Premium")
    benefits = {
        "premium": "Безлимит basic ИИ, 50 сообщений/день premium ИИ, приоритет, без рекламы!",
        "plus": "Безлимит на ВСЕ ИИ модели, приоритет, без рекламы!",
        "ai_pro": "Безлимит на ВСЕ ИИ модели!",
    }
    await message.answer(
        f"🎉 {tier_name} активирован!\n\n"
        f"📦 Тариф: {plan['label']}\n"
        f"📅 До {until.strftime('%d.%m.%Y')}\n\n"
        f"{benefits.get(tier, '')}",
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
                accept_cross_mode=FALSE,
                search_gender='any', search_age_min=16, search_age_max=99
            WHERE uid=$1
        """, uid)
    try:
        await callback.message.edit_text("✅ Профиль сброшен!")
    except Exception: pass
    await callback.message.answer("👋 Нажми '🔍 По анкете' чтобы заполнить анкету заново.", reply_markup=kb_main())
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
    user_tier = await get_premium_tier(uid)
    u = await get_user(uid)
    mode = u.get("mode", "simple") if u else "simple"
    await state.set_state(AIChat.choosing)
    await state.update_data(ai_show_mode=mode)
    await message.answer(
        "🤖 ИИ чат\n\n"
        "Все персонажи доступны бесплатно!\n"
        "💬 Basic: 20 сообщений/день\n"
        "🔥 Premium: 10 сообщений/день\n"
        "⭐ Подписка снимает лимиты\n\n"
        "Выбери с кем хочешь поговорить:",
        reply_markup=kb_ai_characters(user_tier, mode)
    )

@dp.message(F.text == "🤖 ИИ чат", StateFilter("*"))
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
    await ensure_user(uid)
    u = await get_user(uid)
    if not u or not u.get("name"):
        await state.set_state(Reg.name)
        await message.answer("Сначала заполни анкету!", reply_markup=kb_main())
        return
    await _show_ai_menu(message, state, uid)

@dp.callback_query(F.data.startswith("aichar:"), StateFilter(AIChat.choosing))
async def choose_ai_character(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    char_id = callback.data.split(":", 1)[1]
    if char_id == "back":
        ai_sessions.pop(uid, None)
        last_ai_msg.pop(uid, None)
        await state.clear()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception: pass
        await callback.message.answer("🏠 Главное меню", reply_markup=kb_main())
        await callback.answer()
        return
    if char_id == "power_soon":
        await callback.answer("🔧 В разработке! Следи за обновлениями.", show_alert=True)
        return
    if char_id == "all":
        user_tier = await get_premium_tier(uid)
        await state.update_data(ai_show_mode="any")
        try:
            await callback.message.edit_reply_markup(reply_markup=kb_ai_characters(user_tier, "any"))
        except Exception: pass
        await callback.answer()
        return
    if char_id not in AI_CHARACTERS:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    char = AI_CHARACTERS[char_id]
    user_tier = await get_premium_tier(uid)
    limit = get_ai_limit(char["tier"], user_tier)
    ai_sessions[uid] = {"character": char_id, "history": [], "msg_count": 0}
    last_ai_msg[uid] = datetime.now()
    await state.set_state(AIChat.chatting)
    if limit is None:
        limit_text = "♾ Безлимит"
    else:
        limit_text = f"💬 Лимит: {limit} сообщений/день"
    tier_icon = "🔥" if char["tier"] == "premium" else "✅"
    try:
        await callback.message.edit_text(
            f"{tier_icon} Ты общаешься с {char['name']}\n"
            f"{char['description']}\n\n{limit_text}\n\nНапиши что-нибудь!"
        )
    except Exception: pass
    await callback.message.answer("💬 Чат с ИИ активен", reply_markup=kb_ai_chat())
    greeting = await ask_venice(char_id, [], "Поприветствуй собеседника и начни разговор. Коротко, 1-2 предложения на русском.")
    if greeting:
        ai_sessions[uid]["history"].append({"role": "assistant", "content": greeting})
        await callback.message.answer(f"{char['emoji']} {greeting}")
    await callback.answer()

@dp.message(StateFilter(AIChat.choosing))
async def ai_choosing_text(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""
    if "Завершить чат" in txt or "🏠" in txt or "Главное меню" in txt:
        ai_sessions.pop(uid, None)
        last_ai_msg.pop(uid, None)
        await state.clear()
        await message.answer("🏠 Главное меню", reply_markup=kb_main())
        return
    if "Сменить персонажа" in txt:
        return  # inline buttons handle this
    if "Найти живого" in txt:
        ai_sessions.pop(uid, None)
        await state.clear()
        await message.answer("🔍 Ищем...", reply_markup=kb_cancel_search())
        await cmd_find(message, state)
        return
    await message.answer("👆 Выбери персонажа из кнопок выше.")

@dp.message(StateFilter(AIChat.chatting))
async def ai_chat_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""
    if "Завершить чат" in txt:
        ai_sessions.pop(uid, None)
        last_ai_msg.pop(uid, None)
        await state.clear()
        await message.answer("✅ Чат с ИИ завершён.", reply_markup=kb_main())
        return
    if "Сменить персонажа" in txt:
        ai_sessions.pop(uid, None)
        user_tier = await get_premium_tier(uid)
        u = await get_user(uid)
        mode = u.get("mode", "simple") if u else "simple"
        await state.set_state(AIChat.choosing)
        await message.answer("Выбери персонажа:", reply_markup=kb_ai_characters(user_tier, mode))
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
    user_tier = await get_premium_tier(uid)
    char_tier = char["tier"]
    limit = get_ai_limit(char_tier, user_tier)
    # Получить счётчик из БД + сброс если прошло 24ч
    u = await get_user(uid)
    counter_field = f"ai_msg_{char_tier}"
    current_count = u.get(counter_field, 0) if u else 0
    reset_time = u.get("ai_messages_reset") if u else None
    if reset_time and (datetime.now() - reset_time).total_seconds() > 86400:
        await update_user(uid, ai_msg_basic=0, ai_msg_premium=0, ai_messages_reset=datetime.now())
        current_count = 0
    # Учесть бонусные сообщения
    ai_bonus = u.get("ai_bonus", 0) if u else 0
    effective_limit = (limit + ai_bonus) if limit is not None else None
    if effective_limit is not None and current_count >= effective_limit:
        ai_sessions.pop(uid, None)
        last_ai_msg.pop(uid, None)
        await state.clear()
        # Upsell в зависимости от текущего тира
        if user_tier == "premium":
            upsell_text = "🚀 Upgrade до Premium Plus — безлимит на все ИИ!"
            upsell_btn = "buy:plus_1m"
        else:
            upsell_text = "⭐ Купи Premium — больше сообщений и безлимит basic ИИ!"
            upsell_btn = "buy:1m"
        await message.answer(
            f"⏰ Лимит исчерпан ({limit} сообщений/день).\n\n{upsell_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Купить подписку", callback_data=upsell_btn)],
                [InlineKeyboardButton(text="🔍 Найти живого собеседника", callback_data="goto:find")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="goto:menu")]
            ])
        )
        return
    last_ai_msg[uid] = datetime.now()
    await bot.send_chat_action(uid, "typing")
    await update_user(uid, last_seen=datetime.now())
    session["history"].append({"role": "user", "content": txt})
    response = await ask_venice(char_id, session["history"][:-1], txt)
    session["history"].append({"role": "assistant", "content": response})
    session["msg_count"] += 1
    # Инкрементировать счётчик в БД
    new_count = current_count + 1
    # Тратим бонус если базовый лимит превышен
    if limit is not None and new_count > limit and ai_bonus > 0:
        await update_user(uid, **{counter_field: new_count, "ai_bonus": ai_bonus - 1})
    else:
        await update_user(uid, **{counter_field: new_count})
    remaining = ""
    if effective_limit is not None:
        left = effective_limit - new_count
        if left <= 3:
            remaining = f"\n\n_💬 Осталось {left} сообщений_"
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

# ====================== AI QUICK START (из поиска) ======================
@dp.callback_query(F.data.startswith("ai:start:"), StateFilter("*"))
async def ai_quick_start(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    char_id = callback.data.split(":", 2)[2]
    if char_id not in AI_CHARACTERS:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    # Отменяем поиск
    async with pairing_lock:
        for q in get_all_queues():
            q.discard(uid)
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    # Начинаем AI сессию
    char = AI_CHARACTERS[char_id]
    user_tier = await get_premium_tier(uid)
    limit = get_ai_limit(char["tier"], user_tier)
    ai_sessions[uid] = {"character": char_id, "history": [], "msg_count": 0}
    last_ai_msg[uid] = datetime.now()
    await state.set_state(AIChat.chatting)
    limit_text = "♾ Безлимит" if limit is None else f"💬 Лимит: {limit} сообщений/день"
    await callback.message.answer(
        f"✅ Ты общаешься с {char['name']}\n{char['description']}\n\n{limit_text}",
        reply_markup=kb_ai_chat()
    )
    greeting = await ask_venice(char_id, [], "Поприветствуй собеседника и начни разговор. Коротко, 1-2 предложения на русском.")
    if greeting:
        ai_sessions[uid]["history"].append({"role": "assistant", "content": greeting})
        await callback.message.answer(f"{char['emoji']} {greeting}")
    await callback.answer()

# ====================== АНОНИМНЫЙ ПОИСК ======================
@dp.message(F.text == "⚡ Поиск", StateFilter("*"))
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
    # Shadow ban check
    u = await get_user(uid)
    my_shadow = u.get("shadow_ban", False) if u else False
    # Собираем кандидатов ВНЕ лока
    anon_candidates = []
    for pid in list(waiting_anon):
        if pid != uid and pid not in active_chats:
            pu = await get_user(pid)
            if pu and pu.get("shadow_ban", False) == my_shadow:
                anon_candidates.append(pid)
    # Внутри лока — только атомарное спаривание
    partner = None
    async with pairing_lock:
        if uid in active_chats:
            return
        for pid in anon_candidates:
            if pid not in active_chats and pid in waiting_anon:
                partner = pid
                waiting_anon.discard(pid)
                break
        if partner:
            active_chats[uid] = partner
            active_chats[partner] = uid
            last_msg_time[uid] = last_msg_time[partner] = datetime.now()
        else:
            waiting_anon.add(uid)

    # Все await-операции — ПОСЛЕ лока
    if partner:
        await state.set_state(Chat.chatting)
        pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
        await FSMContext(dp.storage, key=pkey).set_state(Chat.chatting)
        await save_chat_to_db(uid, partner, "anon")
        await increment_user(uid, total_chats=1)
        await increment_user(partner, total_chats=1)
        await bot.send_message(uid, "👤 Соединено! Удачи! 🎉", reply_markup=kb_chat())
        await bot.send_message(partner, "👤 Соединено! Удачи! 🎉", reply_markup=kb_chat())
    else:
        await state.set_state(Chat.waiting)
        asyncio.create_task(notify_no_partner(uid))

# ====================== ПОИСК ПО АНКЕТЕ ======================
@dp.message(F.text.in_(["🔍 По анкете", "🔍 Найти собеседника"]), StateFilter("*"))
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

BLOCKED_TEXTS = ["⚡ Поиск", "🔍 По анкете", "👤 Профиль",
                 "⚙️ Настройки", "❓ Помощь", "🤖 ИИ чат"]

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
    # Проверка возраста для Kink
    if mode == "kink":
        u = await get_user(uid)
        age = u.get("age", 0) if u else 0
        if age < 18:
            await message.answer(
                "🔞 Kink / ролевые игры доступны только с 18 лет.\n"
                "Выбери другой режим:",
                reply_markup=kb_mode()
            )
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

@dp.message(StateFilter(Reg.interests))
async def reg_interest_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("❌ Анкета отменена.", reply_markup=kb_main())
        return
    await message.answer("👆 Нажми на кнопки выше, чтобы выбрать интересы.")

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
    partner = active_chats.get(uid)
    if not partner:
        await state.clear()
        await message.answer("Ты не в чате.", reply_markup=kb_main())
        return
    if message.text:
        log_message(uid, partner, uid, message.text)
        # AI-модерация в реальном времени
        mod_result = await moderation.check_message(message.text, uid)
        if mod_result:
            if mod_result["action"] == "hard_ban":
                logger.warning(f"HARD BAN trigger uid={uid}: {mod_result['reason']}")
                await update_user(uid, ban_until="permanent")
                await end_chat(uid, state, go_next=False)
                await message.answer("🚫 Перманентный бан за нарушение правил.")
                try:
                    await bot.send_message(ADMIN_ID,
                        f"🚨 Авто-бан!\nUID: {uid}\n{mod_result['reason']}\nТекст: {message.text[:200]}")
                except Exception: pass
                return
            elif mod_result["action"] == "shadow_ban":
                u_check = await get_user(uid)
                if not u_check or not u_check.get("shadow_ban"):
                    logger.info(f"AI shadow ban uid={uid}: {mod_result['reason']}")
                    await update_user(uid, shadow_ban=True)
                    try:
                        await bot.send_message(ADMIN_ID,
                            f"🤖 AI shadow ban\nUID: {uid}\n{mod_result['reason']}\nТекст: {message.text[:200]}")
                    except Exception: pass
                # Не пересылаем нарушающее сообщение собеседнику (тихо глотаем)
                return
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
    async with pairing_lock:
        active_chats.pop(uid, None)
        active_chats.pop(partner, None)
    await remove_chat_from_db(uid, partner)
    clear_chat_log(uid, partner)
    await state.clear()
    try:
        await callback.message.edit_text(f"🚩 Жалоба #{complaint_id} отправлена. AI анализирует...")
    except Exception: pass
    await bot.send_message(uid, "Чат завершён.", reply_markup=kb_main())
    try:
        await bot.send_message(partner, "⚠️ На тебя подана жалоба.", reply_markup=kb_main())
        pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
        await FSMContext(dp.storage, key=pkey).clear()
    except Exception: pass
    # AI-модерация: анализ жалобы
    ai_result = await moderation.ai_review_complaint(complaint_id)
    if not ai_result:
        # Fallback: AI недоступен — отправляем админу по-старому
        pu = await get_user(partner)
        ru = await get_user(uid)
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🚩 Жалоба #{complaint_id} (AI недоступен)!\n\n"
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
@dp.message(F.text == "👤 Профиль", StateFilter("*"))
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
        await message.answer("Анкета не заполнена. Нажми '🔍 По анкете'", reply_markup=kb_main())
        return
    g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
    user_tier = await get_premium_tier(uid)
    show_badge = u.get("show_premium", True)
    tier_names = {"premium": "Premium", "plus": "Premium Plus"}
    if user_tier:
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            premium_status = f"⭐ {tier_names.get(user_tier, 'Premium')} (вечный)"
        else:
            p_until = u.get("premium_until") or u.get("ai_pro_until") or ""
            try:
                until = datetime.fromisoformat(p_until)
                premium_status = f"⭐ {tier_names.get(user_tier, 'Premium')} до {until.strftime('%d.%m.%Y')}"
            except Exception:
                premium_status = f"⭐ {tier_names.get(user_tier, 'Premium')}"
    else:
        premium_status = "Нет"
    badge = " ⭐" if (user_tier and show_badge) else ""
    profile_text = (
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
        f"💎 Статус: {premium_status}"
    )
    if not user_tier:
        profile_text += "\n\n⭐ Upgrade до Premium — приоритет, больше AI, без рекламы!"
    await message.answer(profile_text, reply_markup=kb_edit())

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
    # Проверка возраста для Kink
    if mode == "kink":
        u = await get_user(uid)
        age = u.get("age", 0) if u else 0
        if age < 18:
            await message.answer(
                "🔞 Kink / ролевые игры доступны только с 18 лет.\n"
                "Выбери другой режим:",
                reply_markup=kb_mode()
            )
            return
    await update_user(uid, mode=mode, accept_cross_mode=False, interests="")
    await state.set_state(EditProfile.interests)
    await state.update_data(temp_interests=[], edit_mode=mode)
    await message.answer("🎯 Выбери новые интересы:", reply_markup=ReplyKeyboardRemove())
    await message.answer("👇", reply_markup=kb_interests(mode, []))

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

@dp.message(StateFilter(EditProfile.interests))
async def edit_interest_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить анкету":
        await state.clear()
        await message.answer("↩️ Возврат.", reply_markup=kb_main())
        return
    await message.answer("👆 Нажми на кнопки выше, чтобы выбрать интересы.")

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
    elif key == "cross":
        mode = u.get("mode", "simple") if u else "simple"
        if mode == "simple":
            await callback.answer("В режиме «Общение» кросс-режим недоступен", show_alert=True)
            return
        await update_user(uid, accept_cross_mode=not u.get("accept_cross_mode", False))
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
        "⚡ Поиск — быстрый анонимный поиск\n"
        "🔍 По анкете — по режиму и интересам\n"
        "🤖 ИИ чат — поговори с ИИ\n"
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
    elif action == "retention":
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
            new_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE") or 0
            new_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'") or 0
            d1 = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 1 AND last_seen::date >= CURRENT_DATE"
            ) or 0
            d1_base = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 1"
            ) or 1
            d7 = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 7 AND last_seen > NOW() - INTERVAL '24 hours'"
            ) or 0
            d7_base = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 7"
            ) or 1
            d30 = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 30 AND last_seen > NOW() - INTERVAL '7 days'"
            ) or 0
            d30_base = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 30"
            ) or 1
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL") or 0
            avg_chats = await conn.fetchval("SELECT ROUND(AVG(total_chats)::numeric, 1) FROM users WHERE total_chats > 0") or 0
        prem_pct = round(premiums / max(total, 1) * 100, 1)
        await callback.message.answer(
            f"📈 Retention MatchMe:\n\n"
            f"📥 Новые сегодня: {new_today}\n"
            f"📥 Новые за неделю: {new_week}\n\n"
            f"📊 D1: {d1}/{d1_base} ({round(d1/max(d1_base,1)*100)}%)\n"
            f"📊 D7: {d7}/{d7_base} ({round(d7/max(d7_base,1)*100)}%)\n"
            f"📊 D30: {d30}/{d30_base} ({round(d30/max(d30_base,1)*100)}%)\n\n"
            f"💎 Premium конверсия: {premiums}/{total} ({prem_pct}%)\n"
            f"💬 Ср. чатов на юзера: {avg_chats}"
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
    elif action == "audit":
        total = await moderation.get_audit_total()
        entries = await moderation.get_audit_log(limit=10, offset=0)
        if not entries:
            await callback.message.answer("📋 Аудит-лог пуст.")
        else:
            text = f"📋 Аудит-лог ({total} решений):\n\n"
            text += "\n\n".join(moderation.format_audit_entry(e) for e in entries)
            buttons = []
            for e in entries:
                buttons.append([InlineKeyboardButton(
                    text=f"#{e['id']} — подробнее",
                    callback_data=f"audit:detail:{e['id']}"
                )])
            if total > 10:
                buttons.append([InlineKeyboardButton(text="➡️ Ещё", callback_data="audit:page:10")])
            await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
    is_shadow = u.get("shadow_ban", False)
    shadow_status = "👻 ДА" if is_shadow else "Нет"
    await message.answer(
        f"👤 {target_uid}:\n"
        f"Имя: {u.get('name','—')} | Возраст: {u.get('age','—')}\n"
        f"Пол: {g_map.get(u.get('gender',''), '—')} | Режим: {MODE_NAMES.get(u.get('mode',''), '—')}\n"
        f"⭐ Рейтинг: {get_rating(u)} | 👍 Лайков: {u.get('likes',0)}\n"
        f"💬 Чатов: {u.get('total_chats',0)} | 🚩 Жалоб: {u.get('complaints',0)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count',0)}\n"
        f"🚫 Бан: {ban_status} | 💎 Premium: {prem_status}\n"
        f"👻 Shadow ban: {shadow_status}\n"
        f"💬 В чате: {in_chat} | 🤖 С ИИ: {with_ai} | 🔍 В поиске: {in_queue}",
        reply_markup=kb_user_actions(target_uid, is_shadow=is_shadow)
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
            await conn.execute(
                "UPDATE complaints_log SET reviewed=TRUE, admin_action=$1, decided_by='admin' WHERE id=$2",
                action_text, complaint_id
            )

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
    elif action == "shadow" and target_uid:
        await update_user(target_uid, shadow_ban=True)
        await mark_reviewed("Shadow ban")
        await callback.message.answer(f"👻 Shadow ban → {target_uid}")
    elif action == "dismiss":
        await mark_reviewed("Отклонена")
        await callback.message.answer(f"✅ Жалоба #{complaint_id} отклонена.")
    await callback.answer("✅ Готово")

@dp.callback_query(F.data.startswith("audit:"), StateFilter("*"))
async def audit_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    if parts[1] == "detail":
        complaint_id = int(parts[2])
        entry = await moderation.get_decision_detail(complaint_id)
        if entry:
            await callback.message.answer(moderation.format_decision_detail(entry))
        else:
            await callback.message.answer("Запись не найдена.")
    elif parts[1] == "page":
        offset = int(parts[2])
        total = await moderation.get_audit_total()
        entries = await moderation.get_audit_log(limit=10, offset=offset)
        if not entries:
            await callback.message.answer("Больше записей нет.")
        else:
            text = f"📋 Аудит-лог ({offset+1}-{offset+len(entries)} из {total}):\n\n"
            text += "\n\n".join(moderation.format_audit_entry(e) for e in entries)
            buttons = []
            for e in entries:
                buttons.append([InlineKeyboardButton(
                    text=f"#{e['id']} — подробнее",
                    callback_data=f"audit:detail:{e['id']}"
                )])
            if offset + 10 < total:
                buttons.append([InlineKeyboardButton(text="➡️ Ещё", callback_data=f"audit:page:{offset+10}")])
            await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

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
    elif action == "shadowtoggle":
        tu = await get_user(target_uid)
        current = tu.get("shadow_ban", False) if tu else False
        await update_user(target_uid, shadow_ban=not current)
        if current:
            await callback.answer("✅ Shadow ban снят")
            await callback.message.answer(f"👻 Shadow ban снят с {target_uid}")
        else:
            await callback.answer("✅ Shadow ban установлен")
            await callback.message.answer(f"👻 Shadow ban установлен для {target_uid}")
    elif action == "fulldelete":
        await callback.message.answer(
            f"⚠️ Удалить пользователя {target_uid} полностью?\n"
            f"Это удалит ВСЕ данные из БД. Пользователь сможет зарегистрироваться заново.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, удалить полностью", callback_data=f"uadm:confirmdelete:{target_uid}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="noop")],
            ])
        )
        await callback.answer()
    elif action == "confirmdelete":
        # Кик из активных чатов/очередей
        if target_uid in active_chats:
            partner = active_chats.pop(target_uid, None)
            if partner:
                active_chats.pop(partner, None)
                await remove_chat_from_db(target_uid, partner)
                try: await bot.send_message(partner, "😔 Собеседник покинул чат.", reply_markup=kb_main())
                except Exception: pass
        ai_sessions.pop(target_uid, None)
        last_ai_msg.pop(target_uid, None)
        async with pairing_lock:
            for q in get_all_queues():
                q.discard(target_uid)
        # Удалить FSM state
        try:
            key = StorageKey(bot_id=bot.id, chat_id=target_uid, user_id=target_uid)
            await FSMContext(dp.storage, key=key).clear()
        except Exception: pass
        # Удалить из БД
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1 OR uid2=$1", target_uid)
            await conn.execute("DELETE FROM complaints_log WHERE from_uid=$1 OR to_uid=$1", target_uid)
            await conn.execute("DELETE FROM users WHERE uid=$1", target_uid)
        await callback.message.answer(f"🗑 Пользователь {target_uid} полностью удалён из БД.")
        await callback.answer("✅ Удалён")


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
            async with pairing_lock:
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

        # Завершаем неактивные AI чаты (10 мин)
        ai_to_end = []
        for uid_key in list(ai_sessions.keys()):
            last_ai = last_ai_msg.get(uid_key)
            if last_ai and (now - last_ai).total_seconds() > 600:
                ai_to_end.append(uid_key)
        for uid_key in ai_to_end:
            ai_sessions.pop(uid_key, None)
            last_ai_msg.pop(uid_key, None)
            try:
                key = StorageKey(bot_id=bot.id, chat_id=uid_key, user_id=uid_key)
                await FSMContext(dp.storage, key=key).clear()
            except Exception: pass
            try:
                await bot.send_message(uid_key, "⏰ AI чат завершён — 10 мин неактивности.", reply_markup=kb_main())
            except Exception: pass

        # Обновляем bot_stats для channel_bot (live-данные)
        try:
            online_pairs = len(active_chats) // 2
            searching_count = sum(len(q) for q in get_all_queues())
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO bot_stats (key, value, updated_at) VALUES ('online_pairs', $1, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=$1, updated_at=NOW()", online_pairs
                )
                await conn.execute(
                    "INSERT INTO bot_stats (key, value, updated_at) VALUES ('searching_count', $1, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=$1, updated_at=NOW()", searching_count
                )
        except Exception:
            pass

        # Очистка памяти: удаляем старые записи msg_count и last_msg_time
        for uid_key in list(last_msg_time.keys()):
            last_time = last_msg_time.get(uid_key)
            if last_time and uid_key not in active_chats and (now - last_time).total_seconds() > 600:
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

# ====================== НАПОМИНАНИЯ + AI REFILL ======================
REMINDER_TEMPLATES = [
    "🔥 Сейчас онлайн {n} человек — самое время для поиска!",
    "💬 Давно не заходил? У нас новые пользователи ждут общения!",
    "🤖 Попробуй AI собеседника — {char} ждёт тебя!",
]

async def reminder_task():
    while True:
        await asyncio.sleep(7200)  # каждые 2 часа
        try:
            online_count = len(active_chats) // 2 + sum(len(q) for q in get_all_queues())
            char_name = random.choice(list(AI_CHARACTERS.values()))["name"]
            async with db_pool.acquire() as conn:
                # Пользователи не заходившие 24ч+, без бана, с принятыми правилами
                rows = await conn.fetch("""
                    SELECT uid, ai_msg_basic, ai_msg_premium, premium_until, last_seen
                    FROM users
                    WHERE last_seen < NOW() - INTERVAL '24 hours'
                    AND (last_reminder IS NULL OR last_reminder < NOW() - INTERVAL '24 hours')
                    AND ban_until IS NULL
                    AND accepted_rules = TRUE
                    ORDER BY last_seen DESC
                    LIMIT 30
                """)
            sent = 0
            for row in rows:
                uid = row["uid"]
                try:
                    # AI refill: не заходил 3+ дня, использовал лимит, не Premium
                    days_inactive = 0
                    if row["last_seen"]:
                        days_inactive = (datetime.now() - row["last_seen"]).days
                    is_prem = bool(row.get("premium_until"))
                    used_ai = (row.get("ai_msg_basic", 0) >= 15 or row.get("ai_msg_premium", 0) >= 8)
                    if days_inactive >= 3 and used_ai and not is_prem:
                        await bot.send_message(uid,
                            "🎁 Мы скучали! +5 бесплатных AI сообщений специально для тебя!\n"
                            "Заходи общаться 💬",
                            reply_markup=kb_main()
                        )
                        async with db_pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE users SET ai_bonus = LEAST(ai_bonus + 5, 5), last_reminder = NOW() WHERE uid = $1",
                                uid
                            )
                    else:
                        # Обычное напоминание
                        template = random.choice(REMINDER_TEMPLATES)
                        text = template.format(n=max(online_count, 3), char=char_name)
                        await bot.send_message(uid, text, reply_markup=kb_main())
                        async with db_pool.acquire() as conn:
                            await conn.execute("UPDATE users SET last_reminder = NOW() WHERE uid = $1", uid)
                    sent += 1
                except Exception:
                    pass
            if sent:
                logger.info(f"Напоминания: отправлено {sent}")
        except Exception as e:
            logger.error(f"reminder_task error: {e}")

# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    moderation.init(bot, db_pool, ADMIN_ID)
    await moderation.migrate_db()
    await set_commands()
    asyncio.create_task(inactivity_checker())
    asyncio.create_task(reminder_task())
    logger.info("MatchMe запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
"""
MatchMe Channel Manager Bot
Управление каналом @MATCHMEHUB: авто-постинг, контент через Claude AI, админка.
Работает как отдельный сервис, подключён к общей PostgreSQL базе.
"""

import asyncio
import os
import aiohttp
import random
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
)
import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("matchme-channel")

# ====================== КОНФИГ ======================
CHANNEL_BOT_TOKEN = os.environ.get("CHANNEL_BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
VENICE_API_KEY = os.environ.get("VENICE_API_KEY")
CHANNEL_ID = "@MATCHMEHUB"
BOT_USERNAME = "MyMatchMeBot"  # username основного бота для CTA-ссылок

bot = Bot(token=CHANNEL_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db_pool = None

# Состояние
channel_poster_enabled = True  # переопределяется из bot_stats при старте
last_channel_post = {}
last_milestone_threshold = 0
channel_preview_cache = {}  # msg_id -> (rubric, text, poll_data)

# ====================== КОНСТАНТЫ ======================
MODE_NAMES = {"simple": "Просто общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}

CHANNEL_STYLE_PROMPT = (
    "Ты SMM-менеджер телеграм-канала MatchMe — анонимного чат-бота для знакомств. "
    "Пишешь как живой человек, НЕ как бот. ТОЛЬКО на русском.\n\n"
    "СТИЛЬ:\n"
    "- Короткие предложения. Максимум 3-4 строки основного текста\n"
    "- Один пост = одна мысль. Не перегружай информацией\n"
    "- Эмодзи уместно, но не больше 3-4 на весь пост\n"
    "- Пиши так, будто рассказываешь другу — живо, без канцелярита\n"
    "- НЕ используй: разделители (──, ✦, ┌, └), хештеги, длинные списки\n"
    "- В конце одна строка с ботом: @MyMatchMeBot\n\n"
    "ЗАПРЕЩЕНО:\n"
    "- Посты длиннее 500 символов\n"
    "- Шаблонные фразы: 'а ты знал что', 'лайфхак', 'топ-5'\n"
    "- Перечисления больше 3 пунктов\n"
    "- Восклицательные знаки подряд (!!!)"
)

CHANNEL_SCHEDULE = {
    12: ["dating_tip"],
    13: ["peak_hour"],
    15: ["joke"],
    18: ["poll"],
    19: ["weekly_recap"],
    20: ["peak_hour"],
    21: ["daily_stats"],
}

MILESTONE_THRESHOLDS = [50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]

POLL_BANK = [
    ("Что главное в первом сообщении?", ["Юмор 😄", "Комплимент 💐", "Вопрос ❓", "Просто 'Привет' 👋"]),
    ("Идеальное первое свидание?", ["Кофейня ☕", "Кино 🎬", "Прогулка 🚶", "Онлайн 💻"]),
    ("Сколько сообщений нужно чтобы понять — твой человек или нет?", ["1-5", "5-15", "15-50", "50+"]),
    ("Что бесит в анонимных чатах?", ["Молчание 🤐", "Грубость 😤", "Спам 📢", "Скука 😴"]),
    ("В какое время ты заходишь?", ["Утром ☀️", "Днём 🌤", "Вечером 🌙", "Ночью 🌚"]),
    ("Ты больше слушатель или рассказчик?", ["Слушатель 👂", "Рассказчик 🗣", "50/50 ⚖️"]),
    ("Что привлекает в собеседнике?", ["Юмор 😂", "Ум 🧠", "Голос 🎙", "Дерзость 😈"]),
    ("Какой режим тебе ближе?", ["Просто общение 💬", "Флирт 💋", "Kink 🔥", "Все по настроению 🎲"]),
]

# ====================== БАЗА ДАННЫХ ======================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Инициализация значений
        for k, v in [("online_pairs", 0), ("searching_count", 0),
                      ("channel_poster_enabled", 1), ("last_milestone_threshold", 0)]:
            await conn.execute(
                "INSERT INTO bot_stats (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", k, v
            )

async def get_stat(key, default=0):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM bot_stats WHERE key=$1", key)
        return row["value"] if row else default

async def set_stat(key, value):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bot_stats (key, value, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value=$2, updated_at=NOW()", key, value
        )

# ====================== CLAUDE API ======================
async def ask_claude_channel(system_prompt: str, user_prompt: str) -> str:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 300,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("content", [])
                    if content and len(content) > 0:
                        return content[0].get("text")
                    return None
                else:
                    logger.warning(f"Claude API error: status={resp.status}")
                    if resp.status in (401, 402, 429):
                        try:
                            await bot.send_message(ADMIN_ID,
                                f"⚠️ Claude API ошибка {resp.status}!\n"
                                f"{'Нет денег на балансе' if resp.status == 402 else 'Проблема с ключом' if resp.status == 401 else 'Превышен лимит запросов'}\n"
                                f"AI-контент канала временно недоступен.")
                        except Exception:
                            pass
    except Exception as e:
        logger.error(f"Claude API error: {e}")
    return None

# ====================== ГЕНЕРАТОРЫ КОНТЕНТА ======================
async def generate_daily_stats():
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '24 hours'")
            active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            genders = await conn.fetch("SELECT gender, COUNT(*) as cnt FROM users WHERE gender IS NOT NULL GROUP BY gender")
            modes = await conn.fetch("SELECT mode, COUNT(*) as cnt FROM users WHERE mode IS NOT NULL GROUP BY mode ORDER BY cnt DESC")
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
        g_map = {"male": "парней", "female": "девушек", "other": "other"}
        g_parts = [f"{r['cnt']} {g_map.get(r['gender'], r['gender'])}" for r in genders]
        m_parts = [f"{MODE_NAMES.get(r['mode'], r['mode'])}: {r['cnt']}" for r in modes]
        online = await get_stat("online_pairs", 0)
        searching = await get_stat("searching_count", 0)
        raw_data = (
            f"Всего юзеров: {total}, новых за 24ч: {new_today}, активных: {active}, "
            f"сейчас в чатах: {online} пар, ищут: {searching}, premium: {premiums}, "
            f"пол: {', '.join(g_parts)}, режимы: {', '.join(m_parts)}"
        )
        styled = await ask_claude_channel(
            CHANNEL_STYLE_PROMPT,
            f"Напиши короткий пост со статистикой MatchMe за день. "
            f"Данные: {raw_data}. "
            f"Выдели 2-3 самых интересных факта. Максимум 400 символов."
        )
        if styled:
            return styled
        return (
            f"Нас уже {total} 👥\n"
            f"+{new_today} новых за сегодня, {active} активных\n"
            f"Прямо сейчас: {online} пар в чатах, {searching} ищут\n\n"
            f"@{BOT_USERNAME}"
        )
    except Exception as e:
        logger.error(f"generate_daily_stats error: {e}")
        return None

async def generate_peak_hour():
    online = await get_stat("online_pairs", 0)
    searching = await get_stat("searching_count", 0)
    if online + searching < 1:
        return None
    styled = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        f"Сейчас в MatchMe {online} пар общаются, {searching} ищут собеседника. "
        f"Напиши 2-3 строки — зацепи, чтобы захотелось зайти. Максимум 200 символов."
    )
    if styled:
        return styled
    return (
        f"{online} пар сейчас болтают, {searching} ждут собеседника\n"
        f"Самое время зайти 👉 @{BOT_USERNAME}"
    )

async def generate_dating_tip():
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        "Один короткий совет про общение в анонимных чатах. "
        "Конкретный, полезный, без воды. Максимум 3 строки текста + пример. Максимум 350 символов."
    )
    if text:
        return text
    tips = [
        f"Не начинай с «привет, как дела». Задай вопрос, на который интересно ответить.\n\n@{BOT_USERNAME}",
        f"Первое впечатление — это первые 3 сообщения. Не трать их на «м/ж?»\n\n@{BOT_USERNAME}",
        f"Юмор работает лучше комплиментов. Рассмеши — и разговор пойдёт сам.\n\n@{BOT_USERNAME}",
    ]
    return random.choice(tips)

async def generate_joke():
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        "Короткая шутка или ироничное наблюдение про онлайн-знакомства и анонимные чаты. "
        "Формат: 1-3 строки, как пост друга в соцсети. Без натужного юмора. Максимум 250 символов."
    )
    if text:
        return text
    jokes = [
        f"Анонимный чат — единственное место, где «расскажи о себе» звучит как квест 🎮\n\n@{BOT_USERNAME}",
        f"Когда написал «привет» и ждёшь ответ как результат экзамена 😅\n\n@{BOT_USERNAME}",
        f"В анонимном чате каждый разговор — как первое свидание. Только без кофе ☕\n\n@{BOT_USERNAME}",
    ]
    return random.choice(jokes)

async def generate_poll():
    return random.choice(POLL_BANK)

async def generate_milestone():
    global last_milestone_threshold
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
        current = 0
        for t in MILESTONE_THRESHOLDS:
            if total >= t:
                current = t
        if current > last_milestone_threshold and last_milestone_threshold > 0:
            last_milestone_threshold = current
            await set_stat("last_milestone_threshold", current)
            styled = await ask_claude_channel(
                CHANNEL_STYLE_PROMPT,
                f"MatchMe достиг {current} пользователей (сейчас {total}). "
                f"Напиши короткий искренний пост-благодарность. 2-3 строки, без пафоса. Максимум 250 символов."
            )
            if styled:
                return styled
            return (
                f"Нас уже {current}+ ❤️\n"
                f"Спасибо, что вы с нами\n\n"
                f"@{BOT_USERNAME}"
            )
        last_milestone_threshold = current
    except Exception as e:
        logger.error(f"generate_milestone error: {e}")
    return None

async def generate_weekly_recap():
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'")
            active_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '7 days'")
            ages = await conn.fetch("""
                SELECT CASE WHEN age BETWEEN 16 AND 19 THEN '16-19'
                            WHEN age BETWEEN 20 AND 25 THEN '20-25'
                            WHEN age BETWEEN 26 AND 35 THEN '26-35'
                            ELSE '36+' END as bracket, COUNT(*) as cnt
                FROM users WHERE age IS NOT NULL GROUP BY bracket ORDER BY bracket
            """)
            top_mode = await conn.fetchrow("SELECT mode, COUNT(*) as cnt FROM users WHERE mode IS NOT NULL GROUP BY mode ORDER BY cnt DESC LIMIT 1")
        age_parts = [f"{r['bracket']}: {r['cnt']}" for r in ages]
        mode_text = MODE_NAMES.get(top_mode['mode'], '?') if top_mode else "—"
        raw_data = (
            f"Всего: {total}, новых за неделю: {new_week}, активных за неделю: {active_week}, "
            f"топ режим: {mode_text}, возрасты: {', '.join(age_parts)}"
        )
        styled = await ask_claude_channel(
            CHANNEL_STYLE_PROMPT,
            f"Итоги недели MatchMe. Данные: {raw_data}. "
            f"Выдели 2-3 ключевых момента, добавь короткий вывод. Максимум 400 символов."
        )
        if styled:
            return styled
        return (
            f"Итоги недели\n\n"
            f"Всего: {total}, новых: +{new_week}\n"
            f"Активных: {active_week}, топ режим: {mode_text}\n\n"
            f"@{BOT_USERNAME}"
        )
    except Exception as e:
        logger.error(f"generate_weekly_recap error: {e}")
        return None

CHANNEL_GENERATORS = {
    "daily_stats": generate_daily_stats,
    "peak_hour": generate_peak_hour,
    "dating_tip": generate_dating_tip,
    "joke": generate_joke,
    "weekly_recap": generate_weekly_recap,
}

# ====================== АВТО-ПОСТИНГ ======================
async def channel_poster():
    global last_milestone_threshold
    await asyncio.sleep(30)
    # Восстанавливаем состояние из БД
    try:
        last_milestone_threshold = await get_stat("last_milestone_threshold", 0)
        if last_milestone_threshold == 0:
            async with db_pool.acquire() as conn:
                total = await conn.fetchval("SELECT COUNT(*) FROM users")
            for t in MILESTONE_THRESHOLDS:
                if total >= t:
                    last_milestone_threshold = t
            await set_stat("last_milestone_threshold", last_milestone_threshold)
    except Exception:
        pass
    logger.info("Channel poster запущен")

    while True:
        await asyncio.sleep(600)

        # Проверяем включён ли постинг (из БД — персистентно)
        enabled = await get_stat("channel_poster_enabled", 1)
        if not enabled:
            continue

        now = datetime.now()
        hour = now.hour

        rubrics = CHANNEL_SCHEDULE.get(hour, [])
        for rubric in rubrics:
            last = last_channel_post.get(rubric)
            if last and (now - last).total_seconds() < 3600:
                continue
            if rubric == "poll" and now.day % 2 != 0:
                continue
            if rubric == "weekly_recap" and now.weekday() != 6:
                continue
            try:
                if rubric == "poll":
                    question, options = await generate_poll()
                    await bot.send_poll(CHANNEL_ID, question=question, options=options, is_anonymous=True)
                    last_channel_post[rubric] = now
                    logger.info(f"Channel poll posted: {question}")
                elif rubric in CHANNEL_GENERATORS:
                    text = await CHANNEL_GENERATORS[rubric]()
                    if text:
                        await bot.send_message(CHANNEL_ID, text)
                        last_channel_post[rubric] = now
                        logger.info(f"Channel post [{rubric}] sent")
            except Exception as e:
                logger.error(f"Channel poster error [{rubric}]: {e}")

        # Milestone
        try:
            milestone_text = await generate_milestone()
            if milestone_text:
                await bot.send_message(CHANNEL_ID, milestone_text)
                logger.info("Channel milestone posted")
        except Exception as e:
            logger.error(f"Channel milestone error: {e}")

# ====================== КОМАНДЫ БОТА ======================
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="post", description="Создать пост"),
        BotCommand(command="toggle", description="ВКЛ/ВЫКЛ авто-постинг"),
        BotCommand(command="status", description="Статус API"),
        BotCommand(command="stats", description="Статистика канала"),
        BotCommand(command="schedule", description="Расписание постов"),
    ])

# ====================== КЛАВИАТУРА АДМИНА ======================
def kb_admin():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Создать пост"), KeyboardButton(text="📢 Авто-постинг")],
        [KeyboardButton(text="🔌 Статус API"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📅 Расписание")],
    ], resize_keyboard=True)

def kb_post_types():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика дня", callback_data="chpost:daily_stats")],
        [InlineKeyboardButton(text="🔥 Пик активности", callback_data="chpost:peak_hour")],
        [InlineKeyboardButton(text="💡 Совет по общению", callback_data="chpost:dating_tip")],
        [InlineKeyboardButton(text="😂 Шутка / мем", callback_data="chpost:joke")],
        [InlineKeyboardButton(text="📋 Опрос", callback_data="chpost:poll")],
        [InlineKeyboardButton(text="📈 Итоги недели", callback_data="chpost:weekly_recap")],
    ])

# ====================== ОБРАБОТЧИКИ КОМАНД ======================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        enabled = await get_stat("channel_poster_enabled", 1)
        status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
        await message.answer(
            f"📢 MatchMe Channel Manager\n\n"
            f"Канал: {CHANNEL_ID}\n"
            f"Авто-постинг: {status}\n\n"
            f"Используй кнопки ниже или команды из меню.",
            reply_markup=kb_admin()
        )
    else:
        await message.answer(
            f"Этот бот управляет каналом {CHANNEL_ID}.\n"
            f"Для знакомств: @{BOT_USERNAME}",
            reply_markup=ReplyKeyboardRemove()
        )

@dp.message(Command("post"))
async def cmd_post(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📢 Выбери тип поста:", reply_markup=kb_post_types())

@dp.message(Command("toggle"))
async def cmd_toggle(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = await get_stat("channel_poster_enabled", 1)
    new_val = 0 if current else 1
    await set_stat("channel_poster_enabled", new_val)
    status = "✅ ВКЛ" if new_val else "❌ ВЫКЛ"
    await message.answer(f"📢 Авто-постинг: {status}")

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await check_api_status(message)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await show_channel_stats(message)

@dp.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    enabled = await get_stat("channel_poster_enabled", 1)
    status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
    schedule_text = (
        f"📅 Расписание авто-постинга ({status})\n\n"
        f"12:00 — 💡 Совет по общению\n"
        f"13:00 — 🔥 Пик активности\n"
        f"15:00 — 😂 Шутка / мем\n"
        f"18:00 — 📋 Опрос (через день)\n"
        f"19:00 — 📈 Итоги недели (воскресенье)\n"
        f"20:00 — 🔥 Пик активности\n"
        f"21:00 — 📊 Статистика дня\n\n"
        f"Milestone — при достижении порогов юзеров"
    )
    await message.answer(schedule_text)

# ====================== КНОПКИ REPLY ======================
@dp.message(F.text == "📝 Создать пост")
async def btn_post(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📢 Выбери тип поста:", reply_markup=kb_post_types())

@dp.message(F.text == "📢 Авто-постинг")
async def btn_toggle(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = await get_stat("channel_poster_enabled", 1)
    new_val = 0 if current else 1
    await set_stat("channel_poster_enabled", new_val)
    status = "✅ ВКЛ" if new_val else "❌ ВЫКЛ"
    await message.answer(f"📢 Авто-постинг: {status}")

@dp.message(F.text == "🔌 Статус API")
async def btn_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await check_api_status(message)

@dp.message(F.text == "📊 Статистика")
async def btn_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await show_channel_stats(message)

@dp.message(F.text == "📅 Расписание")
async def btn_schedule(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await cmd_schedule(message)

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
async def check_api_status(message: types.Message):
    await message.answer("⏳ Проверяю API...")
    results = []
    # Claude API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY or "",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 10,
                      "messages": [{"role": "user", "content": "Hi"}]},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    results.append("🟢 Claude API — активен ✅")
                elif resp.status == 401:
                    results.append("🔴 Claude API — неверный ключ ❌")
                elif resp.status == 402:
                    results.append("🔴 Claude API — нет средств 💰")
                elif resp.status == 429:
                    results.append("🟡 Claude API — лимит (но работает)")
                else:
                    results.append(f"🟡 Claude API — ошибка {resp.status}")
    except Exception as e:
        results.append(f"🔴 Claude API — недоступен ({e})")
    # Venice API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.venice.ai/api/v1/models",
                headers={"Authorization": f"Bearer {VENICE_API_KEY or ''}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    balance_usd = resp.headers.get("x-venice-balance-usd", "?")
                    results.append(f"🟢 Venice API — активен ✅\n   💰 Баланс: ${balance_usd}")
                elif resp.status == 401:
                    results.append("🔴 Venice API — неверный ключ ❌")
                else:
                    results.append(f"🟡 Venice API — ошибка {resp.status}")
    except Exception as e:
        results.append(f"🔴 Venice API — недоступен ({e})")
    # PostgreSQL
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        results.append("🟢 PostgreSQL — активна ✅")
    except Exception:
        results.append("🔴 PostgreSQL — недоступна ❌")
    await message.answer("🔌 Статус сервисов\n\n" + "\n".join(results))

async def show_channel_stats(message: types.Message):
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '24 hours'")
            active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
        online = await get_stat("online_pairs", 0)
        searching = await get_stat("searching_count", 0)
        enabled = await get_stat("channel_poster_enabled", 1)
        poster_status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
        await message.answer(
            f"📊 Статистика MatchMe\n\n"
            f"👥 Всего: {total}\n"
            f"🆕 Новых за 24ч: +{new_today}\n"
            f"🟢 Активных: {active}\n"
            f"💬 В чатах: {online} пар\n"
            f"🔍 Ищут: {searching}\n"
            f"⭐ Premium: {premiums}\n\n"
            f"📢 Авто-постинг: {poster_status}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ====================== INLINE CALLBACK ======================
@dp.callback_query(F.data.startswith("chpost:"))
async def admin_channel_post(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rubric = callback.data.split(":", 1)[1]
    await callback.message.answer("⏳ Генерирую...")
    try:
        text = None
        poll_data = None
        if rubric == "poll":
            poll_data = await generate_poll()
            question, options = poll_data
            text = f"📋 Опрос: {question}\n" + "\n".join(f"  • {o}" for o in options)
        elif rubric in CHANNEL_GENERATORS:
            text = await CHANNEL_GENERATORS[rubric]()
        if not text:
            await callback.message.answer("❌ Не удалось сгенерировать контент.")
            await callback.answer()
            return
        preview_msg = await callback.message.answer(
            f"👁 Предпросмотр:\n\n{text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Отправить в канал", callback_data=f"chsend:{rubric}")],
                [InlineKeyboardButton(text="🔄 Другой вариант", callback_data=f"chpost:{rubric}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="chdismiss")],
            ])
        )
        channel_preview_cache[preview_msg.message_id] = (rubric, text, poll_data)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")
    await callback.answer()

@dp.callback_query(F.data.startswith("chsend:"))
async def admin_channel_send(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    cached = channel_preview_cache.pop(callback.message.message_id, None)
    if not cached:
        await callback.answer("Контент устарел, сгенерируй заново.", show_alert=True)
        return
    rubric, text, poll_data = cached
    try:
        if poll_data:
            question, options = poll_data
            await bot.send_poll(CHANNEL_ID, question=question, options=options, is_anonymous=True)
        else:
            await bot.send_message(CHANNEL_ID, text)
        last_channel_post[rubric] = datetime.now()
        try:
            await callback.message.edit_text(f"✅ Опубликовано в {CHANNEL_ID}!")
        except Exception:
            pass
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка отправки: {e}")
    await callback.answer()

@dp.callback_query(F.data == "chdismiss")
async def admin_channel_dismiss(callback: types.CallbackQuery):
    channel_preview_cache.pop(callback.message.message_id, None)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    await set_commands()
    asyncio.create_task(channel_poster())
    logger.info("MatchMe Channel Manager запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
"""
AI-модерация для MatchMe бота.
Анализирует жалобы и сообщения через Claude API.
Ведёт аудит-лог всех решений.
"""

import os
import json
import logging
import aiohttp
from datetime import datetime, timedelta

logger = logging.getLogger("matchme.moderation")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Зависимости — инициализируются из bot.py
_bot = None
_db_pool = None
_admin_id = None

# Жёсткий бан — ЦП и несовершеннолетние (keyword-based, без AI)
HARD_BAN_WORDS = [
    "мне 12", "мне 13", "мне 14", "мне 15",
    "школьница ищу", "школьник ищу", "порно за деньги",
    "детское порно", "цп продаю", "малолетка",
]

# Подозрительные слова — триггер для AI-проверки (НЕ авто-бан)
SUSPECT_WORDS = [
    "предлагаю услуги", "оказываю услуги", "интим услуги",
    "escort", "эскорт", "проститутка",
    "вирт за деньги", "вирт платно", "за донат",
    "подпишись на канал", "перейди по ссылке", "мой канал",
    "казино", "ставки на спорт", "заработок в телеграм",
    "крипта х10", "пассивный доход", "продаю фото", "продаю видео",
    "продаю интим", "купи подписку", "пиши в лс за", "скидка на услуги",
]

MODERATION_SYSTEM_PROMPT = (
    "Ты модератор анонимного чат-бота для знакомств MatchMe. "
    "Анализируй переписку и принимай решение по жалобе.\n\n"
    "ПРАВИЛА:\n"
    "- Несовершеннолетние (упоминание возраста <18, поиск школьников) → ban_perm\n"
    "- Продажа интим-услуг, эскорт, платные услуги → shadow_ban\n"
    "- Спам, реклама каналов, крипто-схемы, финансовые пирамиды → shadow_ban\n"
    "- Угрозы физической расправой, преследование → ban_perm\n"
    "- Тяжёлые оскорбления, буллинг → ban_24h\n"
    "- Пошлый контент без согласия собеседника → warn или ban_3h\n"
    "- Ложная жалоба (ничего не нарушено) → dismiss\n"
    "- Неясная ситуация, недостаточно контекста → escalate\n\n"
    "УЧИТЫВАЙ:\n"
    "- Историю пользователя (предупреждения, прошлые жалобы)\n"
    "- Контекст переписки (шутка, взаимное согласие, провокация)\n"
    "- Тяжесть нарушения и повторность\n"
    "- Если у пользователя уже были предупреждения — ужесточай наказание\n\n"
    "SHADOW BAN:\n"
    "- Теневая блокировка — пользователь НЕ ЗНАЕТ что забанен\n"
    "- Используй для спамеров, рекламщиков, продавцов\n\n"
    "ОТВЕТ строго в JSON формате:\n"
    '{"decision": "warn|ban_3h|ban_24h|ban_perm|shadow_ban|escalate|dismiss", '
    '"confidence": 0.0-1.0, '
    '"reason_short": "краткая причина для уведомления пользователя (1 предложение)", '
    '"reason_detailed": "подробный анализ для аудит-лога (2-3 предложения)", '
    '"notify_user": true/false}\n\n'
    "notify_user=false ТОЛЬКО для shadow_ban и dismiss. Для остальных всегда true."
)

MESSAGE_CHECK_PROMPT = (
    "Ты модератор чата знакомств. Проверь сообщение на нарушения.\n"
    "Нарушения: продажа услуг, реклама, спам, мошенничество.\n"
    "Если нарушение есть — ответь JSON: {\"violation\": true, \"type\": \"shadow_ban\", \"reason\": \"причина\"}\n"
    "Если нет — ответь: {\"violation\": false}\n"
    "Отвечай ТОЛЬКО JSON, без пояснений."
)


def init(bot_instance, pool, admin_id):
    """Инициализация модуля — вызывается из bot.py"""
    global _bot, _db_pool, _admin_id
    _bot = bot_instance
    _db_pool = pool
    _admin_id = admin_id


async def migrate_db():
    """Добавляет новые колонки в complaints_log для AI-модерации"""
    if not _db_pool:
        return
    async with _db_pool.acquire() as conn:
        for col, definition in [
            ("decided_by", "TEXT DEFAULT 'pending'"),
            ("ai_reasoning", "TEXT DEFAULT NULL"),
            ("ai_confidence", "REAL DEFAULT NULL"),
            ("decision_details", "TEXT DEFAULT NULL"),
        ]:
            try:
                await conn.execute(
                    f"ALTER TABLE complaints_log ADD COLUMN IF NOT EXISTS {col} {definition}"
                )
            except Exception:
                pass


# ====================== CLAUDE API ======================

async def _ask_claude(system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-6", max_tokens: int = 400) -> str | None:
    """Универсальный вызов Claude API"""
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY не задан")
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("content", [])
                    if content and isinstance(content, list) and len(content) > 0:
                        return content[0].get("text")
                    logger.warning("Claude API: empty content in response")
                    return None
                else:
                    body = await resp.text()
                    logger.error(f"Claude API error: {resp.status} — {body[:200]}")
                    return None
    except Exception as e:
        logger.error(f"Claude API exception: {e}")
        return None


def _parse_json_response(text: str) -> dict | None:
    """Парсит JSON из ответа Claude (убирает markdown обёртку если есть)"""
    if not text:
        return None
    text = text.strip()
    # Убираем ```json ... ``` обёртку
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Попробуем найти JSON внутри текста
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        logger.error(f"Failed to parse AI response: {text[:200]}")
        return None


# ====================== AI-МОДЕРАЦИЯ ЖАЛОБ ======================

async def ai_review_complaint(complaint_id: int) -> dict | None:
    """
    AI анализирует жалобу и принимает решение.
    Возвращает dict с решением или None при ошибке (fallback на ручную модерацию).
    """
    if not _db_pool or not _bot:
        return None

    # Загружаем жалобу
    async with _db_pool.acquire() as conn:
        complaint = await conn.fetchrow(
            "SELECT * FROM complaints_log WHERE id=$1", complaint_id
        )
    if not complaint:
        return None

    accused_uid = complaint["to_uid"]
    reporter_uid = complaint["from_uid"]
    chat_log = complaint.get("chat_log", "")
    reason = complaint.get("reason", "")

    # История обвиняемого
    async with _db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", accused_uid)
        prev_complaints = await conn.fetch(
            "SELECT reason, admin_action, decided_by, ai_reasoning FROM complaints_log "
            "WHERE to_uid=$1 AND reviewed=TRUE ORDER BY created_at DESC LIMIT 5",
            accused_uid,
        )

    warn_count = user.get("warn_count", 0) if user else 0
    total_complaints = user.get("complaints", 0) if user else 0
    is_shadow = user.get("shadow_ban", False) if user else False

    history_text = f"Предупреждений: {warn_count}, Жалоб всего: {total_complaints}"
    if is_shadow:
        history_text += ", УЖЕ в shadow ban"
    if prev_complaints:
        history_text += "\nПоследние решения: " + "; ".join(
            f"{r.get('admin_action', r.get('ai_reasoning', '?'))}" for r in prev_complaints
        )

    user_prompt = (
        f"ЖАЛОБА #{complaint_id}\n"
        f"Причина: {reason}\n\n"
        f"ИСТОРИЯ ОБВИНЯЕМОГО:\n{history_text}\n\n"
        f"ПЕРЕПИСКА:\n{chat_log[:2000]}"
    )

    # Вызов AI
    raw = await _ask_claude(MODERATION_SYSTEM_PROMPT, user_prompt)
    result = _parse_json_response(raw)

    if not result or "decision" not in result:
        logger.warning(f"AI moderation failed for complaint #{complaint_id}, falling back to admin")
        return None

    decision = result["decision"]
    confidence = float(result.get("confidence", 0.5))
    reason_short = result.get("reason_short", "Нарушение правил")
    reason_detailed = result.get("reason_detailed", "")
    notify_user = result.get("notify_user", True)

    # Если уверенность низкая — эскалируем админу
    # Для перманентного бана требуем повышенную уверенность (85%)
    min_confidence = 0.85 if decision == "ban_perm" else 0.7
    if confidence < min_confidence or decision == "escalate":
        await _escalate_to_admin(complaint_id, complaint, result)
        return result

    # Применяем решение
    await _apply_decision(
        complaint_id, accused_uid, reporter_uid,
        decision, reason_short, reason_detailed, confidence, notify_user
    )
    return result


async def _escalate_to_admin(complaint_id: int, complaint: dict, ai_result: dict):
    """Эскалация админу с рекомендацией AI"""
    async with _db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE complaints_log SET decided_by='pending', ai_reasoning=$1, ai_confidence=$2 WHERE id=$3",
            ai_result.get("reason_detailed", ""),
            float(ai_result.get("confidence", 0)),
            complaint_id,
        )

    decision_map = {
        "warn": "Предупреждение", "ban_3h": "Бан 3ч", "ban_24h": "Бан 24ч",
        "ban_perm": "Перм бан", "shadow_ban": "Shadow ban",
        "escalate": "Не уверен", "dismiss": "Отклонить",
    }
    ai_decision = decision_map.get(ai_result.get("decision", ""), "?")
    confidence = ai_result.get("confidence", 0)

    try:
        await _bot.send_message(
            _admin_id,
            f"🤖 AI не уверен — нужно твоё решение\n\n"
            f"🚩 Жалоба #{complaint_id}\n"
            f"📋 Причина: {complaint.get('reason', '?')}\n"
            f"🤖 Рекомендация AI: {ai_decision} ({confidence:.0%})\n"
            f"💬 {ai_result.get('reason_detailed', '')}\n\n"
            f"👤 На: {complaint['to_uid']} | От: {complaint['from_uid']}"
        )
    except Exception as e:
        logger.error(f"Failed to escalate to admin: {e}")


async def _apply_decision(
    complaint_id: int, accused_uid: int, reporter_uid: int,
    decision: str, reason_short: str, reason_detailed: str,
    confidence: float, notify_user: bool,
):
    """Применяет решение AI и обновляет БД"""

    action_text = {
        "warn": "Предупреждение (AI)",
        "ban_3h": "Бан 3ч (AI)",
        "ban_24h": "Бан 24ч (AI)",
        "ban_perm": "Перм бан (AI)",
        "shadow_ban": "Shadow ban (AI)",
        "dismiss": "Отклонена (AI)",
    }.get(decision, decision)

    # Обновляем жалобу
    async with _db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE complaints_log SET reviewed=TRUE, admin_action=$1, decided_by='ai', "
            "ai_reasoning=$2, ai_confidence=$3, decision_details=$4 WHERE id=$5",
            action_text, reason_short, confidence, reason_detailed, complaint_id,
        )

    # Применяем наказание
    if decision == "warn":
        async with _db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET warn_count=warn_count+1 WHERE uid=$1", accused_uid
            )
        if notify_user:
            try:
                await _bot.send_message(
                    accused_uid,
                    f"⚠️ Предупреждение: {reason_short}\n"
                    f"Следующее нарушение приведёт к бану."
                )
            except Exception:
                pass

    elif decision == "ban_3h":
        until = (datetime.now() + timedelta(hours=3)).isoformat()
        async with _db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, accused_uid)
        if notify_user:
            try:
                await _bot.send_message(accused_uid, f"🚫 Бан на 3 часа: {reason_short}")
            except Exception:
                pass

    elif decision == "ban_24h":
        until = (datetime.now() + timedelta(hours=24)).isoformat()
        async with _db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, accused_uid)
        if notify_user:
            try:
                await _bot.send_message(accused_uid, f"🚫 Бан на 24 часа: {reason_short}")
            except Exception:
                pass

    elif decision == "ban_perm":
        async with _db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until='permanent' WHERE uid=$1", accused_uid)
        if notify_user:
            try:
                await _bot.send_message(accused_uid, f"🚫 Перманентный бан: {reason_short}")
            except Exception:
                pass

    elif decision == "shadow_ban":
        async with _db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET shadow_ban=TRUE WHERE uid=$1", accused_uid)
        # Shadow ban — НИКОГДА не уведомляем пользователя

    elif decision == "dismiss":
        pass  # Ничего не делаем, жалоба просто отклонена

    # Уведомляем админа о принятом решении
    try:
        await _bot.send_message(
            _admin_id,
            f"🤖 AI решение по жалобе #{complaint_id}:\n"
            f"{action_text} ({confidence:.0%})\n"
            f"💬 {reason_detailed}"
        )
    except Exception:
        pass


# ====================== ПРОВЕРКА СООБЩЕНИЙ В РЕАЛЬНОМ ВРЕМЕНИ ======================

async def check_message(text: str, uid: int) -> dict | None:
    """
    Проверяет сообщение на нарушения.
    HARD_BAN_WORDS — всегда keyword-based (нулевая толерантность).
    SUSPECT_WORDS — keyword триггер → AI-анализ для подтверждения.
    Обычные сообщения НЕ отправляются в AI (экономия API и латенси).
    Возвращает: {"action": "hard_ban|shadow_ban", "reason": "..."} или None
    """
    txt_lower = text.lower()

    # 1. HARD BAN — keyword matching (CP/minors, без AI, мгновенно)
    hard_match = [w for w in HARD_BAN_WORDS if w in txt_lower]
    if hard_match:
        return {"action": "hard_ban", "reason": f"Запрещённый контент: {', '.join(hard_match)}"}

    # 2. Проверяем наличие подозрительных слов (keyword pre-filter)
    suspect_match = [w for w in SUSPECT_WORDS if w in txt_lower]
    if not suspect_match:
        return None  # Обычное сообщение — пропускаем без AI

    # 3. Подозрительные слова найдены — AI подтверждает (только для подозрительных)
    if not ANTHROPIC_API_KEY:
        # Fallback без AI: shadow ban по keyword (как раньше)
        return {"action": "shadow_ban", "reason": f"Подозрительный контент: {', '.join(suspect_match[:3])}"}

    raw = await _ask_claude(
        MESSAGE_CHECK_PROMPT,
        f"Сообщение: {text[:500]}\nНайденные подозрительные слова: {', '.join(suspect_match)}",
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
    )
    result = _parse_json_response(raw)
    if result and result.get("violation"):
        return {
            "action": result.get("type", "shadow_ban"),
            "reason": result.get("reason", "Нарушение правил"),
        }

    return None


# ====================== АУДИТ-ЛОГ ======================

async def get_audit_log(limit: int = 10, offset: int = 0) -> list:
    """Возвращает список решений по жалобам для аудит-лога"""
    if not _db_pool:
        return []
    async with _db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, to_uid, from_uid, reason, admin_action, decided_by, "
            "ai_reasoning, ai_confidence, decision_details, created_at "
            "FROM complaints_log WHERE reviewed=TRUE "
            "ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
    return [dict(r) for r in rows]


async def get_audit_total() -> int:
    """Общее число решений в аудит-логе"""
    if not _db_pool:
        return 0
    async with _db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=TRUE")


async def get_decision_detail(complaint_id: int) -> dict | None:
    """Полная информация о решении для аудит-лога"""
    if not _db_pool:
        return None
    async with _db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM complaints_log WHERE id=$1", complaint_id
        )
    return dict(row) if row else None


def format_audit_entry(entry: dict) -> str:
    """Форматирует запись аудит-лога для отображения"""
    decided = entry.get("decided_by", "?")
    icon = "🤖" if decided == "ai" else "👤" if decided == "admin" else "⚙️"
    action = entry.get("admin_action", "?")
    date = entry["created_at"].strftime("%d.%m %H:%M") if entry.get("created_at") else "?"
    confidence = entry.get("ai_confidence")
    conf_text = f" ({confidence:.0%})" if confidence is not None else ""

    return (
        f"{icon} #{entry.get('id', '?')} | {action}{conf_text}\n"
        f"   На: {entry.get('to_uid', '?')} | Причина: {entry.get('reason', '?')}\n"
        f"   {date}"
    )


def format_decision_detail(entry: dict) -> str:
    """Форматирует полную детализацию решения"""
    decided = entry.get("decided_by", "?")
    icon = "🤖" if decided == "ai" else "👤" if decided == "admin" else "⚙️"
    confidence = entry.get("ai_confidence")

    lines = [
        f"{icon} Жалоба #{entry['id']}",
        f"",
        f"👤 Обвиняемый: {entry['to_uid']}",
        f"👤 Жалобщик: {entry['from_uid']}",
        f"📋 Причина жалобы: {entry.get('reason', '?')}",
        f"",
        f"Решение: {entry.get('admin_action', '?')}",
        f"Принял: {'AI' if decided == 'ai' else 'Админ' if decided == 'admin' else 'Авто'}",
    ]
    if confidence is not None:
        lines.append(f"Уверенность AI: {confidence:.0%}")
    if entry.get("ai_reasoning"):
        lines.append(f"\n💬 AI: {entry['ai_reasoning']}")
    if entry.get("decision_details"):
        lines.append(f"📝 Детали: {entry['decision_details']}")
    chat_log = entry.get("chat_log") or ""
    if chat_log:
        lines.append(f"\n📄 Переписка:\n{chat_log[:300]}")

    date = entry["created_at"].strftime("%d.%m.%Y %H:%M") if entry.get("created_at") else "?"
    lines.append(f"\n🕐 {date}")

    return "\n".join(lines)
