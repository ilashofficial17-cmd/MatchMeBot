import asyncio
import os
import logging
from telegraph_pages import create_legal_pages
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand,
)
import asyncpg
import moderation
from locales import t
from keyboards import (
    CHANNEL_ID,
    kb_main, kb_privacy, kb_cancel_reg,
    kb_gender, kb_mode, kb_cancel_search, kb_chat, kb_search_gender,
    kb_after_chat, kb_channel_bonus, kb_ai_chat,
    kb_interests, kb_complaint, kb_edit, kb_complaint_action,
    kb_premium, kb_energy_shop,
)
import db
from constants import (
    PREMIUM_PLANS, AB_PRICE_DISCOUNT_B, GIFTS, ENERGY_PACKS,
    get_plan_price, get_chat_topics,
    LEVEL_THRESHOLDS, LEVEL_NAMES, STREAK_BONUSES,
    PARTNER_ADS, filter_ads as _filter_ads,
)
import ai_chat
import admin as admin_module
import energy_shop as energy_shop_module
import redis_state

# monitoring.py — безопасный импорт
try:
    import monitoring
    _has_monitoring = True
except ImportError:
    monitoring = None
    _has_monitoring = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("matchme")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))


# Constants imported from constants.py: PREMIUM_PLANS, GIFTS, PRICE_MULTIPLIERS, etc.

bot = Bot(token=BOT_TOKEN)
# Storage: RedisStorage if REDIS_URL available, else MemoryStorage (fallback)
_use_redis = False  # set in main() after init_redis
dp = Dispatcher(storage=MemoryStorage())  # replaced in main() if Redis available

db_pool = None
# --- In-memory only (latency-critical or non-critical, safe to lose on restart) ---
msg_count = {}
translate_notice_sent = set()  # (uid, partner) — one-time translation upsell per chat
gift_prompt_sent = set()  # (uid, partner) — one-time gift prompt per chat
last_ai_msg = {}  # uid -> datetime последнего сообщения в AI чат
# --- Fallback dicts (used only when Redis is unavailable) ---
_fb_active_chats = {}
_fb_waiting_anon = set()
_fb_waiting_simple = set()
_fb_waiting_flirt = set()
_fb_waiting_kink = set()
_fb_waiting_simple_premium = set()
_fb_waiting_flirt_premium = set()
_fb_waiting_kink_premium = set()
_fb_last_msg_time = {}
_fb_chat_logs = {}
_fb_ai_sessions = {}
_fb_mutual_likes = {}
_fb_liked_chats = set()
_fb_pairing_lock = asyncio.Lock()


# GIFTS, STOP_WORDS — see constants.py


