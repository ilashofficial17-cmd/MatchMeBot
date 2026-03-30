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
from ai_utils import get_ai_answer  # подготовка для AI-персонажей на OpenRouter
from states import (Reg, Chat, LangSelect, Rules, Complaint, EditProfile,
                    AdminState, ResetProfile, AIChat)
from locales import t, LANG_BUTTONS, TEXTS
from keyboards import (
    CHANNEL_ID, INTERESTS_MAP,
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
    "7d":      {"stars": 99,  "days": 7,  "label_key": "plan_label_7d",    "desc_key": "plan_desc_try",          "tier": "premium"},
    "1m":      {"stars": 299, "days": 30, "label_key": "plan_label_1m",    "desc_key": "plan_desc_popular",      "tier": "premium"},
    "3m":      {"stars": 599, "days": 90, "label_key": "plan_label_3m",    "desc_key": "plan_desc_discount",     "tier": "premium"},
    # Premium Plus — всё безлимит
    "plus_1m": {"stars": 499, "days": 30, "label_key": "plan_label_plus_1m", "desc_key": "plan_desc_ai_unlimited", "tier": "plus"},
    "plus_3m": {"stars": 999, "days": 90, "label_key": "plan_label_plus_3m", "desc_key": "plan_desc_best_price",   "tier": "plus"},
    # AI Pro — отдельная подписка, разблокирует всё как Plus
    "ai_1m":   {"stars": 399, "days": 30, "label_key": "plan_label_ai_1m", "desc_key": "plan_desc_powerful_ai",  "tier": "ai_pro"},
    "ai_3m":   {"stars": 799, "days": 90, "label_key": "plan_label_ai_3m", "desc_key": "plan_desc_ai_discount",  "tier": "ai_pro"},
}


def get_chat_topics(lang: str) -> list:
    return TEXTS.get(lang, TEXTS["ru"]).get("chat_topics", TEXTS["ru"]["chat_topics"])

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
liked_chats = set()  # (uid, chat_key) — защита от спама лайков


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
                lang TEXT DEFAULT NULL,
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

    await _migrate_interests()
    await restore_chats()

async def _migrate_interests():
    """One-time migration: convert old Russian interest strings to locale keys."""
    OLD_TO_NEW = {
        "Разговор по душам 🗣": "int_talk",
        "Юмор и мемы 😂":       "int_humor",
        "Советы по жизни 💡":    "int_advice",
        "Музыка 🎵":             "int_music",
        "Игры 🎮":               "int_games",
        "Лёгкий флирт 😏":       "int_flirt_light",
        "Комплименты 💌":         "int_compliments",
        "Секстинг 🔥":            "int_sexting",
        "Виртуальные свидания 💑": "int_virtual_date",
        "Флирт и игры 🎭":        "int_flirt_games",
        "BDSM 🖤":               "int_bdsm",
        "Bondage 🔗":            "int_bondage",
        "Roleplay 🎭":           "int_roleplay",
        "Dom/Sub ⛓":            "int_domsub",
        "Pet play 🐾":           "int_petplay",
        "Другой фетиш ✨":        "int_other_fetish",
    }
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT uid, interests FROM users WHERE interests IS NOT NULL AND interests != ''"
        )
        updated = 0
        for row in rows:
            parts = [p.strip() for p in row["interests"].split(",") if p.strip()]
            if all(p.startswith("int_") for p in parts):
                continue  # already migrated
            new_parts = [OLD_TO_NEW.get(p, p) for p in parts]
            new_val = ",".join(new_parts)
            await conn.execute("UPDATE users SET interests=$1 WHERE uid=$2", new_val, row["uid"])
            updated += 1
    if updated:
        logger.info(f"Migrated interests for {updated} users")

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
            u1 = await get_user(uid1)
            u2 = await get_user(uid2)
            lang1 = (u1.get("lang") or "ru") if u1 else "ru"
            lang2 = (u2.get("lang") or "ru") if u2 else "ru"
            await bot.send_message(uid1, t(lang1, "bot_restarted"), reply_markup=kb_chat(lang1))
            await bot.send_message(uid2, t(lang2, "bot_restarted"), reply_markup=kb_chat(lang2))
        except Exception: pass
    if restored:
        logger.info(f"Восстановлено {restored} чатов")

async def get_user(uid):
    if not db_pool:
        return None
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
        return dict(row) if row else None

