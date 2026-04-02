import asyncio
import os
import aiohttp
import random
import logging
from telegraph_pages import create_legal_pages, get_legal_url
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand,
    LabeledPrice, PreCheckoutQuery,
)
import asyncpg
import moderation
from ai_utils import get_ai_answer, translate_message  # подготовка для AI-персонажей на OpenRouter
from states import (Reg, Chat, LangSelect, Rules, Complaint, EditProfile,
                    AdminState, ResetProfile, AIChat)
from locales import t, LANG_BUTTONS, TEXTS
from keyboards import (
    CHANNEL_ID, INTERESTS_MAP,
    kb_main, kb_lang, kb_privacy, kb_rules, kb_rules_profile, kb_cancel_reg,
    kb_gender, kb_mode, kb_cancel_search, kb_chat, kb_search_gender,
    kb_after_chat, kb_channel_bonus, kb_ai_characters, kb_ai_chat,
    kb_interests, kb_complaint, kb_edit, kb_complaint_action,
    kb_user_actions, kb_premium, kb_energy_shop,
)
import db
from constants import (
    PRICE_MULTIPLIERS, PREMIUM_PLANS, AB_PRICE_DISCOUNT_B, GIFTS, ENERGY_PACKS,
    get_plan_price, get_chat_topics,
    LEVEL_THRESHOLDS, LEVEL_NAMES, STREAK_BONUSES,
    STOP_WORDS, PARTNER_ADS, filter_ads as _filter_ads,
)
import ai_chat
import admin as admin_module
import energy_shop as energy_shop_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("matchme")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))


# Constants imported from constants.py: PREMIUM_PLANS, GIFTS, PRICE_MULTIPLIERS, etc.

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
translate_notice_sent = set()  # (uid, partner) — one-time translation upsell per chat
gift_prompt_sent = set()  # (uid, partner) — one-time gift prompt per chat
pairing_lock = asyncio.Lock()
chat_logs = {}
ai_sessions = {}
last_ai_msg = {}  # uid -> datetime последнего сообщения в AI чат
mutual_likes = {}  # uid -> set of partner_uids которым лайкнул
liked_chats = set()  # (uid, chat_key) — защита от спама лайков


