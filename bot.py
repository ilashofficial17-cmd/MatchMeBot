import asyncio
import os
import aiohttp
import random
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand,
    LabeledPrice, PreCheckoutQuery
)
import asyncpg
import moderation
from states import (Reg, Chat, Rules, Complaint, EditProfile,
                    AdminState, ResetProfile, AIChat)
from keyboards import (
    CHANNEL_ID, WELCOME_TEXT, PRIVACY_TEXT, RULES_RU, RULES_PROFILE,
    MODE_NAMES, INTERESTS_MAP,
    kb_main, kb_lang, kb_privacy, kb_rules, kb_rules_profile, kb_cancel_reg,
    kb_gender, kb_mode, kb_cancel_search, kb_chat, kb_search_gender,
    kb_after_chat, kb_channel_bonus, kb_ai_characters, kb_ai_chat,
    kb_interests, kb_complaint, kb_edit, kb_complaint_action,
    kb_user_actions, kb_premium,
)
import ai_chat
import admin as admin_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("matchme")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))

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

# ====================== КЛАВИАТУРЫ ======================
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

@dp.callback_query(F.data == "noop", StateFilter("*"))
async def noop(callback: types.CallbackQuery):
    await callback.answer()

# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    moderation.init(bot, db_pool, ADMIN_ID)
    await moderation.migrate_db()
    await set_commands()
    ai_chat.init(
        bot=bot,
        ai_sessions=ai_sessions,
        last_ai_msg=last_ai_msg,
        pairing_lock=pairing_lock,
        get_all_queues=get_all_queues,
        active_chats=active_chats,
        get_user=get_user,
        ensure_user=ensure_user,
        get_premium_tier=get_premium_tier,
        update_user=update_user,
        cmd_find=cmd_find,
        show_settings=show_settings,
    )
    admin_module.init(
        bot=bot,
        dp=dp,
        db_pool=db_pool,
        admin_id=ADMIN_ID,
        active_chats=active_chats,
        ai_sessions=ai_sessions,
        last_ai_msg=last_ai_msg,
        pairing_lock=pairing_lock,
        get_all_queues=get_all_queues,
        chat_logs=chat_logs,
        last_msg_time=last_msg_time,
        msg_count=msg_count,
        mutual_likes=mutual_likes,
        clear_chat_log=clear_chat_log,
        get_user=get_user,
        update_user=update_user,
        increment_user=increment_user,
        get_rating=get_rating,
        remove_chat_from_db=remove_chat_from_db,
        AI_CHARACTERS=ai_chat.AI_CHARACTERS,
    )
    dp.include_router(ai_chat.router)
    dp.include_router(admin_module.router)
    asyncio.create_task(admin_module.inactivity_checker())
    asyncio.create_task(admin_module.reminder_task())
    logger.info("MatchMe запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