async def get_lang(uid) -> str:
    u = await get_user(uid)
    return (u.get("lang") or "ru") if u else "ru"

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
                "INSERT INTO active_chats_db (uid1, uid2, chat_type) VALUES ($1,$2,$3) ON CONFLICT (uid1) DO UPDATE SET uid2=$2, chat_type=$3",
                uid1, uid2, chat_type
            )
            await conn.execute(
                "INSERT INTO active_chats_db (uid1, uid2, chat_type) VALUES ($1,$2,$3) ON CONFLICT (uid1) DO UPDATE SET uid2=$2, chat_type=$3",
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
def get_age_joke(age, lang="ru"):
    if age <= 6: key = "age_joke_baby"
    elif age <= 12: key = "age_joke_child"
    elif age <= 15: key = "age_joke_teen_young"
    elif age <= 17: key = "age_joke_teen"
    elif age <= 25: key = "age_joke_young"
    elif age <= 35: key = "age_joke_adult"
    elif age <= 50: key = "age_joke_middle"
    elif age <= 70: key = "age_joke_senior"
    elif age <= 90: key = "age_joke_elder"
    else: key = "age_joke_ancient"
    return t(lang, key)

# ====================== КЛАВИАТУРЫ ======================
async def kb_settings(uid, lang="ru"):
    u = await get_user(uid)
    if not u: return InlineKeyboardMarkup(inline_keyboard=[])
    user_premium = await is_premium(uid)
    mode = u.get("mode", "simple")
    age_min = u.get("search_age_min", 16) or 16
    age_max = u.get("search_age_max", 99) or 99
    age_label = t(lang, "settings_age_any") if (age_min == 16 and age_max == 99) else t(lang, "settings_age_range", min=age_min, max=age_max)
    sg_key_map = {"any": "settings_gender_any", "male": "settings_gender_male", "female": "settings_gender_female", "other": "settings_gender_other"}
    sg = t(lang, sg_key_map.get(u.get("search_gender", "any"), "settings_gender_any"))
    show_p = u.get("show_premium", True)
    cross = u.get("accept_cross_mode", False)

    buttons = []

    buttons.append([InlineKeyboardButton(
        text=t(lang, "settings_mode_label", mode=t(lang, f"mode_{mode}")),
        callback_data="noop"
    )])

    if mode == "flirt":
        buttons.append([InlineKeyboardButton(
            text=f"{'✅' if cross else '❌'} {t(lang, 'settings_cross_kink')}",
            callback_data="set:cross"
        )])
    elif mode == "kink":
        buttons.append([InlineKeyboardButton(
            text=f"{'✅' if cross else '❌'} {t(lang, 'settings_cross_flirt')}",
            callback_data="set:cross"
        )])
    elif mode == "simple":
        buttons.append([InlineKeyboardButton(
            text=t(lang, "settings_simple_only"),
            callback_data="noop"
        )])

    if mode == "simple" or user_premium:
        buttons.append([InlineKeyboardButton(text=t(lang, "settings_find_gender", gender=sg), callback_data="set:gender")])
    else:
        buttons.append([InlineKeyboardButton(text=t(lang, "settings_find_gender_premium", gender=sg), callback_data="set:gender_locked")])

    buttons.append([InlineKeyboardButton(text=age_label, callback_data="noop")])
    age_any_label = t(lang, "settings_age_any").lstrip("✅ ")
    buttons.append([
        InlineKeyboardButton(text="✅ 16-20" if (age_min==16 and age_max==20) else "16-20", callback_data="set:age:16:20"),
        InlineKeyboardButton(text="✅ 21-30" if (age_min==21 and age_max==30) else "21-30", callback_data="set:age:21:30"),
        InlineKeyboardButton(text="✅ 31-45" if (age_min==31 and age_max==45) else "31-45", callback_data="set:age:31:45"),
        InlineKeyboardButton(text=f"✅ {age_any_label}" if (age_min==16 and age_max==99) else age_any_label, callback_data="set:age:16:99"),
    ])

    buttons.append([InlineKeyboardButton(
        text=f"{'✅' if show_p else '❌'} {t(lang, 'settings_show_badge')}",
        callback_data="set:show_premium"
    )])

    if user_premium:
        p_until = u.get("premium_until", "")
        if p_until == "permanent" or uid == ADMIN_ID:
            p_text = t(lang, "premium_eternal", tier="⭐ Premium")
        else:
            try:
                p_date = datetime.fromisoformat(p_until)
                days_left = (p_date - datetime.now()).days
                p_text = f"⭐ Premium {t(lang, 'premium_until_date', tier='', until=p_date.strftime('%d.%m.%Y')).strip()} ({days_left}d)"
            except Exception:
                p_text = t(lang, "premium_active")
        buttons.append([InlineKeyboardButton(text=p_text, callback_data="noop")])
    else:
        buttons.append([InlineKeyboardButton(text=t(lang, "settings_buy_premium"), callback_data="buy:1m")])

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
    return waiting_simple

def get_rating(u):
    return u.get("likes", 0) - u.get("dislikes", 0)

async def cleanup(uid, state=None):
    async with pairing_lock:
        for q in get_all_queues():
            q.discard(uid)
        partner = active_chats.pop(uid, None)
        if partner:
            active_chats.pop(partner, None)
    if partner:
        await remove_chat_from_db(uid, partner)
        clear_chat_log(uid, partner)
        # Cleanup liked_chats for this chat
        chat_key = get_chat_key(uid, partner)
        liked_chats.discard((uid, chat_key))
        liked_chats.discard((partner, chat_key))
    ai_sessions.pop(uid, None)
    if state: await state.clear()
    return partner

def _all(key):
    """All language variants for a locale key — for F.text.in_() filters."""
    return {TEXTS[lang][key] for lang in TEXTS if key in TEXTS[lang]}

async def unavailable(message: types.Message, lang: str, reason_key: str):
    await message.answer(t(lang, "unavailable", reason=t(lang, reason_key)))

async def needs_onboarding(message: types.Message, state: FSMContext) -> bool:
    """If user has no lang set, redirect to language selection. Returns True if redirected."""
    uid = message.from_user.id
    await ensure_user(uid)
    u = await get_user(uid)
    if not u or not u.get("lang"):
        await state.set_state(LangSelect.choosing)
        await message.answer(t("ru", "welcome"), reply_markup=kb_lang())
        return True
    return False

async def get_pending_complaints():
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE") or 0

async def set_commands():
    # Default commands (Russian)
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
    # English commands
    await bot.set_my_commands([
        BotCommand(command="start", description="Start / restart"),
        BotCommand(command="find", description="Find a partner"),
        BotCommand(command="stop", description="End chat"),
        BotCommand(command="next", description="Next partner"),
        BotCommand(command="profile", description="Profile"),
        BotCommand(command="settings", description="Settings"),
        BotCommand(command="premium", description="Premium subscription"),
        BotCommand(command="stats", description="My stats"),
        BotCommand(command="reset", description="Reset profile"),
        BotCommand(command="ai", description="AI chat"),
        BotCommand(command="help", description="Help"),
        BotCommand(command="admin", description="Admin panel"),
    ], language_code="en")
    # Spanish commands
    await bot.set_my_commands([
        BotCommand(command="start", description="Iniciar / reiniciar"),
        BotCommand(command="find", description="Buscar compañero"),
        BotCommand(command="stop", description="Terminar chat"),
        BotCommand(command="next", description="Siguiente compañero"),
        BotCommand(command="profile", description="Perfil"),
        BotCommand(command="settings", description="Configuración"),
        BotCommand(command="premium", description="Suscripción Premium"),
        BotCommand(command="stats", description="Mis estadísticas"),
        BotCommand(command="reset", description="Restablecer perfil"),
        BotCommand(command="ai", description="Chat IA"),
        BotCommand(command="help", description="Ayuda"),
        BotCommand(command="admin", description="Panel de admin"),
    ], language_code="es")

async def get_premium_badge(uid):
    u = await get_user(uid)
    if not u or not u.get("show_premium", True): return ""
    if await is_premium(uid): return " ⭐"
    return ""

async def send_ad_message(uid):
    try:
        lang = await get_lang(uid)
        await bot.send_message(
            uid,
            t(lang, "ad_message"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(lang, "prem_1m"), callback_data="buy:1m")]
            ])
        )
    except Exception: pass