# GIFTS, STOP_WORDS — see constants.py


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
            ("ai_energy_used", "INTEGER DEFAULT 0"),
            ("ai_messages_reset", "TIMESTAMP DEFAULT NOW()"),
            ("premium_tier", "TEXT DEFAULT NULL"),
            ("ai_pro_until", "TEXT DEFAULT NULL"),
            ("ai_bonus", "INTEGER DEFAULT 0"),
            ("search_range", "TEXT DEFAULT 'local'"),
            ("auto_translate", "BOOLEAN DEFAULT TRUE"),
            ("referred_by", "BIGINT DEFAULT NULL"),
            ("referral_bonus_given", "BOOLEAN DEFAULT FALSE"),
            ("trial_used", "BOOLEAN DEFAULT FALSE"),
            ("streak_days", "INTEGER DEFAULT 0"),
            ("streak_last_date", "DATE DEFAULT NULL"),
            ("level", "INTEGER DEFAULT 0"),
            ("ab_group", "TEXT DEFAULT NULL"),
            ("winback_stage", "INTEGER DEFAULT 0"),
            ("premium_expired_at", "TIMESTAMP DEFAULT NULL"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}")
            except Exception: pass
        # Migrate ai_character_media
        try:
            await conn.execute("ALTER TABLE ai_character_media ADD COLUMN IF NOT EXISTS hot_photo_file_id TEXT DEFAULT NULL")
            await conn.execute("ALTER TABLE ai_character_media ADD COLUMN IF NOT EXISTS hot_gif_file_id TEXT DEFAULT NULL")
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

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_history (
                id SERIAL PRIMARY KEY,
                uid BIGINT NOT NULL,
                character_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS ai_history_uid_char ON ai_history(uid, character_id)"
            )
        except Exception: pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_character_media (
                character_id TEXT PRIMARY KEY,
                gif_file_id TEXT DEFAULT NULL,
                photo_file_id TEXT DEFAULT NULL,
                blurred_file_id TEXT DEFAULT NULL,
                hot_photo_file_id TEXT DEFAULT NULL,
                hot_gif_file_id TEXT DEFAULT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ab_events (
                id SERIAL PRIMARY KEY,
                uid BIGINT NOT NULL,
                ab_group TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            await conn.execute("CREATE INDEX IF NOT EXISTS ab_events_uid ON ab_events(uid)")
            await conn.execute("CREATE INDEX IF NOT EXISTS ab_events_type ON ab_events(event_type, ab_group)")
        except Exception: pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_notes (
                uid BIGINT NOT NULL,
                character_id TEXT NOT NULL,
                notes TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (uid, character_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ad_events (
                id SERIAL PRIMARY KEY,
                uid BIGINT NOT NULL,
                ad_key TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT DEFAULT 'search',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            await conn.execute("CREATE INDEX IF NOT EXISTS ad_events_key ON ad_events(ad_key, event_type)")
            await conn.execute("CREATE INDEX IF NOT EXISTS ad_events_created ON ad_events(created_at)")
        except Exception: pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_ratings (
                id SERIAL PRIMARY KEY,
                uid BIGINT NOT NULL,
                partner_uid BIGINT NOT NULL,
                stars INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            await conn.execute("CREATE INDEX IF NOT EXISTS chat_ratings_uid ON chat_ratings(uid)")
        except Exception: pass

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

# DB helpers — delegated to db.py
get_user = db.get_user
get_lang = db.get_lang
ensure_user = db.ensure_user
update_user = db.update_user
increment_user = db.increment_user
get_ai_history = db.get_ai_history
save_ai_message = db.save_ai_message
clear_ai_history = db.clear_ai_history
get_ai_notes = db.get_ai_notes
save_ai_notes = db.save_ai_notes
get_premium_tier = db.get_premium_tier
is_premium = db.is_premium


# ====================== SOCIAL PROOF ======================
def get_online_count() -> int:
    """Real online count: active chats + people in queues."""
    chatting = len(active_chats) // 2
    in_queue = sum(len(q) for q in get_all_queues())
    return chatting + in_queue


# ====================== DAILY STREAK ======================
# LEVEL_THRESHOLDS, LEVEL_NAMES, STREAK_BONUSES — see constants.py


def _calc_level(total_chats: int) -> int:
    level = 0
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if total_chats >= threshold:
            level = i
    return level


async def update_streak(uid):
    """Call once per user interaction day. Updates streak and checks level-up."""
    u = await get_user(uid)
    if not u:
        return None, None  # streak_changed, level_changed
    today = datetime.now().date()
    last_date = u.get("streak_last_date")
    streak = u.get("streak_days", 0)
    old_level = u.get("level", 0)

    if last_date == today:
        return None, None  # already counted today

    if last_date and (today - last_date).days == 1:
        streak += 1  # consecutive day
    elif last_date and (today - last_date).days > 1:
        streak = 1  # streak broken
    else:
        streak = 1  # first visit

    # Check level
    new_level = _calc_level(u.get("total_chats", 0))

    # Check streak bonus
    bonus = STREAK_BONUSES.get(streak)
    updates = {"streak_days": streak, "streak_last_date": today, "level": new_level}
    if bonus:
        updates["ai_bonus"] = min((u.get("ai_bonus", 0) + bonus), 50)
    await update_user(uid, **updates)

    streak_changed = bonus if bonus else (streak if streak != u.get("streak_days", 0) else None)
    level_changed = new_level if new_level > old_level else None
    return streak_changed, level_changed


# ====================== A/B TESTING ======================
def get_ab_group(uid: int) -> str:
    """Deterministic A/B group based on uid."""
    return "A" if uid % 2 == 0 else "B"


async def log_ab_event(uid: int, event_type: str, event_data: str = None):
    """Log an A/B test event for analytics."""
    if not db_pool:
        return
    group = get_ab_group(uid)
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ab_events (uid, ab_group, event_type, event_data) VALUES ($1, $2, $3, $4)",
                uid, group, event_type, event_data
            )
    except Exception:
        pass


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


async def grant_referral_bonus(uid):
    """Даёт 3 дня Premium пригласившему, когда реферал завершает 1-й чат."""
    try:
        u = await get_user(uid)
        if not u or u.get("referral_bonus_given"):
            return
        referrer_id = u.get("referred_by")
        if not referrer_id:
            return
        chats = u.get("total_chats", 0)
        if chats < 1:
            return
        await update_user(uid, referral_bonus_given=True)
        referrer = await get_user(referrer_id)
        if not referrer:
            return
        base = datetime.now()
        p_until = referrer.get("premium_until")
        if p_until and p_until != "permanent":
            try:
                existing = datetime.fromisoformat(p_until)
                if existing > base:
                    base = existing
            except Exception:
                pass
        until = base + timedelta(days=3)
        await update_user(referrer_id, premium_until=until.isoformat(), premium_tier="premium")
        ref_lang = (referrer.get("lang") or "ru")
        try:
            await bot.send_message(referrer_id,
                t(ref_lang, "referral_bonus_received", until=until.strftime('%d.%m.%Y')))
        except Exception:
            pass
    except Exception as e:
        logger.error(f"grant_referral_bonus error: {e}")

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

    search_range = u.get("search_range", "local")
    sr_icon = "🌍" if search_range == "global" else "🏠"
    sr_label = t(lang, f"settings_search_{search_range}")
    buttons.append([InlineKeyboardButton(
        text=f"{sr_icon} {sr_label}", callback_data="set:search_range"
    )])

    auto_tr = u.get("auto_translate", True)
    if user_premium:
        tr_icon = "✅" if auto_tr else "❌"
        buttons.append([InlineKeyboardButton(
            text=f"{tr_icon} {t(lang, 'settings_translate')}", callback_data="set:auto_translate"
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text=f"🔒 {t(lang, 'settings_translate')}", callback_data="set:translate_locked"
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
        buttons.append([InlineKeyboardButton(text=t(lang, "settings_buy_premium"), callback_data="premium_show")])

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

def _is_in_queue(uid):
    return any(uid in q for q in get_all_queues())

async def _clear_ai_if_active(uid, state):
    current = await state.get_state()
    if current in (AIChat.choosing.state, AIChat.chatting.state):
        ai_sessions.pop(uid, None)
        await state.clear()

_last_relay_msg_id = {}

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

# Приветствие на выборе языка — всегда на всех 3 языках сразу
_LANG_WELCOME = (
    "👋 Привет! Я MatchMe — анонимный чат для общения, флирта и знакомств.\n\n"
    "👋 Hi! I'm MatchMe — anonymous chat for socializing, flirting and meeting people.\n\n"
    "👋 ¡Hola! Soy MatchMe — chat anónimo para socializar, flirtear y conocer gente.\n\n"
    "🌐 Выбери язык / Choose language / Elige idioma 👇"
)

def _detect_lang(language_code: str | None) -> str:
    """Auto-detect language from Telegram language_code."""
    code = (language_code or "").lower()
    if code.startswith("ru"):
        return "ru"
    if code.startswith("es"):
        return "es"
    return "en"

async def unavailable(message: types.Message, lang: str, reason_key: str):
    await message.answer(t(lang, "unavailable", reason=t(lang, reason_key)))

async def needs_onboarding(message: types.Message, state: FSMContext) -> bool:
    """If user hasn't accepted rules, redirect to /start. Returns True if redirected."""
    uid = message.from_user.id
    await ensure_user(uid)
    u = await get_user(uid)
    if not u or not u.get("accepted_rules") or not u.get("accepted_privacy"):
        await cmd_start(message, state)
        return True
    # Auto-detect lang if somehow missing
    if not u.get("lang"):
        lang = _detect_lang(message.from_user.language_code)
        await update_user(uid, lang=lang)
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
        BotCommand(command="referral", description="Пригласи друга"),
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
        BotCommand(command="referral", description="Invite a friend"),
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
        BotCommand(command="referral", description="Invitar amigo"),
    ], language_code="es")

async def get_premium_badge(uid):
    u = await get_user(uid)
    if not u or not u.get("show_premium", True): return ""
    if await is_premium(uid): return " ⭐"
    return ""

# PARTNER_ADS, _filter_ads — see constants.py


async def _log_ad_event(uid: int, ad_key: str, event_type: str, source: str = "search"):
    """Логирует событие рекламы (impression/click)."""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ad_events (uid, ad_key, event_type, source) VALUES ($1, $2, $3, $4)",
                uid, ad_key, event_type, source
            )
    except Exception:
        pass


async def send_ad_message(uid, source: str = "search"):
    """Показывает таргетированную партнёрскую рекламу с ротацией."""
    try:
        lang = await get_lang(uid)
        u = await get_user(uid)
        mode = u.get("mode", "simple") if u else "simple"
        chats = u.get("total_chats", 0) if u else 0
        ads = _filter_ads(lang, mode)
        if not ads:
            return
        idx = chats % len(ads)
        ad = ads[idx]
        ad_key = ad["text_key"]
        await bot.send_message(
            uid,
            t(lang, ad_key),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(lang, ad["btn_key"]), callback_data=f"adclick:{idx}:{source}")],
                [InlineKeyboardButton(text=t(lang, "btn_ad_remove"), callback_data="buy:info")],
            ])
        )
        await _log_ad_event(uid, ad_key, "impression", source)
    except Exception: pass

async def do_find(uid, state):
    if uid in active_chats:
        return False
    u = await get_user(uid)
    if not u or not u.get("mode"): return False
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
    my_search_range = u.get("search_range", "local")

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
            # Language filter: skip if both users are on "local" and languages differ
            p_lang_val = pu.get("lang") or "ru"
            p_search_range = pu.get("search_range", "local")
            if my_lang != p_lang_val and my_search_range == "local" and p_search_range == "local":
                continue
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
        asyncio.create_task(grant_referral_bonus(uid))
        asyncio.create_task(grant_referral_bonus(partner))
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
              interests=_interests_str(pu, my_lang),
              rating=get_rating(pu))
        )
        await bot.send_message(partner,
            t(p_lang, "partner_found",
              badge=my_badge,
              name=u.get("name", "—"),
              age=u.get("age", "?"),
              gender=t(p_lang, f"gender_{u.get('gender', 'other')}"),
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

# Smart character suggestion: match AI character to user's search mode
_MODE_CHARS = {
    "simple": ["luna", "max_simple"],
    "flirt": ["mia", "kai"],
    "kink": ["lilit", "eva"],
}

async def notify_no_partner(uid):
    await asyncio.sleep(30)
    if uid in active_chats:
        return
    all_waiting = set().union(*get_all_queues())
    if uid in all_waiting:
        try:
            u = await get_user(uid)
            mode = u.get("mode", "simple") if u else "simple"
            candidates = _MODE_CHARS.get(mode, _MODE_CHARS["simple"])
            # For kink, check if user has premium (VIP+ required)
            if mode == "kink" and not await is_premium(uid):
                candidates = _MODE_CHARS["flirt"]
            char_id = random.choice(candidates)
            char = ai_chat.AI_CHARACTERS[char_id]
            lang = await get_lang(uid)
            name = f"{char['emoji']} {t(lang, char['name_key'])}"
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
        translate_notice_sent.discard((uid, partner))
        translate_notice_sent.discard((partner, uid))
        gift_prompt_sent.discard((uid, partner))
        gift_prompt_sent.discard((partner, uid))

        # Сообщение о завершении + оценка + mutual match
        my_lang = await get_lang(uid)
        p_lang = await get_lang(partner)
        rate_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'⭐' * i}", callback_data=f"rate:{partner}:{i}") for i in range(1, 6)],
        ])
        p_rate_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'⭐' * i}", callback_data=f"rate:{uid}:{i}") for i in range(1, 6)],
        ])
        try:
            await bot.send_message(uid, t(my_lang, "chat_ended_rate"), reply_markup=rate_kb)
            await bot.send_message(uid, t(my_lang, "after_chat_propose"), reply_markup=kb_after_chat(partner, my_lang))
        except Exception: pass

        try:
            await bot.send_message(partner, t(p_lang, "chat_ended_rate"), reply_markup=p_rate_kb)
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
    """Умная система показа после чата:
    Чат 1: предложить подписку на канал (3 дня Premium)
    Чат 2: ничего
    Чат 3,6,9,...: upsell Premium
    Чат 5: триал Premium (одноразово)
    Чат 4,8,12,...: партнёрская реклама
    Остальные: ничего
    """
    await asyncio.sleep(3)
    for target_uid in (uid, partner):
        if target_uid in active_chats:
            continue
        u = await get_user(target_uid)
        chats = u.get("total_chats", 0) if u else 0
        # После 1-го чата — предложить подписку на канал
        if chats == 1 and u and not u.get("channel_bonus_used") and not await is_premium(target_uid):
            try:
                lang = await get_lang(target_uid)
                await bot.send_message(target_uid,
                    t(lang, "channel_bonus"),
                    reply_markup=kb_channel_bonus(lang))
            except Exception: pass
            continue
        if await is_premium(target_uid):
            continue
        if chats <= 2:
            continue
        # Триал Premium после 5-го чата
        if chats == 5 and u and not u.get("trial_used"):
            try:
                lang = await get_lang(target_uid)
                await bot.send_message(target_uid,
                    t(lang, "trial_offer"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=t(lang, "btn_activate_trial"), callback_data="trial:activate")]
                    ])
                )
                await log_ab_event(target_uid, "trial_shown")
            except Exception: pass
        # Каждый 3-й чат — upsell Premium
        elif chats % 3 == 0:
            try:
                lang = await get_lang(target_uid)
                await bot.send_message(target_uid,
                    t(lang, "upsell"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=t(lang, "prem_compare"), callback_data="buy:info")]
                    ])
                )
                await log_ab_event(target_uid, "upsell_shown")
            except Exception: pass
        # Каждый 6-й чат — партнёрская реклама (снижено, компенсируется рекламой в AI-чатах)
        elif chats % 6 == 0:
            await send_ad_message(target_uid)