# ====================== БД ======================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=20,
        command_timeout=10,
        max_inactive_connection_lifetime=300,
    )
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
            ("rate_energy_today", "INTEGER DEFAULT 0"),
            ("daily_bonus_claimed", "BOOLEAN DEFAULT FALSE"),
            ("return_gift_stage", "INTEGER DEFAULT 0"),
            ("return_gift_given", "TIMESTAMP DEFAULT NULL"),
            ("return_gifts_total", "INTEGER DEFAULT 0"),
            ("bonus_energy", "INTEGER DEFAULT 0"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}")
            except Exception: pass
        # Одноразовая миграция: перенести отрицательный ai_energy_used в bonus_energy
        try:
            await conn.execute("""
                UPDATE users SET bonus_energy = ABS(ai_energy_used), ai_energy_used = 0
                WHERE ai_energy_used < 0
            """)
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
            CREATE TABLE IF NOT EXISTS user_purchased_media (
                uid BIGINT NOT NULL,
                character_id TEXT NOT NULL,
                media_type TEXT NOT NULL,
                purchased_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (uid, character_id, media_type)
            )
        """)
        try:
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_purchased_media_uid ON user_purchased_media(uid)")
        except Exception: pass

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

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                uid BIGINT NOT NULL,
                achievement_id TEXT NOT NULL,
                unlocked_at TIMESTAMP DEFAULT NOW(),
                energy_claimed BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (uid, achievement_id)
            )
        """)
        try:
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_achievements_uid ON achievements(uid)")
        except Exception: pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_quests (
                uid BIGINT NOT NULL,
                quest_date DATE NOT NULL DEFAULT CURRENT_DATE,
                quest_id TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                goal INTEGER NOT NULL DEFAULT 1,
                reward INTEGER NOT NULL DEFAULT 2,
                claimed BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (uid, quest_date, quest_id)
            )
        """)
        try:
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_quests_uid_date ON daily_quests(uid, quest_date)")
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
        if _use_redis:
            await redis_state.set_active_chat(uid1, uid2)
        else:
            _fb_active_chats[uid1] = uid2
            _fb_active_chats[uid2] = uid1
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
check_achievements = db.check_achievements
generate_daily_quests = db.generate_daily_quests
increment_quest = db.increment_quest


# ====================== SOCIAL PROOF ======================
async def get_online_count() -> int:
    """Real online count: active chats + people in queues."""
    if _use_redis:
        pairs, searching = await redis_state.get_online_count()
        return pairs * 2 + searching
    chatting = len(_fb_active_chats) // 2
    in_queue = sum(len(q) for q in _get_fb_all_queues())
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


async def _notify_achievements(uid):
    """Проверяет ачивки и отправляет уведомления о новых."""
    try:
        new_achs = await check_achievements(uid)
        if new_achs:
            lang = await get_lang(uid)
            for ach_id in new_achs:
                try:
                    await bot.send_message(uid, t(lang, f"ach_{ach_id}"))
                except Exception:
                    pass
    except Exception:
        pass


async def _quest_progress(uid, quest_type):
    """Инкрементирует квест и уведомляет при claim."""
    try:
        claimed = await increment_quest(uid, quest_type)
        if claimed:
            lang = await get_lang(uid)
            for qid in claimed:
                if qid == "all_done":
                    from constants import QUEST_ALL_DONE_BONUS
                    await bot.send_message(uid, t(lang, "quest_all_done", bonus=QUEST_ALL_DONE_BONUS))
                else:
                    await bot.send_message(uid, t(lang, "quest_claimed", quest=qid))
    except Exception:
        pass


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
async def clear_chat_log(uid1, uid2):
    if _use_redis:
        await redis_state.delete_chat_log(uid1, uid2)
    else:
        key = (min(uid1, uid2), max(uid1, uid2))
        if key in _fb_chat_logs:
            del _fb_chat_logs[key]

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
def _get_fb_all_queues():
    """Fallback in-memory queues."""
    return [_fb_waiting_anon, _fb_waiting_simple, _fb_waiting_flirt, _fb_waiting_kink,
            _fb_waiting_simple_premium, _fb_waiting_flirt_premium, _fb_waiting_kink_premium]

def _get_fb_queue(mode, premium=False):
    """Fallback: get specific in-memory queue."""
    if premium:
        if mode == "simple": return _fb_waiting_simple_premium
        if mode == "flirt": return _fb_waiting_flirt_premium
        if mode == "kink": return _fb_waiting_kink_premium
    else:
        if mode == "simple": return _fb_waiting_simple
        if mode == "flirt": return _fb_waiting_flirt
        if mode == "kink": return _fb_waiting_kink
    return _fb_waiting_simple

def get_rating(u):
    return u.get("likes", 0) - u.get("dislikes", 0)

async def cleanup(uid, state=None):
    if _use_redis:
        await redis_state.remove_from_queues(uid)
        partner = await redis_state.disconnect(uid)
    else:
        async with _fb_pairing_lock:
            for q in _get_fb_all_queues():
                q.discard(uid)
            partner = _fb_active_chats.pop(uid, None)
            if partner:
                _fb_active_chats.pop(partner, None)
    if partner:
        await remove_chat_from_db(uid, partner)
        await clear_chat_log(uid, partner)
    if _use_redis:
        await redis_state.delete_ai_session(uid)
    else:
        _fb_ai_sessions.pop(uid, None)
    if state: await state.clear()
    return partner

async def unavailable(message: types.Message, lang: str, reason_key: str):
    await message.answer(t(lang, "unavailable", reason=t(lang, reason_key)))

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
        BotCommand(command="energy", description="Магазин энергии"),
        BotCommand(command="quests", description="Задания"),
        BotCommand(command="help", description="Помощь"),
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
        BotCommand(command="energy", description="Energy shop"),
        BotCommand(command="quests", description="Quests"),
        BotCommand(command="help", description="Help"),
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
        BotCommand(command="energy", description="Tienda de energía"),
        BotCommand(command="quests", description="Misiones"),
        BotCommand(command="help", description="Ayuda"),
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

@dp.errors()
async def error_handler(event, exception):
    logger.error(f"Update error: {exception}", exc_info=True)
    if _has_monitoring:
        monitoring.metrics.record_error()
    return True

# ====================== ЗАПУСК ======================
async def main():
    global _use_redis

    await init_db()
    # --- Redis init (with fallback to in-memory) ---
    _use_redis = await redis_state.init_redis()
    if _use_redis:
        from aiogram.fsm.storage.redis import RedisStorage
        redis_url = os.environ.get("REDIS_URL")
        redis_storage = RedisStorage.from_url(redis_url)
        dp.fsm.storage = redis_storage
        logger.info("FSM switched to RedisStorage")
    else:
        logger.warning("Running with MemoryStorage (no Redis)")

    # --- Monitoring init ---
    if _has_monitoring:
        monitoring.init(bot=bot, db_pool=db_pool, admin_id=ADMIN_ID, redis_pool=redis_state.redis_pool if _use_redis else None)
        asyncio.create_task(monitoring.monitoring_task())
        asyncio.create_task(monitoring.alert_checker())
        asyncio.create_task(monitoring.openrouter_health_probe())
        logger.info("Monitoring tasks started")

    # Create Telegraph legal pages on startup
    try:
        legal_urls = await create_legal_pages()
        logger.info(f"Telegraph legal pages ready: {legal_urls}")
    except Exception as e:
        logger.error(f"Failed to create Telegraph pages: {e}")
    db.init(db_pool, ADMIN_ID)
    moderation.init(bot, db_pool, ADMIN_ID)
    await moderation.migrate_db()
    await moderation.load_stop_words()
    await set_commands()

    # ── Import and initialise extracted modules ──────────────────────────
    import chat as chat_module
    import matching as matching_module
    import registration as registration_module
    import profile as profile_module
    import payments as payments_module
    from constants import MAX_BONUS_ENERGY

    # chat.py — no cross-module deps at init time
    chat_module.init(
        bot=bot, dp=dp, db_pool=db_pool,
        use_redis=_use_redis, admin_id=ADMIN_ID,
        fb_active_chats=_fb_active_chats,
        fb_pairing_lock=_fb_pairing_lock,
        get_all_queues=_get_fb_all_queues,
        fb_last_msg_time=_fb_last_msg_time,
        fb_chat_logs=_fb_chat_logs,
        fb_mutual_likes=_fb_mutual_likes,
        fb_liked_chats=_fb_liked_chats,
        get_user=get_user, get_lang=get_lang,
        update_user=update_user, increment_user=increment_user,
        is_premium=is_premium, get_premium_tier=get_premium_tier,
        cleanup=cleanup, get_rating=get_rating,
        notify_achievements=_notify_achievements,
        quest_progress=_quest_progress,
        log_ab_event=log_ab_event,
        check_achievements=check_achievements,
        send_ad_message=send_ad_message,
        log_ad_event=_log_ad_event,
        kb_main=kb_main, kb_chat=kb_chat,
        kb_cancel_search=kb_cancel_search,
        kb_after_chat=kb_after_chat,
        kb_channel_bonus=kb_channel_bonus,
        kb_complaint=kb_complaint,
        kb_complaint_action=kb_complaint_action,
        check_rate_limit=monitoring.check_rate_limit if _has_monitoring else None,
    )

    # matching.py — needs chat.save_chat_to_db
    matching_module.init(
        bot=bot, dp=dp, db_pool=db_pool, use_redis=_use_redis,
        fb_active_chats=_fb_active_chats,
        fb_pairing_lock=_fb_pairing_lock,
        get_all_queues=_get_fb_all_queues,
        get_fb_queue=_get_fb_queue,
        fb_waiting_anon=_fb_waiting_anon,
        fb_last_msg_time=_fb_last_msg_time,
        fb_ai_sessions=_fb_ai_sessions,
        get_user=get_user, get_lang=get_lang,
        ensure_user=ensure_user, update_user=update_user,
        increment_user=increment_user, is_premium=is_premium,
        get_premium_tier=get_premium_tier, is_banned=is_banned,
        cleanup=cleanup,
        needs_onboarding=registration_module.needs_onboarding,
        unavailable=unavailable,
        get_rating=get_rating,
        update_streak=update_streak,
        notify_achievements_fn=_notify_achievements,
        quest_progress_fn=_quest_progress,
        log_ab_event=log_ab_event,
        grant_referral_bonus=grant_referral_bonus,
        get_online_count=get_online_count,
        save_chat_to_db=chat_module.save_chat_to_db,
        get_premium_badge=get_premium_badge,
        check_rate_limit=monitoring.check_rate_limit if _has_monitoring else None,
        kb_main=kb_main,
        kb_cancel_search=kb_cancel_search,
        kb_ai_chat=kb_ai_chat,
        kb_chat=kb_chat,
        kb_cancel_reg=kb_cancel_reg,
    )

    # chat ← matching post-init setter (breaks circular dep)
    chat_module.set_do_find(matching_module.do_find)

    # registration.py
    registration_module.init(
        bot=bot, dp=dp, db_pool=db_pool,
        use_redis=_use_redis, admin_id=ADMIN_ID,
        fb_active_chats=_fb_active_chats,
        fb_ai_sessions=_fb_ai_sessions,
        fb_pairing_lock=_fb_pairing_lock,
        get_all_queues=_get_fb_all_queues,
        get_user=get_user, get_lang=get_lang,
        ensure_user=ensure_user, update_user=update_user,
        is_premium=is_premium, is_banned=is_banned,
        cleanup=cleanup, get_age_joke=get_age_joke,
        get_premium_badge=get_premium_badge,
        get_online_count=get_online_count,
        update_streak=update_streak,
        notify_achievements_fn=_notify_achievements,
        quest_progress_fn=_quest_progress,
        log_ab_event=log_ab_event,
        get_ab_group=get_ab_group,
        check_channel_sub_fn=check_channel_subscription,
        kb_main=kb_main,
        kb_privacy=kb_privacy,
        kb_accept_all=None,
        kb_cancel_reg=kb_cancel_reg,
        kb_gender=kb_gender,
        kb_mode=kb_mode,
        kb_interests=kb_interests,
        kb_cancel_search=kb_cancel_search,
        kb_channel_bonus=kb_channel_bonus,
        get_fb_queue=_get_fb_queue,
    )
    registration_module.set_do_find(matching_module.do_find)

    # profile.py
    profile_module.init(
        bot=bot, db_pool=db_pool,
        use_redis=_use_redis, admin_id=ADMIN_ID,
        get_user=get_user, get_lang=get_lang,
        update_user=update_user, is_premium=is_premium,
        get_premium_tier=get_premium_tier,
        get_rating=get_rating,
        get_premium_badge=get_premium_badge,
        get_age_joke=get_age_joke,
        cleanup=cleanup,
        needs_onboarding_fn=registration_module.needs_onboarding,
        unavailable_fn=unavailable,
        kb_settings_fn=kb_settings,
        kb_main=kb_main,
        kb_cancel_reg=kb_cancel_reg,
        kb_gender=kb_gender,
        kb_mode=kb_mode,
        kb_interests=kb_interests,
        kb_search_gender=kb_search_gender,
        kb_edit=kb_edit,
        kb_energy_shop=kb_energy_shop,
        kb_premium=kb_premium,
        LEVEL_THRESHOLDS=LEVEL_THRESHOLDS,
        LEVEL_NAMES=LEVEL_NAMES,
        STREAK_BONUSES=STREAK_BONUSES,
        get_all_queues=_get_fb_all_queues,
        fb_ai_sessions=_fb_ai_sessions,
    )

    # payments.py
    payments_module.init(
        bot=bot, db_pool=db_pool,
        use_redis=_use_redis, admin_id=ADMIN_ID,
        get_user=get_user, get_lang=get_lang,
        update_user=update_user, is_premium=is_premium,
        get_premium_tier=get_premium_tier,
        log_ab_event=log_ab_event,
        get_ab_group=get_ab_group,
        needs_onboarding_fn=registration_module.needs_onboarding,
        unavailable_fn=unavailable,
        kb_main=kb_main,
        kb_premium=kb_premium,
        PREMIUM_PLANS=PREMIUM_PLANS,
        GIFTS=GIFTS,
        ENERGY_PACKS=ENERGY_PACKS,
        MAX_BONUS_ENERGY=MAX_BONUS_ENERGY,
        get_plan_price=get_plan_price,
        AB_PRICE_DISCOUNT_B=AB_PRICE_DISCOUNT_B,
    )

    # ai_chat — now references cmd_find from matching, show_settings from profile
    ai_chat.init(
        bot=bot,
        ai_sessions=_fb_ai_sessions,
        last_ai_msg=last_ai_msg,
        pairing_lock=_fb_pairing_lock,
        get_all_queues=_get_fb_all_queues,
        active_chats=_fb_active_chats,
        get_user=get_user,
        ensure_user=ensure_user,
        get_premium_tier=get_premium_tier,
        update_user=update_user,
        cmd_find=matching_module.cmd_find,
        show_settings=profile_module.show_settings,
        get_ai_history=get_ai_history,
        save_ai_message=save_ai_message,
        clear_ai_history=clear_ai_history,
        get_ai_notes=get_ai_notes,
        save_ai_notes=save_ai_notes,
        db_pool=db_pool,
        send_ad_message=send_ad_message,
        use_redis=_use_redis,
        check_rate_limit=monitoring.check_rate_limit if _has_monitoring else None,
    )
    admin_module.init(
        bot=bot,
        dp=dp,
        db_pool=db_pool,
        admin_id=ADMIN_ID,
        active_chats=_fb_active_chats,
        ai_sessions=_fb_ai_sessions,
        last_ai_msg=last_ai_msg,
        pairing_lock=_fb_pairing_lock,
        get_all_queues=_get_fb_all_queues,
        chat_logs=_fb_chat_logs,
        last_msg_time=_fb_last_msg_time,
        msg_count=msg_count,
        mutual_likes=_fb_mutual_likes,
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
        use_redis=_use_redis,
    )
    energy_shop_module.setup(
        bot=bot,
        get_user=get_user,
        update_user=update_user,
        get_lang=get_lang,
    )
    if _has_monitoring:
        dp.message.middleware(monitoring.MetricsMiddleware())
        dp.callback_query.middleware(monitoring.MetricsMiddleware())
    # Extracted modules (order matters: registration → matching → chat → profile → payments)
    dp.include_router(registration_module.router)
    dp.include_router(matching_module.router)
    dp.include_router(chat_module.router)
    dp.include_router(profile_module.router)
    dp.include_router(payments_module.router)
    dp.include_router(ai_chat.router)
    dp.include_router(energy_shop_module.router)

    # Fallback router: dismiss spinner on stale inline keyboards
    # Must be last so it doesn't intercept valid callbacks
    from aiogram import Router as _FallbackRouter
    _fb_router = _FallbackRouter(name="fallback")
    @_fb_router.callback_query()
    async def _fallback_callback(callback: types.CallbackQuery):
        await callback.answer()
    dp.include_router(_fb_router)

    # admin_module.router перенесён в admin_bot/ — НЕ подключаем здесь
    # tasks (reminder, winback, streak) перенесены в admin_bot/tasks/ — НЕ запускаем здесь
    # inactivity_checker остаётся — reads from Redis when available
    asyncio.create_task(admin_module.inactivity_checker())
    logger.info("MatchMe запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