async def do_find(uid, state):
    if uid in active_chats:
        return False
    u = await get_user(uid)
    if not u or not u.get("name") or not u.get("mode"): return False
    mode = u["mode"]
    my_lang = u.get("lang") or "ru"
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
            # Language isolation: users only match within same language
            p_lang_val = pu.get("lang") or "ru"
            if my_lang != p_lang_val: continue
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
        my_lang = (u.get("lang") or "ru") if u else "ru"
        p_lang = (pu.get("lang") or "ru") if pu else "ru"
        p_badge = await get_premium_badge(partner)
        my_badge = await get_premium_badge(uid)

        def _interests_str(row, lang):
            raw = (row.get("interests") or "").split(",") if row else []
            keys = [k.strip() for k in raw if k.strip()]
            return ", ".join(t(lang, k) for k in keys) or "—"

        await bot.send_message(uid,
            t(my_lang, "partner_found",
              badge=p_badge,
              name=pu.get("name", "—"),
              age=pu.get("age", "?"),
              gender=t(my_lang, f"gender_{pu.get('gender', 'other')}"),
              mode=t(my_lang, f"mode_{pu.get('mode', 'simple')}"),
              interests=_interests_str(pu, my_lang),
              rating=get_rating(pu))
        )
        await bot.send_message(partner,
            t(p_lang, "partner_found",
              badge=my_badge,
              name=u.get("name", "—"),
              age=u.get("age", "?"),
              gender=t(p_lang, f"gender_{u.get('gender', 'other')}"),
              mode=t(p_lang, f"mode_{u.get('mode', 'simple')}"),
              interests=_interests_str(u, p_lang),
              rating=get_rating(u))
        )
        await bot.send_message(uid, t(my_lang, "chat_start"), reply_markup=kb_chat(my_lang))
        await bot.send_message(partner, t(p_lang, "chat_start"), reply_markup=kb_chat(p_lang))
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
            lang = await get_lang(uid)
            char_id = random.choice(["polina", "max", "danil"])
            char = ai_chat.AI_CHARACTERS[char_id]
            name = t(lang, char["name_key"])
            await bot.send_message(uid,
                t(lang, "no_partner_wait", name=name),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"💬 {name}", callback_data=f"ai:start:{char_id}")],
                    [InlineKeyboardButton(text=t(lang, "btn_settings"), callback_data="goto:settings")],
                    [InlineKeyboardButton(text=t(lang, "ai_waiting_continue"), callback_data="goto:wait")],
                ])
            )
        except Exception: pass

async def end_chat(uid, state, go_next=False):
    async with pairing_lock:
        partner = active_chats.pop(uid, None)
        if partner:
            active_chats.pop(partner, None)
        for q in get_all_queues():
            q.discard(uid)
    if partner:
        await remove_chat_from_db(uid, partner)
        clear_chat_log(uid, partner)

        # Сообщение о завершении + кнопка mutual match
        my_lang = await get_lang(uid)
        p_lang = await get_lang(partner)
        try:
            await bot.send_message(uid, t(my_lang, "chat_ended"), reply_markup=kb_main(my_lang))
            await bot.send_message(uid, t(my_lang, "after_chat_propose"), reply_markup=kb_after_chat(partner, my_lang))
        except Exception: pass

        try:
            await bot.send_message(partner, t(p_lang, "partner_left"), reply_markup=kb_main(p_lang))
            await bot.send_message(partner, t(p_lang, "after_chat_propose"), reply_markup=kb_after_chat(uid, p_lang))
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).clear()
        except Exception: pass

        # Upsell после каждого 3-го чата
        asyncio.create_task(_send_upsell_after_chat(uid, partner))
    else:
        lang = await get_lang(uid)
        await bot.send_message(uid, t(lang, "chat_ended"), reply_markup=kb_main(lang))
    await state.clear()

    if go_next and partner:
        await asyncio.sleep(0.5)
        u = await get_user(uid)
        if u and u.get("mode"):
            lang = (u.get("lang") or "ru")
            mode = u["mode"]
            q_len = len(get_queue(mode, False)) + len(get_queue(mode, True))
            await bot.send_message(uid,
                t(lang, "queue_info", mode=t(lang, f"mode_{mode}"), count=q_len, status=t(lang, "queue_searching")),
                reply_markup=kb_cancel_search(lang)
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
            try:
                lang = await get_lang(target_uid)
                await bot.send_message(target_uid,
                    t(lang, "upsell"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=t(lang, "prem_compare"), callback_data="buy:info")]
                    ])
                )
            except Exception: pass
        else:
            await send_ad_message(target_uid)
# ====================== MUTUAL MATCH ======================
@dp.callback_query(F.data.startswith("mutual:"), ~F.data.func(lambda d: d == "mutual:decline"), StateFilter("*"))
async def mutual_like(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    partner_uid = int(callback.data.split(":", 1)[1])
        # Проверяем что партнёр не в активном чате с кем-то другим
    if partner_uid in active_chats and active_chats.get(partner_uid) != uid:
        lang = await get_lang(uid)
        await callback.answer(t(lang, "partner_busy"), show_alert=True)
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
                my_lang_tmp = await get_lang(uid)
                await callback.answer(t(my_lang_tmp, "mutual_already_in_chat"), show_alert=True)
                return
            active_chats[uid] = partner_uid
            active_chats[partner_uid] = uid
            last_msg_time[uid] = last_msg_time[partner_uid] = datetime.now()
        await state.set_state(Chat.chatting)
        pkey = StorageKey(bot_id=bot.id, chat_id=partner_uid, user_id=partner_uid)
        await FSMContext(dp.storage, key=pkey).set_state(Chat.chatting)
        await save_chat_to_db(uid, partner_uid, "mutual")

        my_lang = await get_lang(uid)
        p_lang = await get_lang(partner_uid)
        await bot.send_message(uid, t(my_lang, "mutual_match"), reply_markup=kb_chat(my_lang))
        await bot.send_message(partner_uid, t(p_lang, "mutual_match"), reply_markup=kb_chat(p_lang))
    else:
        lang = await get_lang(uid)
        p_lang = await get_lang(partner_uid)
        await callback.message.answer(t(lang, "mutual_request_sent"))
        try:
            await bot.send_message(partner_uid,
                t(p_lang, "mutual_request_received"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t(p_lang, "btn_continue"), callback_data=f"mutual:{uid}")],
                    [InlineKeyboardButton(text=t(p_lang, "btn_stop"), callback_data="mutual:decline")],
                ])
            )
        except Exception: pass
        asyncio.create_task(_mutual_timeout(uid, partner_uid))

    try:
        await callback.answer()
    except Exception:
        pass

@dp.callback_query(F.data == "mutual:decline", StateFilter("*"))
async def mutual_decline(callback: types.CallbackQuery):
    uid = callback.from_user.id
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    # Очищаем все взаимные лайки с этим пользователем
    for key in list(mutual_likes.keys()):
        mutual_likes[key].discard(uid)
    lang = await get_lang(callback.from_user.id)
    await callback.answer(t(lang, "mutual_decline_ok"))

async def _mutual_timeout(uid, partner_uid):
    await asyncio.sleep(600)  # 10 минут
    if uid in mutual_likes and partner_uid in mutual_likes[uid]:
        mutual_likes[uid].discard(partner_uid)
        try:
            lang = await get_lang(uid)
            await bot.send_message(uid, t(lang, "mutual_no_response"))
        except Exception: pass