# ====================== ТРИАЛ PREMIUM ======================
@dp.callback_query(F.data == "trial:activate", StateFilter("*"))
async def activate_trial(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    u = await get_user(uid)
    if not u:
        await callback.answer()
        return
    if u.get("trial_used"):
        await callback.answer(t(lang, "trial_already_used"), show_alert=True)
        return
    if await is_premium(uid):
        await callback.answer(t(lang, "channel_already_premium"), show_alert=True)
        # Уже Premium — помечаем триал как использованный, не трогаем подписку
        await update_user(uid, trial_used=True)
        return
    base = datetime.now()
    current_until = u.get("premium_until")
    if current_until and current_until != "permanent":
        try:
            existing = datetime.fromisoformat(current_until)
            if existing > base:
                base = existing
        except Exception:
            pass
    until = base + timedelta(days=3)
    await update_user(uid, premium_until=until.isoformat(), premium_tier="premium", trial_used=True)
    await log_ab_event(uid, "trial_activated")
    try:
        await callback.message.edit_text(t(lang, "trial_activated", until=until.strftime('%d.%m.%Y %H:%M')))
    except Exception: pass
    await callback.answer()


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

    # Обработка реферальной ссылки /start ref_<uid>
    args = (message.text or "").split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1][4:])
            if referrer_id != uid:
                u_check = await get_user(uid)
                if u_check and not u_check.get("referred_by"):
                    await update_user(uid, referred_by=referrer_id)
        except (ValueError, TypeError):
            pass

    # Автоопределение языка
    u = await get_user(uid)
    if not u or not u.get("lang"):
        lang = _detect_lang(message.from_user.language_code)
        await update_user(uid, lang=lang)
    else:
        lang = u.get("lang", "ru")

    # Автозахват имени из Telegram
    tg_name = (message.from_user.first_name or "User")[:30]
    if not u or not u.get("name"):
        await update_user(uid, name=tg_name)

    u = await get_user(uid)

    banned, until = await is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer(t(lang, "banned_permanent"))
        else:
            await message.answer(t(lang, "banned_until", until=until.strftime('%H:%M %d.%m.%Y')))
        return

    # Уже всё принял — в меню
    if u.get("accepted_rules") and u.get("accepted_privacy"):
        # Streak + level check
        streak_info, level_info = await update_streak(uid)
        badge = await get_premium_badge(uid)
        online = get_online_count()
        online_text = f"\n🟢 {t(lang, 'online_count', count=online)}" if online > 0 else ""
        await message.answer(
            t(lang, "welcome_back", badge=badge) + online_text,
            reply_markup=kb_main(lang)
        )
        # Notify streak milestone
        if streak_info and isinstance(streak_info, int) and streak_info in STREAK_BONUSES:
            await message.answer(t(lang, "streak_bonus", days=streak_info, bonus=STREAK_BONUSES[streak_info]))
        # Notify level-up
        if level_info is not None:
            level_name = t(lang, LEVEL_NAMES.get(level_info, "level_0"))
            await message.answer(t(lang, "level_up", level=level_info, name=level_name))
        # A/B log
        await log_ab_event(uid, "session_start")
        return

    # Новый юзер — отправляем условия со ссылкой на полную версию
    legal_url = get_legal_url(lang)
    await message.answer(
        t(lang, "privacy", legal_url=legal_url),
        disable_web_page_preview=True,
    )

    name = u.get("name", tg_name)
    await message.answer(
        t(lang, "welcome_intro", name=name),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_accept_all"), callback_data="accept:all")],
            [
                InlineKeyboardButton(text="🇷🇺", callback_data="lang:ru"),
                InlineKeyboardButton(text="🇬🇧", callback_data="lang:en"),
                InlineKeyboardButton(text="🇪🇸", callback_data="lang:es"),
            ],
        ])
    )

# ====================== ПРИНЯТИЕ ПРАВИЛ (НОВЫЙ ОНБОРДИНГ) ======================
@dp.callback_query(F.data == "accept:all", StateFilter("*"))
async def accept_all(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    await update_user(uid, accepted_privacy=True, accepted_rules=True, ab_group=get_ab_group(uid))
    await update_streak(uid)
    try:
        await callback.message.edit_text(t(lang, "rules_accepted"))
    except Exception: pass
    badge = await get_premium_badge(uid)
    online = get_online_count()
    online_text = f"\n🟢 {t(lang, 'online_count', count=online)}" if online > 0 else ""
    await callback.message.answer(
        t(lang, "welcome_new", badge=badge) + online_text,
        reply_markup=kb_main(lang)
    )
    await log_ab_event(uid, "registered")
    await callback.answer()

@dp.callback_query(F.data.startswith("lang:"), StateFilter("*"))
async def switch_lang_onboarding(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    new_lang = callback.data.split(":")[1]
    if new_lang not in ("ru", "en", "es"):
        await callback.answer()
        return
    await update_user(uid, lang=new_lang)
    u = await get_user(uid)
    name = u.get("name", "User") if u else "User"

    # Отправляем условия на новом языке со ссылкой
    legal_url = get_legal_url(new_lang)
    try:
        await callback.message.edit_text(
            t(new_lang, "privacy", legal_url=legal_url),
            disable_web_page_preview=True,
        )
    except Exception: pass
    try:
        await callback.message.answer(
            t(new_lang, "welcome_intro", name=name),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(new_lang, "btn_accept_all"), callback_data="accept:all")],
                [
                    InlineKeyboardButton(text="🇷🇺", callback_data="lang:ru"),
                    InlineKeyboardButton(text="🇬🇧", callback_data="lang:en"),
                    InlineKeyboardButton(text="🇪🇸", callback_data="lang:es"),
                ],
            ])
        )
    except Exception: pass
    await callback.answer()