# ====================== СТАРТ ======================
@dp.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await cleanup(uid, state)
    await ensure_user(uid)
    u = await get_user(uid)
    lang = (u.get("lang") or "ru") if u else "ru"

    banned, until = await is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer(t(lang, "banned_permanent"))
        else:
            await message.answer(t(lang, "banned_until", until=until.strftime('%H:%M %d.%m.%Y')))
        return

    # Шаг 0: Выбор языка (самый первый шаг)
    if not u or not u.get("lang"):
        await state.set_state(LangSelect.choosing)
        await message.answer(t("ru", "welcome"), reply_markup=kb_lang())
        return

    # Шаг 1: Политика конфиденциальности
    if not u.get("accepted_privacy"):
        await message.answer(t(lang, "privacy"), reply_markup=kb_privacy(lang))
        return

    # Шаг 2: Правила
    if not u.get("accepted_rules"):
        await state.set_state(Rules.waiting)
        await message.answer(t(lang, "rules"), reply_markup=kb_rules(lang))
        return

    # Всё принято — в меню
    badge = await get_premium_badge(uid)
    await message.answer(t(lang, "welcome_back", badge=badge), reply_markup=kb_main(lang))

# ====================== ВЫБОР ЯЗЫКА ======================
@dp.message(StateFilter(LangSelect.choosing), F.text.in_(list(LANG_BUTTONS.keys())))
async def choose_language(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = LANG_BUTTONS[message.text]
    await update_user(uid, lang=lang)
    await state.clear()
    # Переходим к политике конфиденциальности на выбранном языке
    await message.answer(t(lang, "privacy"), reply_markup=kb_privacy(lang))

@dp.message(StateFilter(LangSelect.choosing))
async def lang_other(message: types.Message):
    await message.answer("👆 Выбери язык / Choose language / Elige idioma")

# ====================== ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ ======================
@dp.callback_query(F.data == "privacy:accept", StateFilter("*"))
async def privacy_accept(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    await update_user(uid, accepted_privacy=True)
    try:
        await callback.message.edit_text(t(lang, "privacy_accepted"))
    except Exception: pass

    # Предлагаем подписку на канал
    await callback.message.answer(t(lang, "channel_bonus"), reply_markup=kb_channel_bonus(lang))
    await callback.answer()

@dp.callback_query(F.data == "privacy:decline", StateFilter("*"))
async def privacy_decline(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    try:
        await callback.message.edit_text(t(lang, "privacy_declined"))
    except Exception: pass
    await callback.answer()

# ====================== БОНУС ЗА КАНАЛ ======================
@dp.callback_query(F.data == "channel:check", StateFilter("*"))
async def channel_check(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    u = await get_user(uid)

    if u and u.get("channel_bonus_used"):
        await callback.answer(t(lang, "channel_bonus_used"), show_alert=True)
        await _proceed_to_rules(callback.message, state, uid)
        return

    # Если уже есть активный Premium — не даём бесплатный бонус
    if await is_premium(uid):
        await callback.answer(t(lang, "channel_already_premium"), show_alert=True)
        await update_user(uid, channel_bonus_used=True)
        await _proceed_to_rules(callback.message, state, uid)
        return

    is_subscribed = await check_channel_subscription(uid)
    if not is_subscribed:
        await callback.answer(t(lang, "channel_not_subscribed"), show_alert=True)
        return

    until = datetime.now() + timedelta(days=3)
    await update_user(uid, premium_until=until.isoformat(), channel_bonus_used=True)
    try:
        await callback.message.edit_text(
            t(lang, "channel_bonus_activated", until=until.strftime('%d.%m.%Y'))
        )
    except Exception: pass
    await _proceed_to_rules(callback.message, state, uid)
    await callback.answer()

@dp.callback_query(F.data == "channel:skip", StateFilter("*"))
async def channel_skip(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    try:
        await callback.message.edit_text(t(lang, "channel_skip"))
    except Exception: pass
    await _proceed_to_rules(callback.message, state, uid)
    await callback.answer()

async def _proceed_to_rules(message, state, uid):
    """Продолжение после privacy/channel — к правилам или в меню"""
    u = await get_user(uid)
    lang = (u.get("lang") or "ru") if u else "ru"
    if not u or not u.get("accepted_rules"):
        await state.set_state(Rules.waiting)
        await message.answer(t(lang, "rules"), reply_markup=kb_rules(lang))
    else:
        badge = await get_premium_badge(uid)
        await message.answer(t(lang, "welcome_new", badge=badge), reply_markup=kb_main(lang))

# ====================== ПРАВИЛА ======================

@dp.message(StateFilter(Rules.waiting), F.text.in_(_all("btn_accept_rules")))
async def accept_rules(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    await update_user(uid, accepted_rules=True)
    await state.clear()
    await message.answer(t(lang, "rules_accepted"), reply_markup=kb_main(lang))

@dp.message(StateFilter(Rules.waiting))
async def rules_other(message: types.Message):
    uid = message.from_user.id
    lang = await get_lang(uid)
    await message.answer(t(lang, "rules_choose_lang"))

# ====================== СТАТИСТИКА ======================
@dp.message(Command("stats"), StateFilter("*"))
async def cmd_stats(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    u = await get_user(uid)
    if not u:
        await message.answer(t(lang, "not_registered"))
        return
    user_premium = await is_premium(uid)
    if user_premium:
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            premium_text = t(lang, "stats_premium_eternal")
        else:
            try:
                until = datetime.fromisoformat(u["premium_until"])
                premium_text = t(lang, "stats_premium_until", until=until.strftime('%d.%m.%Y'))
            except Exception:
                premium_text = t(lang, "stats_premium_active")
    else:
        premium_text = t(lang, "stats_no_premium")
    days_in_bot = (datetime.now() - u.get("created_at", datetime.now())).days
    await message.answer(t(lang, "stats_text",
        chats=u.get("total_chats", 0),
        likes=u.get("likes", 0),
        rating=get_rating(u),
        warns=u.get("warn_count", 0),
        days=days_in_bot,
        premium=premium_text
    ))

# ====================== PREMIUM ======================
@dp.message(Command("premium"), StateFilter("*"))
async def cmd_premium(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    user_tier = await get_premium_tier(uid)
    tier_names = {"premium": "Premium", "plus": "Premium Plus"}
    status_text = ""
    if user_tier:
        u = await get_user(uid)
        tier_name = tier_names.get(user_tier, "Premium")
        if uid == ADMIN_ID or (u and u.get("premium_until") == "permanent"):
            status_text = t(lang, "premium_status_eternal", tier=tier_name)
        else:
            p_until = (u.get("premium_until") or u.get("ai_pro_until") or "") if u else ""
            try:
                until = datetime.fromisoformat(p_until)
                status_text = t(lang, "premium_status_until", tier=tier_name, until=until.strftime('%d.%m.%Y'))
            except Exception:
                status_text = t(lang, "premium_status_eternal", tier=tier_name)
    await message.answer(t(lang, "premium_title", status=status_text), reply_markup=kb_premium(lang))

@dp.callback_query(F.data == "buy:info", StateFilter("*"))
async def premium_info(callback: types.CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    await callback.message.answer(t(lang, "premium_info"))
    await callback.answer()

@dp.callback_query(F.data.startswith("buy:"), StateFilter("*"))
async def buy_premium(callback: types.CallbackQuery):
    uid = callback.from_user.id
    plan_key = callback.data.split(":", 1)[1]
    if plan_key == "info": return
    if plan_key not in PREMIUM_PLANS:
        lang = await get_lang(callback.from_user.id)
        await callback.answer(t(lang, "premium_unknown_plan"), show_alert=True)
        return
    plan = PREMIUM_PLANS[plan_key]
    tier = plan["tier"]
    lang = await get_lang(uid)
    tier_names = {"premium": "Premium", "plus": "Premium Plus", "ai_pro": "AI Pro"}
    tier_name = tier_names.get(tier, "Premium")
    label = t(lang, plan["label_key"])
    desc = t(lang, plan["desc_key"])
    stars = plan["stars"]
    # x2 price for non-Russian languages
    if lang != "ru":
        stars *= 2
    await callback.answer()
    await bot.send_invoice(
        chat_id=uid,
        title=f"MatchMe {tier_name} — {label}",
        description=t(lang, "invoice_desc", tier=tier_name, label=label, desc=desc),
        payload=f"premium_{plan_key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{tier_name} {label}", amount=stars)],
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
    lang = await get_lang(uid)
    tier_names = {"premium": "Premium", "plus": "Premium Plus", "ai_pro": "AI Pro"}
    tier_name = tier_names.get(tier, "Premium")
    label = t(lang, plan["label_key"])
    benefit_keys = {"premium": "benefit_premium", "plus": "benefit_plus", "ai_pro": "benefit_ai_pro"}
    await message.answer(
        t(lang, "premium_activated",
          tier=tier_name,
          label=label,
          until=until.strftime('%d.%m.%Y'),
          benefits=t(lang, benefit_keys.get(tier, "benefit_premium"))),
        reply_markup=kb_main(lang)
    )

# ====================== СБРОС ПРОФИЛЯ ======================
@dp.message(Command("reset"), StateFilter("*"))
async def cmd_reset(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    current = await state.get_state()
    if current == Chat.chatting.state:
        await unavailable(message, lang, "reason_finish_chat")
        return
    await state.set_state(ResetProfile.confirm)
    await message.answer(
        t(lang, "reset_confirm"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_accept_rules"), callback_data="reset:confirm")],
            [InlineKeyboardButton(text=t(lang, "btn_cancel_reg"), callback_data="reset:cancel")],
        ])
    )

@dp.callback_query(F.data == "reset:confirm", StateFilter(ResetProfile.confirm))
async def reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    try:
        await cleanup(uid, state)
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET name=NULL, age=NULL, gender=NULL, mode=NULL,
                    interests='', likes=0, dislikes=0, accept_simple=TRUE,
                    accept_flirt=TRUE, accept_kink=FALSE, only_own_mode=FALSE,
                    accept_cross_mode=FALSE,
                    search_gender='any', search_age_min=16, search_age_max=99,
                    lang=NULL, accepted_privacy=FALSE, accepted_rules=FALSE
                WHERE uid=$1
            """, uid)
        try:
            await callback.message.edit_text("✅ Профиль сброшен. Нажми /start чтобы начать заново.")
        except Exception:
            pass
    except Exception as e:
        logging.exception(f"reset_confirm error uid={uid}: {e}")
        try:
            await callback.message.answer("⚠️ Ошибка при сбросе профиля. Попробуй снова.")
        except Exception:
            pass
    finally:
        await callback.answer()

@dp.callback_query(F.data == "reset:cancel", StateFilter(ResetProfile.confirm))
async def reset_cancel(callback: types.CallbackQuery, state: FSMContext):
    lang = await get_lang(callback.from_user.id)
    await state.clear()
    try:
        await callback.message.edit_text(t(lang, "reset_cancelled"))
    except Exception: pass
    await callback.message.answer(t(lang, "reset_back"), reply_markup=kb_main(lang))
    await callback.answer()

# ====================== АНОНИМНЫЙ ПОИСК ======================
@dp.message(F.text.in_(_all("btn_search")), StateFilter("*"))
async def anon_search(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, lang, "reason_finish_form")
        return
    if current == Chat.chatting.state or uid in active_chats:
        await unavailable(message, lang, "reason_in_chat")
        return
    if current == AIChat.chatting.state:
        ai_sessions.pop(uid, None)
    await cleanup(uid, state)
    banned, until = await is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer(t(lang, "banned_permanent"))
        else:
            await message.answer(t(lang, "banned_until", until=until.strftime('%H:%M %d.%m.%Y')))
        return
    await ensure_user(uid)
    await message.answer(t(lang, "searching_anon"), reply_markup=kb_cancel_search(lang))
    # Shadow ban & language check
    u = await get_user(uid)
    my_shadow = u.get("shadow_ban", False) if u else False
    my_lang = (u.get("lang") or "ru") if u else "ru"
    # Собираем кандидатов ВНЕ лока
    anon_candidates = []
    for pid in list(waiting_anon):
        if pid != uid and pid not in active_chats:
            pu = await get_user(pid)
            if not pu: continue
            if pu.get("shadow_ban", False) != my_shadow: continue
            if (pu.get("lang") or "ru") != my_lang: continue
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
        p_lang = await get_lang(partner)
        await bot.send_message(uid, t(lang, "connected"), reply_markup=kb_chat(lang))
        await bot.send_message(partner, t(p_lang, "connected"), reply_markup=kb_chat(p_lang))
    else:
        await state.set_state(Chat.waiting)
        asyncio.create_task(notify_no_partner(uid))

# ====================== ПОИСК ПО АНКЕТЕ ======================
@dp.message(F.text.in_(_all("btn_find")), StateFilter("*"))
@dp.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, lang, "reason_finish_form")
        return
    if current == Chat.chatting.state or uid in active_chats:
        await unavailable(message, lang, "reason_in_chat")
        return
    if current == AIChat.chatting.state:
        ai_sessions.pop(uid, None)
    await cleanup(uid, state)
    await ensure_user(uid)
    banned, until = await is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer(t(lang, "banned_permanent"))
        else:
            await message.answer(t(lang, "banned_until", until=until.strftime('%H:%M %d.%m.%Y')))
        return
    u = await get_user(uid)
    if not u or not u.get("name") or not u.get("mode"):
        await state.set_state(Reg.name)
        await message.answer(t(lang, "reg_rules_profile"), reply_markup=kb_rules_profile(lang))
        return
    mode = u["mode"]
    user_premium = await is_premium(uid)
    q_len = len(get_queue(mode, False)) + len(get_queue(mode, True))
    status = t(lang, "queue_priority") if user_premium else t(lang, "queue_searching")
    await message.answer(
        t(lang, "queue_info", mode=t(lang, f"mode_{mode}"), count=q_len, status=status),
        reply_markup=kb_cancel_search(lang)
    )
    await do_find(uid, state)

# ====================== РЕГИСТРАЦИЯ ======================
@dp.message(F.text.in_(_all("btn_start_form")), StateFilter(Reg.name))
async def start_reg(message: types.Message):
    lang = await get_lang(message.from_user.id)
    await message.answer(t(lang, "reg_name_prompt"), reply_markup=kb_cancel_reg(lang))

@dp.message(F.text.in_(_all("btn_cancel_reg")), StateFilter("*"))
async def cancel_reg(message: types.Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    await state.clear()
    await message.answer(t(lang, "reg_cancelled"), reply_markup=kb_main(lang))

BLOCKED_TEXTS = (
    _all("btn_search") | _all("btn_find") | _all("btn_profile") |
    _all("btn_settings") | _all("btn_help") | _all("btn_ai_chat")
)

@dp.message(StateFilter(Reg.name))
async def reg_name(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await unavailable(message, lang, "reason_enter_name")
        return
    if txt in _all("btn_start_form"):
        await message.answer(t(lang, "reg_name_prompt"), reply_markup=kb_cancel_reg(lang))
        return
    await ensure_user(uid)
    await update_user(uid, name=txt.strip()[:20])
    await state.set_state(Reg.age)
    await message.answer(t(lang, "reg_age_prompt"), reply_markup=kb_cancel_reg(lang))

@dp.message(StateFilter(Reg.age))
async def reg_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await unavailable(message, lang, "reason_enter_age")
        return
    if not txt.isdigit():
        await message.answer(t(lang, "reg_age_invalid"))
        return
    age = int(txt)
    joke = get_age_joke(age, lang)
    if age <= 15:
        await message.answer(t(lang, "reg_age_too_young", joke=joke))
        return
    if age > 99:
        await message.answer(t(lang, "reg_age_too_old", joke=joke))
        return
    await update_user(uid, age=age)
    await message.answer(joke)
    await asyncio.sleep(0.5)
    await state.set_state(Reg.gender)
    await message.answer(t(lang, "reg_gender_prompt"), reply_markup=kb_gender(lang))

@dp.message(StateFilter(Reg.gender))
async def reg_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await unavailable(message, lang, "reason_choose_gender")
        return
    if txt == t(lang, "btn_male"): gender = "male"
    elif txt == t(lang, "btn_female"): gender = "female"
    elif txt == t(lang, "btn_other"): gender = "other"
    else:
        await message.answer(t(lang, "reg_gender_invalid"), reply_markup=kb_gender(lang))
        return
    await update_user(uid, gender=gender)
    await state.set_state(Reg.mode)
    await message.answer(t(lang, "reg_mode_prompt"), reply_markup=kb_mode(lang))

@dp.message(StateFilter(Reg.mode))
async def reg_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await unavailable(message, lang, "reason_choose_mode")
        return
    if txt == t(lang, "btn_mode_simple"): mode = "simple"
    elif txt == t(lang, "btn_mode_flirt"): mode = "flirt"
    elif txt == t(lang, "btn_mode_kink"): mode = "kink"
    else:
        await message.answer(t(lang, "reg_mode_invalid"), reply_markup=kb_mode(lang))
        return
    # Проверка возраста для Kink
    if mode == "kink":
        u = await get_user(uid)
        age = u.get("age", 0) if u else 0
        if age < 18:
            await message.answer(t(lang, "reg_kink_age"), reply_markup=kb_mode(lang))
            return
    await update_user(uid, mode=mode)
    await state.update_data(temp_interests=[], reg_mode=mode)
    await state.set_state(Reg.interests)
    await message.answer(t(lang, "reg_interests_prompt"), reply_markup=ReplyKeyboardRemove())
    await message.answer("👇", reply_markup=kb_interests(mode, [], lang))

@dp.callback_query(F.data.startswith("int:"), StateFilter(Reg.interests))
async def reg_interest(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    sel = data.get("temp_interests", [])
    mode = data.get("reg_mode", "simple")
    if val == "done":
        if not sel:
            await callback.answer(t(lang, "reg_interests_min"), show_alert=True)
            return
        await update_user(uid, interests=",".join(sel))
        await state.clear()
        try:
            await callback.message.edit_text(t(lang, "reg_done"))
        except Exception: pass
        await callback.answer()
        u = await get_user(uid)
        mode = u.get("mode", "simple")
        q_len = len(get_queue(mode, False)) + len(get_queue(mode, True))
        await callback.message.answer(
            t(lang, "queue_info", mode=t(lang, f"mode_{mode}"), count=q_len, status=t(lang, "queue_searching")),
            reply_markup=kb_cancel_search(lang)
        )
        await do_find(uid, state)
        return
    if val in sel:
        sel.remove(val)
        await callback.answer(t(lang, "reg_interest_removed", val=t(lang, val)))
    elif len(sel) < 3:
        sel.append(val)
        await callback.answer(t(lang, "reg_interest_added", val=t(lang, val)))
    else:
        await callback.answer(t(lang, "reg_interests_max"), show_alert=True)
        return
    await state.update_data(temp_interests=sel)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb_interests(mode, sel, lang))
    except Exception: pass

@dp.message(StateFilter(Reg.interests))
async def reg_interest_text(message: types.Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "reg_cancelled"), reply_markup=kb_main(lang))
        return
    await message.answer(t(lang, "reg_interests_invalid"))

# ====================== ЧАТ ======================
@dp.message(StateFilter(Chat.chatting))
async def relay(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    txt = message.text or ""
    if txt == t(lang, "btn_next") or "⏭" in txt:
        await end_chat(uid, state, go_next=True)
        return
    if txt == t(lang, "btn_stop"):
        await end_chat(uid, state, go_next=False)
        return
    if txt == t(lang, "btn_complaint") or "🚩" in txt:
        await state.set_state(Complaint.reason)
        await message.answer(t(lang, "complaint_prompt"), reply_markup=kb_complaint(lang))
        return
    if txt == t(lang, "btn_like") or "👍" in txt:
        if uid in active_chats:
            partner = active_chats[uid]
            # Защита от спама лайков — 1 лайк за чат
            chat_key = get_chat_key(uid, partner)
            like_key = (uid, chat_key)
            if like_key in liked_chats:
                await message.answer(t(lang, "like_already"))
                return
            liked_chats.add(like_key)
            await increment_user(partner, likes=1)
            await message.answer(t(lang, "like_sent"))
            try:
                p_lang = await get_lang(partner)
                await bot.send_message(partner, t(p_lang, "like_received"))
            except Exception: pass
        return
    if txt == t(lang, "btn_topic") or "🎲" in txt:
        if uid in active_chats:
            partner = active_chats[uid]
            topics = get_chat_topics(lang)
            idx = random.randrange(len(topics))
            topic = topics[idx]
            await message.answer(t(lang, "topic_sent", topic=topic))
            try:
                p_lang = await get_lang(partner)
                p_topics = get_chat_topics(p_lang)
                p_topic = p_topics[idx] if idx < len(p_topics) else topic
                await bot.send_message(partner, t(p_lang, "topic_received", topic=p_topic))
            except Exception: pass
        return
    if txt == t(lang, "btn_home") or "🏠" in txt:
        await end_chat(uid, state, go_next=False)
        return
    if txt.startswith("/start"):
        await end_chat(uid, state, go_next=False)
        return
    partner = active_chats.get(uid)
    if not partner:
        await state.clear()
        await message.answer(t(lang, "not_in_chat"), reply_markup=kb_main(lang))
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
                await message.answer(t(lang, "hardban"))
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
        await message.answer(t(lang, "spam_warning"))
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
    lang = await get_lang(callback.from_user.id)
    await state.set_state(Chat.chatting)
    try:
        await callback.message.edit_text(t(lang, "complaint_cancelled"))
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
    lang = await get_lang(uid)
    if not partner:
        try:
            await callback.message.edit_text(t(lang, "complaint_not_in_chat"))
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
        await callback.message.edit_text(t(lang, "complaint_sent", id=complaint_id))
    except Exception: pass
    await bot.send_message(uid, t(lang, "chat_ended"), reply_markup=kb_main(lang))
    try:
        p_lang = await get_lang(partner)
        await bot.send_message(partner, t(p_lang, "partner_complained"), reply_markup=kb_main(p_lang))
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
@dp.message(F.text.in_(_all("btn_cancel_search")), StateFilter("*"))
async def cancel_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    async with pairing_lock:
        removed = any(uid in q for q in get_all_queues())
        for q in get_all_queues():
            q.discard(uid)
    await state.clear()
    await message.answer(t(lang, "search_cancelled") if removed else t(lang, "not_searching"), reply_markup=kb_main(lang))

# ====================== СТОП / СЛЕДУЮЩИЙ ======================
@dp.message(Command("stop"), StateFilter("*"))
async def cmd_stop(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, lang, "reason_finish_anketa")
        return
    await end_chat(uid, state, go_next=False)

@dp.message(Command("next"), StateFilter("*"))
async def cmd_next(message: types.Message, state: FSMContext):
    await end_chat(message.from_user.id, state, go_next=True)

# ====================== ПРОФИЛЬ ======================
@dp.message(F.text.in_(_all("btn_profile")), StateFilter("*"))
@dp.message(Command("profile"), StateFilter("*"))
async def show_profile(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, lang, "reason_finish_form")
        return
    if current == Chat.chatting.state:
        await unavailable(message, lang, "reason_in_chat_stop")
        return
    await ensure_user(uid)
    u = await get_user(uid)
    if not u or not u.get("name"):
        await message.answer(t(lang, "profile_not_filled"), reply_markup=kb_main(lang))
        return
    user_tier = await get_premium_tier(uid)
    show_badge = u.get("show_premium", True)
    tier_names = {"premium": "Premium", "plus": "Premium Plus"}
    if user_tier:
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            premium_status = t(lang, "premium_eternal", tier=tier_names.get(user_tier, "Premium"))
        else:
            p_until = u.get("premium_until") or u.get("ai_pro_until") or ""
            try:
                until = datetime.fromisoformat(p_until)
                premium_status = t(lang, "premium_until_date", tier=tier_names.get(user_tier, "Premium"), until=until.strftime('%d.%m.%Y'))
            except Exception:
                premium_status = tier_names.get(user_tier, "Premium")
    else:
        premium_status = t(lang, "premium_none")
    badge = " ⭐" if (user_tier and show_badge) else ""
    raw_interests = (u.get("interests") or "").split(",")
    interests_str = ", ".join(t(lang, k.strip()) for k in raw_interests if k.strip()) or "—"
    profile_text = t(lang, "profile_text",
        badge=badge,
        name=u.get("name", "—"),
        age=u.get("age", "—"),
        gender=t(lang, f"gender_{u.get('gender', 'other')}"),
        mode=t(lang, f"mode_{u.get('mode', 'simple')}"),
        interests=interests_str,
        rating=get_rating(u),
        likes=u.get("likes", 0),
        chats=u.get("total_chats", 0),
        warns=u.get("warn_count", 0),
        premium=premium_status
    )
    if not user_tier:
        profile_text += t(lang, "profile_upgrade")
    await message.answer(profile_text, reply_markup=kb_edit(lang))

# ====================== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ======================
@dp.callback_query(F.data.startswith("edit:"), StateFilter("*"))
async def edit_profile_cb(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    lang = await get_lang(uid)
    await callback.answer()
    if field == "name":
        await state.set_state(EditProfile.name)
        await callback.message.answer(t(lang, "edit_name_prompt"), reply_markup=kb_cancel_reg(lang))
    elif field == "age":
        await state.set_state(EditProfile.age)
        await callback.message.answer(t(lang, "edit_age_prompt"), reply_markup=kb_cancel_reg(lang))
    elif field == "gender":
        await state.set_state(EditProfile.gender)
        await callback.message.answer(t(lang, "edit_gender_prompt"), reply_markup=kb_gender(lang))
    elif field == "mode":
        await state.set_state(EditProfile.mode)
        await callback.message.answer(t(lang, "edit_mode_prompt"), reply_markup=kb_mode(lang))
    elif field == "interests":
        u = await get_user(uid)
        mode = u.get("mode", "simple") if u else "simple"
        await state.set_state(EditProfile.interests)
        await state.update_data(temp_interests=[], edit_mode=mode)
        await callback.message.answer(t(lang, "edit_interests_prompt"), reply_markup=kb_interests(mode, [], lang))

@dp.message(StateFilter(EditProfile.name))
async def edit_name(message: types.Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=kb_main(lang))
        return
    await update_user(message.from_user.id, name=message.text.strip()[:20])
    await state.clear()
    await message.answer(t(lang, "edit_name_done"), reply_markup=kb_main(lang))

@dp.message(StateFilter(EditProfile.age))
async def edit_age(message: types.Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=kb_main(lang))
        return
    if not message.text or not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer(t(lang, "edit_age_invalid"))
        return
    age = int(message.text)
    joke = get_age_joke(age, lang)
    await update_user(message.from_user.id, age=age)
    await state.clear()
    await message.answer(t(lang, "edit_age_done", joke=joke), reply_markup=kb_main(lang))

@dp.message(StateFilter(EditProfile.gender))
async def edit_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=kb_main(lang))
        return
    txt = message.text or ""
    if txt == t(lang, "btn_male"): g = "male"
    elif txt == t(lang, "btn_female"): g = "female"
    elif txt == t(lang, "btn_other"): g = "other"
    else:
        await message.answer(t(lang, "reg_gender_invalid"), reply_markup=kb_gender(lang))
        return
    await update_user(uid, gender=g)
    await state.clear()
    await message.answer(t(lang, "edit_gender_done"), reply_markup=kb_main(lang))

@dp.message(StateFilter(EditProfile.mode))
async def edit_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=kb_main(lang))
        return
    txt = message.text or ""
    if txt == t(lang, "btn_mode_simple"): mode = "simple"
    elif txt == t(lang, "btn_mode_flirt"): mode = "flirt"
    elif txt == t(lang, "btn_mode_kink"): mode = "kink"
    else:
        await message.answer(t(lang, "reg_mode_invalid"), reply_markup=kb_mode(lang))
        return
    # Проверка возраста для Kink
    if mode == "kink":
        u = await get_user(uid)
        age = u.get("age", 0) if u else 0
        if age < 18:
            await message.answer(t(lang, "reg_kink_age"), reply_markup=kb_mode(lang))
            return
    await update_user(uid, mode=mode, accept_cross_mode=False, interests="")
    await state.set_state(EditProfile.interests)
    await state.update_data(temp_interests=[], edit_mode=mode)
    await message.answer(t(lang, "edit_interests_prompt"), reply_markup=ReplyKeyboardRemove())
    await message.answer("👇", reply_markup=kb_interests(mode, [], lang))

@dp.callback_query(F.data.startswith("int:"), StateFilter(EditProfile.interests))
async def edit_interest(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    sel = data.get("temp_interests", [])
    mode = data.get("edit_mode", "simple")
    if val == "done":
        if not sel:
            await callback.answer(t(lang, "reg_interests_min"), show_alert=True)
            return
        await update_user(uid, interests=",".join(sel))
        await state.clear()
        try:
            await callback.message.edit_text(t(lang, "edit_interests_done"))
        except Exception: pass
        await callback.message.answer(t(lang, "edit_done"), reply_markup=kb_main(lang))
        await callback.answer()
        return
    if val in sel:
        sel.remove(val)
        await callback.answer(t(lang, "reg_interest_removed", val=t(lang, val)))
    elif len(sel) < 3:
        sel.append(val)
        await callback.answer(t(lang, "reg_interest_added", val=t(lang, val)))
    else:
        await callback.answer(t(lang, "reg_interests_max"), show_alert=True)
        return
    await state.update_data(temp_interests=sel)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb_interests(mode, sel, lang))
    except Exception: pass

@dp.message(StateFilter(EditProfile.interests))
async def edit_interest_text(message: types.Message, state: FSMContext):
    lang = await get_lang(message.from_user.id)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=kb_main(lang))
        return
    await message.answer(t(lang, "reg_interests_invalid"))

# ====================== НАСТРОЙКИ ======================
@dp.message(F.text.in_(_all("btn_settings")), StateFilter("*"))
@dp.message(Command("settings"), StateFilter("*"))
async def show_settings(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await unavailable(message, lang, "reason_finish_anketa")
        return
    if current == Chat.chatting.state:
        await unavailable(message, lang, "reason_in_chat")
        return
    await ensure_user(uid)
    await message.answer(t(lang, "settings_title"), reply_markup=await kb_settings(uid, lang))

@dp.callback_query(F.data.startswith("set:"), StateFilter("*"))
async def toggle_setting(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    parts = callback.data.split(":")
    key = parts[1]
    u = await get_user(uid)
    if key == "gender":
        user_premium = await is_premium(uid)
        mode = u.get("mode", "simple") if u else "simple"
        if mode != "simple" and not user_premium:
            await callback.answer(t(lang, "settings_gender_locked"), show_alert=True)
            return
        await state.set_state(EditProfile.search_gender)
        await callback.message.answer(t(lang, "settings_gender_prompt"), reply_markup=kb_search_gender(lang))
        await callback.answer()
        return
    elif key == "gender_locked":
        await callback.answer(t(lang, "settings_premium_only"), show_alert=True)
        return
    elif key == "age" and len(parts) == 4:
        min_age = int(parts[2])
        max_age = int(parts[3])
        await update_user(uid, search_age_min=min_age, search_age_max=max_age)
        try:
            await callback.message.edit_reply_markup(reply_markup=await kb_settings(uid, lang))
        except Exception: pass
        if min_age == 16 and max_age == 99:
            await callback.answer(t(lang, "settings_age_any").lstrip("✅ "))
        else:
            await callback.answer(t(lang, "settings_age_range", min=min_age, max=max_age).lstrip("✅ "))
        return
    elif key == "cross":
        mode = u.get("mode", "simple") if u else "simple"
        if mode == "simple":
            await callback.answer(t(lang, "settings_cross_unavailable"), show_alert=True)
            return
        await update_user(uid, accept_cross_mode=not u.get("accept_cross_mode", False))
    elif key == "show_premium":
        await update_user(uid, show_premium=not u.get("show_premium", True))
    try:
        await callback.message.edit_reply_markup(reply_markup=await kb_settings(uid, lang))
    except Exception: pass
    await callback.answer(t(lang, "settings_changed"))

@dp.message(StateFilter(EditProfile.search_gender))
async def set_search_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await get_lang(uid)
    txt = message.text or ""
    if txt == t(lang, "btn_back"):
        await state.clear()
        await message.answer(t(lang, "settings_title"), reply_markup=await kb_settings(uid, lang))
        return
    if txt == t(lang, "btn_find_male"): sg = "male"
    elif txt == t(lang, "btn_find_female"): sg = "female"
    elif txt == t(lang, "btn_find_other"): sg = "other"
    else: sg = "any"
    await update_user(uid, search_gender=sg)
    await state.clear()
    await message.answer(t(lang, "settings_gender_saved"), reply_markup=kb_main(lang))

# ====================== ПОМОЩЬ ======================
@dp.message(F.text.in_(_all("btn_help")), StateFilter("*"))
@dp.message(Command("help"), StateFilter("*"))
async def show_help(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    await message.answer(t(lang, "help_text"), reply_markup=kb_main(lang))

@dp.message(Command("restart"), StateFilter("*"))
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