# ====================== ВЫБОР ЯЗЫКА (legacy) ======================
@dp.message(StateFilter(LangSelect.choosing), F.text.in_(list(LANG_BUTTONS.keys())))
async def choose_language(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = LANG_BUTTONS[message.text]
    await update_user(uid, lang=lang)
    await state.clear()
    legal_url = get_legal_url(lang)
    await message.answer(t(lang, "privacy", legal_url=legal_url), reply_markup=kb_privacy(lang), disable_web_page_preview=True)

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
        await _proceed_after_channel(callback.message, state, uid)
        return

    # Если уже есть активный Premium — не даём бесплатный бонус
    if await is_premium(uid):
        await callback.answer(t(lang, "channel_already_premium"), show_alert=True)
        await update_user(uid, channel_bonus_used=True)
        await _proceed_after_channel(callback.message, state, uid)
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
    await _proceed_after_channel(callback.message, state, uid)
    await callback.answer()

@dp.callback_query(F.data == "channel:skip", StateFilter("*"))
async def channel_skip(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    try:
        await callback.message.edit_text(t(lang, "channel_skip"))
    except Exception: pass
    await _proceed_after_channel(callback.message, state, uid)
    await callback.answer()

async def _proceed_after_channel(message, state, uid):
    """Продолжение после channel bonus — в меню"""
    u = await get_user(uid)
    lang = (u.get("lang") or "ru") if u else "ru"
    badge = await get_premium_badge(uid)
    await message.answer(t(lang, "welcome_back", badge=badge), reply_markup=kb_main(lang))

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
    warns = u.get("warn_count", 0)
    warns_line = f"⚠️ Warnings: {warns}\n" if warns > 0 else ""
    await message.answer(t(lang, "stats_text",
        total_chats=u.get("total_chats", 0),
        likes=u.get("likes", 0),
        rating=get_rating(u),
        warns_line=warns_line,
        days=days_in_bot,
        premium=premium_text
    ))

# ====================== РЕФЕРАЛЬНАЯ ПРОГРАММА ======================
@dp.message(Command("referral"), StateFilter("*"))
async def cmd_referral(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    if _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
    ref_link = f"https://t.me/MyMatchMeBot?start=ref_{uid}"
    # Считаем сколько рефералов привёл
    count = 0
    if db_pool:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as cnt FROM users WHERE referred_by=$1 AND referral_bonus_given=TRUE", uid)
            count = row["cnt"] if row else 0
    await message.answer(t(lang, "referral_info", link=ref_link, count=count))


# ====================== PREMIUM ======================
@dp.message(Command("premium"), StateFilter("*"))
async def cmd_premium(message: types.Message, state: FSMContext):
    if await needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await get_lang(uid)
    if _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
    user_tier = await get_premium_tier(uid)
    u = await get_user(uid)
    status_text = ""
    if user_tier:
        if uid == ADMIN_ID or (u and u.get("premium_until") == "permanent"):
            status_text = t(lang, "premium_status_eternal", tier="Premium")
        else:
            p_until = (u.get("premium_until") or "") if u else ""
            try:
                until = datetime.fromisoformat(p_until)
                status_text = t(lang, "premium_status_until", tier="Premium", until=until.strftime('%d.%m.%Y'))
            except Exception:
                status_text = t(lang, "premium_status_eternal", tier="Premium")
    ab_group = u.get("ab_group") if u else None
    prices = {k: get_plan_price(k, lang, ab_group) for k in PREMIUM_PLANS}
    await message.answer(t(lang, "premium_title", status=status_text), reply_markup=kb_premium(lang, plan_prices=prices))

@dp.callback_query(F.data == "premium_show", StateFilter("*"))
async def premium_show_cb(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    user_tier = await get_premium_tier(uid)
    u = await get_user(uid)
    status_text = ""
    if user_tier:
        if uid == ADMIN_ID or (u and u.get("premium_until") == "permanent"):
            status_text = t(lang, "premium_status_eternal", tier="Premium")
        else:
            p_until = (u.get("premium_until") or "") if u else ""
            try:
                until = datetime.fromisoformat(p_until)
                status_text = t(lang, "premium_status_until", tier="Premium", until=until.strftime('%d.%m.%Y'))
            except Exception:
                status_text = t(lang, "premium_status_eternal", tier="Premium")
    ab_group = u.get("ab_group") if u else None
    prices = {k: get_plan_price(k, lang, ab_group) for k in PREMIUM_PLANS}
    await callback.message.answer(t(lang, "premium_title", status=status_text), reply_markup=kb_premium(lang, plan_prices=prices))
    await callback.answer()

@dp.callback_query(F.data == "buy:info", StateFilter("*"))
async def premium_info(callback: types.CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    await callback.message.answer(t(lang, "premium_info"))
    await callback.answer()

@dp.callback_query(F.data.startswith("buy:"), StateFilter("*"))
async def buy_premium(callback: types.CallbackQuery):
    uid = callback.from_user.id
    plan_key = callback.data.split(":", 1)[1]
    if plan_key not in PREMIUM_PLANS:
        lang = await get_lang(callback.from_user.id)
        await callback.answer(t(lang, "premium_unknown_plan"), show_alert=True)
        return
    plan = PREMIUM_PLANS[plan_key]
    lang = await get_lang(uid)
    u = await get_user(uid)
    ab_group = u.get("ab_group") if u else None
    label = t(lang, plan["label_key"])
    desc = t(lang, plan["desc_key"])
    stars = get_plan_price(plan_key, lang, ab_group)
    # Логируем A/B ценовой тест
    await log_ab_event(uid, "price_shown", f"{plan_key}:{stars}")
    await callback.answer()
    await bot.send_invoice(
        chat_id=uid,
        title=f"MatchMe Premium — {label}",
        description=t(lang, "invoice_desc", tier="Premium", label=label, desc=desc),
        payload=f"premium_{plan_key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Premium {label}", amount=stars)],
    )

async def _handle_gift_payment(uid, payload):
    """Process a gift payment: grant premium to recipient."""
    parts = payload.split("_", 2)
    if len(parts) != 3:
        return
    gift_type = parts[1]
    try:
        partner_uid = int(parts[2])
    except ValueError:
        logger.warning(f"Invalid gift payload: {payload}")
        return
    gift = GIFTS.get(gift_type)
    if not gift:
        return
    lang = await get_lang(uid)
    p_lang = await get_lang(partner_uid)

    # Grant premium to partner
    base = datetime.now()
    p_user = await get_user(partner_uid)
    if p_user:
        current_until = p_user.get("premium_until")
        if current_until and current_until != "permanent":
            try:
                existing = datetime.fromisoformat(current_until)
                if existing > base:
                    base = existing
            except Exception: pass
    until = base + timedelta(days=gift["days"])
    await update_user(partner_uid, premium_until=until.isoformat(), premium_tier="premium",
                      winback_stage=0, premium_expired_at=None)

    # Sender confirmation
    try:
        await bot.send_message(uid, t(lang, "gift_sent", emoji=gift["emoji"], days=gift["days"]))
    except Exception: pass

    # Recipient "opening" visual
    try:
        opening_msg = await bot.send_message(partner_uid, t(p_lang, "gift_opening"))
        await asyncio.sleep(1.5)
        await opening_msg.edit_text(
            t(p_lang, "gift_received",
              emoji=gift["emoji"],
              gift_name=t(p_lang, f"gift_{gift_type}"),
              days=gift["days"],
              until=until.strftime('%d.%m.%Y'))
        )
    except Exception:
        try:
            await bot.send_message(partner_uid,
                t(p_lang, "gift_received",
                  emoji=gift["emoji"],
                  gift_name=t(p_lang, f"gift_{gift_type}"),
                  days=gift["days"],
                  until=until.strftime('%d.%m.%Y')))
        except Exception: pass
    await log_ab_event(uid, "gift_sent", gift_type)


@dp.pre_checkout_query(StateFilter("*"))
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment, StateFilter("*"))
async def successful_payment(message: types.Message):
    uid = message.from_user.id
    payload = message.successful_payment.invoice_payload

    # Gift payments
    if payload.startswith("gift_"):
        await _handle_gift_payment(uid, payload)
        return

    # Energy pack payments
    if payload.startswith("energy_"):
        pack_key = payload[len("energy_"):]
        pack = ENERGY_PACKS.get(pack_key)
        if not pack:
            logger.warning(f"Unknown energy pack: {pack_key}")
            return
        lang = await get_lang(uid)
        u = await get_user(uid)
        energy_used = u.get("ai_energy_used", 0) if u else 0
        new_used = max(0, energy_used - pack["amount"])
        await update_user(uid, ai_energy_used=new_used)
        await message.answer(t(lang, "energy_purchased", amount=pack["amount"]))
        return

    plan_key = payload.replace("premium_", "")
    if plan_key not in PREMIUM_PLANS:
        logger.warning(f"Invalid plan_key in payload: {plan_key}")
        return
    plan = PREMIUM_PLANS[plan_key]
    u = await get_user(uid)
    base = datetime.now()
    # Продлеваем от текущей даты окончания если есть
    if u:
        current_until = u.get("premium_until")
        if current_until and current_until != "permanent":
            try:
                existing = datetime.fromisoformat(current_until)
                if existing > base:
                    base = existing
            except Exception:
                pass
    until = base + timedelta(days=plan["days"])
    await update_user(uid, premium_until=until.isoformat(), premium_tier="premium",
                      winback_stage=0, premium_expired_at=None)
    await log_ab_event(uid, "purchase", plan_key)
    lang = await get_lang(uid)
    label = t(lang, plan["label_key"])
    await message.answer(
        t(lang, "premium_activated",
          tier="Premium",
          label=label,
          until=until.strftime('%d.%m.%Y'),
          benefits=t(lang, "benefit_premium")),
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
    online = get_online_count()
    online_hint = f"\n🟢 {t(lang, 'online_count', count=online)}" if online > 0 else ""
    await message.answer(t(lang, "searching_anon") + online_hint, reply_markup=kb_cancel_search(lang))
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
        asyncio.create_task(grant_referral_bonus(uid))
        asyncio.create_task(grant_referral_bonus(partner))
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
    if not u or not u.get("mode"):
        await state.set_state(Reg.age)
        await message.answer(t(lang, "reg_age_prompt"), reply_markup=kb_cancel_reg(lang))
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
    await state.clear()
    await message.answer(t(lang, "reg_done"), reply_markup=kb_main(lang))
    # Онбординг-тур для новых пользователей
    u_check = await get_user(uid)
    if u_check and u_check.get("total_chats", 0) == 0:
        await message.answer(t(lang, "welcome_tour"))
        await log_ab_event(uid, "onboarding_shown")
    # Автозапуск поиска
    q_len = len(get_queue(mode, False)) + len(get_queue(mode, True))
    status = t(lang, "queue_searching")
    await message.answer(
        t(lang, "queue_info", mode=t(lang, f"mode_{mode}"), count=q_len, status=status),
        reply_markup=kb_cancel_search(lang)
    )
    await do_find(uid, state)

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
        # Онбординг-тур для новых пользователей
        u = await get_user(uid)
        if u and u.get("total_chats", 0) == 0:
            await callback.message.answer(t(lang, "welcome_tour"))
            await log_ab_event(uid, "onboarding_shown")
        mode = u.get("mode", "simple") if u else "simple"
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
    if _last_relay_msg_id.get(uid) == message.message_id:
        return
    _last_relay_msg_id[uid] = message.message_id
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
    msg_count[uid] = [ts for ts in msg_count[uid] if (now - ts).total_seconds() < 5]
    if len(msg_count[uid]) >= 5:
        await message.answer(t(lang, "spam_warning"))
        return
    msg_count[uid].append(now)
    last_msg_time[uid] = last_msg_time[partner] = now
    # --- Translation for cross-language chats ---
    p_lang = await get_lang(partner)
    need_translate = lang != p_lang
    partner_premium = False
    partner_auto_translate = True
    if need_translate:
        partner_premium = await is_premium(partner)
        p_user = await get_user(partner)
        partner_auto_translate = p_user.get("auto_translate", True) if p_user else True

    async def _translate_text(text: str | None) -> str | None:
        """Translate text for partner if needed. Returns formatted or original."""
        if not text or not need_translate:
            return text
        if not partner_premium or not partner_auto_translate:
            # Send one-time notice to non-premium partner
            if (partner, uid) not in translate_notice_sent:
                translate_notice_sent.add((partner, uid))
                try:
                    await bot.send_message(partner, t(p_lang, "translate_premium_notice"))
                except Exception:
                    pass
            return text
        translated = await translate_message(text, lang, p_lang)
        if translated and translated.strip() != text.strip():
            return f"{translated}\n\n💬 {text}"
        return text

    # --- Gift prompt: premium user sees option to gift non-premium partner ---
    if need_translate and (uid, partner) not in gift_prompt_sent:
        my_premium = await is_premium(uid)
        if my_premium and not partner_premium:
            gift_prompt_sent.add((uid, partner))
            try:
                await bot.send_message(uid,
                    t(lang, "gift_prompt"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text=f"🌹 {t(lang, 'gift_rose')} — {GIFTS['rose']['stars']}⭐", callback_data=f"gift:rose:{partner}"),
                            InlineKeyboardButton(text=f"💎 {t(lang, 'gift_diamond')} — {GIFTS['diamond']['stars']}⭐", callback_data=f"gift:diamond:{partner}"),
                        ],
                        [InlineKeyboardButton(text=f"👑 {t(lang, 'gift_crown')} — {GIFTS['crown']['stars']}⭐", callback_data=f"gift:crown:{partner}")],
                    ])
                )
            except Exception: pass

    try:
        if message.text:
            relay_text = await _translate_text(message.text)
            await bot.send_message(partner, relay_text)
        elif message.sticker:
            await bot.send_sticker(partner, message.sticker.file_id)
        elif message.photo:
            cap = await _translate_text(message.caption)
            sent = await bot.send_photo(partner, message.photo[-1].file_id, caption=cap)
            # Фото-реакция получателю
            try:
                await bot.set_message_reaction(
                    chat_id=uid,
                    message_id=message.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="📸")],
                )
            except Exception:
                pass
            try:
                await bot.set_message_reaction(
                    chat_id=partner,
                    message_id=sent.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="😍")],
                )
            except Exception:
                pass
        elif message.voice:
            await bot.send_voice(partner, message.voice.file_id)
        elif message.video:
            cap = await _translate_text(message.caption)
            sent = await bot.send_video(partner, message.video.file_id, caption=cap)
            try:
                await bot.set_message_reaction(
                    chat_id=uid,
                    message_id=message.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="🎬")],
                )
            except Exception:
                pass
            try:
                await bot.set_message_reaction(
                    chat_id=partner,
                    message_id=sent.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="🔥")],
                )
            except Exception:
                pass
        elif message.video_note:
            sent = await bot.send_video_note(partner, message.video_note.file_id)
            try:
                await bot.set_message_reaction(
                    chat_id=partner,
                    message_id=sent.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="👀")],
                )
            except Exception:
                pass
        elif message.document:
            cap = await _translate_text(message.caption)
            await bot.send_document(partner, message.document.file_id, caption=cap)
        elif message.audio:
            await bot.send_audio(partner, message.audio.file_id)
    except Exception as e:
        logger.warning(f"Relay failed {uid}->{partner}: {e}")

# ====================== ПОДАРКИ В ЧАТЕ ======================
@dp.callback_query(F.data.startswith("gift:"), StateFilter("*"))
async def gift_select(callback: types.CallbackQuery):
    uid = callback.from_user.id
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    gift_type = parts[1]
    partner_uid = int(parts[2])
    gift = GIFTS.get(gift_type)
    if not gift:
        await callback.answer()
        return
    lang = await get_lang(uid)
    # Send invoice for the gift
    await bot.send_invoice(
        chat_id=uid,
        title=t(lang, f"gift_{gift_type}_title"),
        description=t(lang, "gift_desc", days=gift["days"]),
        payload=f"gift_{gift_type}_{partner_uid}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{gift['emoji']} Gift", amount=gift["stars"])],
    )
    await callback.answer()


# ====================== ЖАЛОБА ======================
@dp.callback_query(F.data == "rep:cancel", StateFilter(Complaint.reason))
async def complaint_cancel(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    # If user is still in a chat, restore chatting state; otherwise clear
    if uid in active_chats:
        await state.set_state(Chat.chatting)
    else:
        await state.clear()
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
    if _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
    await ensure_user(uid)
    u = await get_user(uid)
    if not u or not u.get("name"):
        await message.answer(t(lang, "profile_not_filled"), reply_markup=kb_main(lang))
        return
    user_tier = await get_premium_tier(uid)
    show_badge = u.get("show_premium", True)
    if user_tier:
        if uid == ADMIN_ID or u.get("premium_until") == "permanent":
            premium_line = "💎 " + t(lang, "premium_eternal", tier="Premium")
        else:
            p_until = u.get("premium_until") or ""
            try:
                until = datetime.fromisoformat(p_until)
                premium_line = "💎 " + t(lang, "premium_until_date", tier="Premium", until=until.strftime('%d.%m.%Y'))
            except Exception:
                premium_line = "💎 Premium"
    else:
        premium_line = ""
    badge = " ⭐" if (user_tier and show_badge) else ""
    not_set = t(lang, "not_set")
    raw_interests = (u.get("interests") or "").split(",")
    interests_str = ", ".join(t(lang, k.strip()) for k in raw_interests if k.strip()) or not_set
    # Level / streak / progress
    level = u.get("level", 0)
    level_name = t(lang, f"level_{level}")
    level_info = t(lang, "profile_level", level=level, name=level_name)
    streak = u.get("streak_days", 0)
    streak_info = t(lang, "profile_streak", days=streak) if streak > 0 else ""
    total_chats = u.get("total_chats", 0)
    if level < len(LEVEL_THRESHOLDS) - 1:
        next_threshold = LEVEL_THRESHOLDS[level + 1]
        current_threshold = LEVEL_THRESHOLDS[level]
        progress_current = total_chats - current_threshold
        progress_needed = next_threshold - current_threshold
        pct = min(round(progress_current / max(progress_needed, 1) * 100), 99)
        bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
        progress_info = t(lang, "profile_progress", current=total_chats, next=next_threshold, pct=pct) + f"\n{bar}"
    else:
        progress_info = t(lang, "profile_progress_max")
    warns = u.get("warn_count", 0)
    warns_line = f"⚠️ Предупреждений: {warns}\n" if warns > 0 else ""
    profile_text = t(lang, "profile_text",
        badge=badge,
        name=u.get("name") or not_set,
        age=f"{u['age']} {t(lang, 'age_suffix')}" if u.get("age") else not_set,
        gender=t(lang, f"gender_{u.get('gender') or 'other'}"),
        mode=t(lang, f"mode_{u.get('mode') or 'simple'}"),
        interests=interests_str,
        rating=get_rating(u),
        likes=u.get("likes", 0),
        chats=total_chats,
        warns_line=warns_line,
        premium_line=premium_line,
        level_info=level_info,
        streak_info=streak_info,
        progress_info=progress_info,
    )
    await message.answer(profile_text, reply_markup=kb_edit(lang, show_premium_btn=not user_tier))

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
    if _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
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
    elif key == "search_range":
        current = u.get("search_range", "local")
        new_val = "global" if current == "local" else "local"
        await update_user(uid, search_range=new_val)
    elif key == "auto_translate":
        if not await is_premium(uid):
            await callback.answer(t(lang, "settings_premium_only"), show_alert=True)
            return
        await update_user(uid, auto_translate=not u.get("auto_translate", True))
    elif key == "translate_locked":
        await callback.answer(t(lang, "settings_translate_locked"), show_alert=True)
        return
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
    if _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
    await message.answer(t(lang, "help_text"), reply_markup=kb_main(lang))

@dp.message(Command("restart"), StateFilter("*"))
async def cmd_restart(message: types.Message, state: FSMContext):
    await cmd_start(message, state)

@dp.callback_query(F.data == "noop", StateFilter("*"))
async def noop(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("rate:"), StateFilter("*"))
async def rate_chat(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await get_lang(uid)
    parts = callback.data.split(":")
    partner_uid = int(parts[1])
    stars = int(parts[2])
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                exists = await conn.fetchval(
                    "SELECT 1 FROM chat_ratings WHERE uid=$1 AND partner_uid=$2 AND created_at > NOW() - INTERVAL '1 minute' FOR UPDATE",
                    uid, partner_uid
                )
                if exists:
                    await callback.answer(t(lang, "rate_already"), show_alert=True)
                    return
                await conn.execute(
                    "INSERT INTO chat_ratings (uid, partner_uid, stars) VALUES ($1, $2, $3)",
                    uid, partner_uid, stars
                )
        try:
            await callback.message.edit_text(t(lang, "rate_thanks", stars=stars))
        except Exception:
            pass
        await callback.answer(t(lang, "rate_thanks", stars=stars))
    except Exception:
        await callback.answer()


@dp.callback_query(F.data.startswith("adclick:"), StateFilter("*"))
async def ad_click_handler(callback: types.CallbackQuery):
    """Трекинг клика по рекламе + отправка ссылки."""
    uid = callback.from_user.id
    lang = await get_lang(uid)
    parts = callback.data.split(":")
    try:
        idx = int(parts[1])
        source = parts[2] if len(parts) > 2 else "search"
    except (ValueError, IndexError):
        await callback.answer()
        return
    u = await get_user(uid)
    mode = u.get("mode", "simple") if u else "simple"
    ads = _filter_ads(lang, mode)
    if not ads or idx >= len(ads):
        await callback.answer()
        return
    ad = ads[idx]
    # Логируем клик
    await _log_ad_event(uid, ad["text_key"], "click", source)
    # Отправляем ссылку (callback.answer(url=) работает только для игр,
    # поэтому отправляем ссылку сообщением)
    await callback.answer()
    await bot.send_message(uid, ad["url"], disable_web_page_preview=False)


# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    # Create Telegraph legal pages on startup
    try:
        legal_urls = await create_legal_pages()
        logger.info(f"Telegraph legal pages ready: {legal_urls}")
    except Exception as e:
        logger.error(f"Failed to create Telegraph pages: {e}")
    db.init(db_pool, ADMIN_ID)
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
        get_ai_history=get_ai_history,
        save_ai_message=save_ai_message,
        clear_ai_history=clear_ai_history,
        get_ai_notes=get_ai_notes,
        save_ai_notes=save_ai_notes,
        db_pool=db_pool,
        send_ad_message=send_ad_message,
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
        PARTNER_ADS=PARTNER_ADS,
        filter_ads=_filter_ads,
        get_chat_topics=get_chat_topics,
    )
    energy_shop_module.setup(
        bot=bot,
        get_user=get_user,
        update_user=update_user,
        get_lang=get_lang,
    )
    dp.include_router(ai_chat.router)
    dp.include_router(energy_shop_module.router)
    dp.include_router(admin_module.router)
    asyncio.create_task(admin_module.inactivity_checker())
    asyncio.create_task(admin_module.reminder_task())
    asyncio.create_task(admin_module.winback_task())
    asyncio.create_task(admin_module.streak_and_ai_push_task())
    logger.info("MatchMe запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
