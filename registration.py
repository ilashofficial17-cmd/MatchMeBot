"""
Registration & onboarding logic extracted from bot.py.

All external dependencies are injected via init() to avoid circular imports.
The do_find reference is set later via set_do_find() after matching.py is ready.
"""

import asyncio
import logging

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from telegraph_pages import get_legal_url
from locales import t, TEXTS, LANG_BUTTONS
from states import Reg, Chat, Rules
from constants import STREAK_BONUSES, LEVEL_NAMES
import redis_state

logger = logging.getLogger("matchme")

router = Router()

# ---------------------------------------------------------------------------
# Module-level references populated by init() / set_do_find()
# ---------------------------------------------------------------------------
_bot = None
_dp = None
_db_pool = None
_use_redis = False
_admin_id = None

# Fallback dicts (used only when Redis is unavailable)
_fb_active_chats = {}
_fb_ai_sessions = {}
_fb_pairing_lock = None
_get_all_queues = None  # callable returning list of sets

# Helper functions
_get_user = None
_get_lang = None
_ensure_user = None
_update_user = None
_is_premium = None
_is_banned = None
_cleanup = None
_get_age_joke = None
_get_premium_badge = None
_get_online_count = None
_update_streak = None
_notify_achievements_fn = None
_quest_progress_fn = None
_log_ab_event = None
_get_ab_group = None
_check_channel_sub_fn = None

# Keyboards
_kb_main = None
_kb_privacy = None
_kb_accept_all = None
_kb_cancel_reg = None
_kb_gender = None
_kb_mode = None
_kb_interests = None
_kb_cancel_search = None
_kb_channel_bonus = None

# do_find — set later via set_do_find() to break circular dependency
_do_find = None

# get_fb_queue — for queue length display in registration
_get_fb_queue = None


def init(
    *,
    bot,
    dp,
    db_pool,
    use_redis,
    admin_id,
    # Fallback dicts
    fb_active_chats,
    fb_ai_sessions,
    fb_pairing_lock,
    get_all_queues,
    # Helper functions
    get_user,
    get_lang,
    ensure_user,
    update_user,
    is_premium,
    is_banned,
    cleanup,
    get_age_joke,
    get_premium_badge,
    get_online_count,
    update_streak,
    notify_achievements_fn,
    quest_progress_fn,
    log_ab_event,
    get_ab_group,
    check_channel_sub_fn,
    # Keyboards
    kb_main,
    kb_privacy,
    kb_accept_all,
    kb_cancel_reg,
    kb_gender,
    kb_mode,
    kb_interests,
    kb_cancel_search,
    kb_channel_bonus,
    # Queue helper for fallback mode
    get_fb_queue=None,
):
    """Dependency injection — must be called before the router is used."""
    global _bot, _dp, _db_pool, _use_redis, _admin_id
    global _fb_active_chats, _fb_ai_sessions, _fb_pairing_lock, _get_all_queues
    global _get_user, _get_lang, _ensure_user, _update_user
    global _is_premium, _is_banned, _cleanup
    global _get_age_joke, _get_premium_badge, _get_online_count, _update_streak
    global _notify_achievements_fn, _quest_progress_fn
    global _log_ab_event, _get_ab_group, _check_channel_sub_fn
    global _kb_main, _kb_privacy, _kb_accept_all
    global _kb_cancel_reg, _kb_gender, _kb_mode, _kb_interests
    global _kb_cancel_search, _kb_channel_bonus
    global _get_fb_queue

    _bot = bot
    _dp = dp
    _db_pool = db_pool
    _use_redis = use_redis
    _admin_id = admin_id

    _fb_active_chats = fb_active_chats
    _fb_ai_sessions = fb_ai_sessions
    _fb_pairing_lock = fb_pairing_lock
    _get_all_queues = get_all_queues

    _get_user = get_user
    _get_lang = get_lang
    _ensure_user = ensure_user
    _update_user = update_user
    _is_premium = is_premium
    _is_banned = is_banned
    _cleanup = cleanup
    _get_age_joke = get_age_joke
    _get_premium_badge = get_premium_badge
    _get_online_count = get_online_count
    _update_streak = update_streak
    _notify_achievements_fn = notify_achievements_fn
    _quest_progress_fn = quest_progress_fn
    _log_ab_event = log_ab_event
    _get_ab_group = get_ab_group
    _check_channel_sub_fn = check_channel_sub_fn

    _kb_main = kb_main
    _kb_privacy = kb_privacy
    _kb_accept_all = kb_accept_all
    _kb_cancel_reg = kb_cancel_reg
    _kb_gender = kb_gender
    _kb_mode = kb_mode
    _kb_interests = kb_interests
    _kb_cancel_search = kb_cancel_search
    _kb_channel_bonus = kb_channel_bonus

    _get_fb_queue = get_fb_queue


def set_do_find(fn):
    """Set do_find reference AFTER matching.py is initialised (avoids circular dep)."""
    global _do_find
    _do_find = fn


# ---------------------------------------------------------------------------
# Locale helpers
# ---------------------------------------------------------------------------

def _all(key):
    """All language variants for a locale key — for F.text.in_() filters."""
    return {TEXTS[lang][key] for lang in TEXTS if key in TEXTS[lang]}


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Unavailable helper (local)
# ---------------------------------------------------------------------------

async def _unavailable(message: types.Message, lang: str, reason_key: str):
    await message.answer(t(lang, "unavailable", reason=t(lang, reason_key)))


# ---------------------------------------------------------------------------
# needs_onboarding — module-level function, other modules call
#   registration.needs_onboarding(message, state)
# ---------------------------------------------------------------------------

async def needs_onboarding(message: types.Message, state: FSMContext) -> bool:
    """If user hasn't accepted rules, redirect to /start. Returns True if redirected."""
    uid = message.from_user.id
    await _ensure_user(uid)
    u = await _get_user(uid)
    if not u or not u.get("accepted_rules") or not u.get("accepted_privacy"):
        await cmd_start(message, state)
        return True
    # Default lang to 'ru' if somehow missing — never auto-detect for existing users
    if not u.get("lang"):
        await _update_user(uid, lang="ru")
    return False


# ---------------------------------------------------------------------------
# BLOCKED_TEXTS — blocked name patterns (button labels that are not valid names)
# ---------------------------------------------------------------------------

BLOCKED_TEXTS = (
    _all("btn_search") | _all("btn_find") | _all("btn_profile") |
    _all("btn_settings") | _all("btn_help") | _all("btn_ai_chat")
)


# ======================== /start ========================

@router.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await _cleanup(uid, state)
    await _ensure_user(uid)

    # Обработка реферальной ссылки /start ref_<uid>
    args = (message.text or "").split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1][4:])
            if referrer_id != uid:
                u_check = await _get_user(uid)
                if u_check and not u_check.get("referred_by"):
                    await _update_user(uid, referred_by=referrer_id)
        except (ValueError, TypeError):
            pass

    # Автоопределение языка — только для новых пользователей
    u = await _get_user(uid)
    if not u:
        lang = _detect_lang(message.from_user.language_code)
        await _update_user(uid, lang=lang)
        logger.info(f"[{uid}] new user, lang={lang} (tg={message.from_user.language_code})")
    else:
        lang = u.get("lang") or "ru"
        if not u.get("lang"):
            await _update_user(uid, lang=lang)
            logger.info(f"[{uid}] lang was NULL, set to default 'ru'")

    # Автозахват имени из Telegram
    tg_name = (message.from_user.first_name or "User")[:30]
    if not u or not u.get("name"):
        await _update_user(uid, name=tg_name)

    u = await _get_user(uid)

    banned, until = await _is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer(t(lang, "banned_permanent"))
        else:
            await message.answer(t(lang, "banned_until", until=until.strftime('%H:%M %d.%m.%Y')))
        return

    # Уже всё принял — в меню
    if u.get("accepted_rules") and u.get("accepted_privacy"):
        # Streak + level check
        streak_info, level_info = await _update_streak(uid)
        asyncio.create_task(_notify_achievements_fn(uid))
        asyncio.create_task(_quest_progress_fn(uid, "streak"))
        badge = await _get_premium_badge(uid)
        online = await _get_online_count()
        online_text = f"\n🟢 {t(lang, 'online_count', count=online)}" if online > 0 else ""
        await message.answer(
            t(lang, "welcome_back", badge=badge) + online_text,
            reply_markup=_kb_main(lang)
        )
        # Notify streak milestone
        if streak_info and isinstance(streak_info, int) and streak_info in STREAK_BONUSES:
            await message.answer(t(lang, "streak_bonus", days=streak_info, bonus=STREAK_BONUSES[streak_info]))
        # Notify level-up
        if level_info is not None:
            level_name = t(lang, LEVEL_NAMES.get(level_info, "level_0"))
            await message.answer(t(lang, "level_up", level=level_info, name=level_name))
        # A/B log
        await _log_ab_event(uid, "session_start")
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


# ======================== accept:all (new onboarding) ========================

@router.callback_query(F.data == "accept:all", StateFilter("*"))
async def accept_all(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    await _update_user(uid, accepted_privacy=True, accepted_rules=True, ab_group=_get_ab_group(uid))
    await _update_streak(uid)
    asyncio.create_task(_notify_achievements_fn(uid))
    asyncio.create_task(_quest_progress_fn(uid, "streak"))
    try:
        await callback.message.edit_text(t(lang, "rules_accepted"))
    except Exception:
        pass
    badge = await _get_premium_badge(uid)
    online = await _get_online_count()
    online_text = f"\n🟢 {t(lang, 'online_count', count=online)}" if online > 0 else ""
    await callback.message.answer(
        t(lang, "welcome_new", badge=badge) + online_text,
        reply_markup=_kb_main(lang)
    )
    await _log_ab_event(uid, "registered")
    await callback.answer()


# ======================== lang switch during onboarding ========================

@router.callback_query(F.data.startswith("lang:"), StateFilter("*"))
async def switch_lang_onboarding(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    new_lang = callback.data.split(":")[1]
    if new_lang not in ("ru", "en", "es"):
        await callback.answer()
        return
    await _update_user(uid, lang=new_lang)
    u = await _get_user(uid)
    name = u.get("name", "User") if u else "User"

    # Отправляем условия на новом языке со ссылкой
    legal_url = get_legal_url(new_lang)
    try:
        await callback.message.edit_text(
            t(new_lang, "privacy", legal_url=legal_url),
            disable_web_page_preview=True,
        )
    except Exception:
        pass
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
    except Exception:
        pass
    await callback.answer()


# ======================== Privacy policy ========================

@router.callback_query(F.data == "privacy:accept", StateFilter("*"))
async def privacy_accept(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    await _update_user(uid, accepted_privacy=True)
    try:
        await callback.message.edit_text(t(lang, "privacy_accepted"))
    except Exception:
        pass

    # Предлагаем подписку на канал
    await callback.message.answer(t(lang, "channel_bonus"), reply_markup=_kb_channel_bonus(lang))
    await callback.answer()


@router.callback_query(F.data == "privacy:decline", StateFilter("*"))
async def privacy_decline(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    try:
        await callback.message.edit_text(t(lang, "privacy_declined"))
    except Exception:
        pass
    await callback.answer()


# ======================== Channel subscription bonus ========================

@router.callback_query(F.data == "channel:check", StateFilter("*"))
async def channel_check(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    u = await _get_user(uid)

    if u and u.get("channel_bonus_used"):
        await callback.answer(t(lang, "channel_bonus_used"), show_alert=True)
        await _proceed_after_channel(callback.message, state, uid)
        return

    # Если уже есть активный Premium — не даём бесплатный бонус
    if await _is_premium(uid):
        await callback.answer(t(lang, "channel_already_premium"), show_alert=True)
        await _update_user(uid, channel_bonus_used=True)
        await _proceed_after_channel(callback.message, state, uid)
        return

    is_subscribed = await _check_channel_sub_fn(uid)
    if not is_subscribed:
        await callback.answer(t(lang, "channel_not_subscribed"), show_alert=True)
        return

    from datetime import datetime, timedelta
    until = datetime.now() + timedelta(days=3)
    await _update_user(uid, premium_until=until.isoformat(), channel_bonus_used=True)
    try:
        await callback.message.edit_text(
            t(lang, "channel_bonus_activated", until=until.strftime('%d.%m.%Y'))
        )
    except Exception:
        pass
    await _proceed_after_channel(callback.message, state, uid)
    await callback.answer()


@router.callback_query(F.data == "channel:skip", StateFilter("*"))
async def channel_skip(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    try:
        await callback.message.edit_text(t(lang, "channel_skip"))
    except Exception:
        pass
    await _proceed_after_channel(callback.message, state, uid)
    await callback.answer()


async def _proceed_after_channel(message, state, uid):
    """Продолжение после channel bonus — в меню"""
    u = await _get_user(uid)
    lang = (u.get("lang") or "ru") if u else "ru"
    badge = await _get_premium_badge(uid)
    await message.answer(t(lang, "welcome_back", badge=badge), reply_markup=_kb_main(lang))


# ======================== Rules (legacy) ========================

@router.message(StateFilter(Rules.waiting), F.text.in_(_all("btn_accept_rules")))
async def accept_rules(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    await _update_user(uid, accepted_rules=True)
    await state.clear()
    await message.answer(t(lang, "rules_accepted"), reply_markup=_kb_main(lang))


@router.message(StateFilter(Rules.waiting))
async def rules_other(message: types.Message):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    await message.answer(t(lang, "rules_choose_lang"))


# ======================== Registration form ========================

@router.message(F.text.in_(_all("btn_start_form")), StateFilter(Reg.name))
async def start_reg(message: types.Message):
    lang = await _get_lang(message.from_user.id)
    await message.answer(t(lang, "reg_name_prompt"), reply_markup=_kb_cancel_reg(lang))


@router.message(F.text.in_(_all("btn_cancel_reg")), StateFilter("*"))
async def cancel_reg(message: types.Message, state: FSMContext):
    lang = await _get_lang(message.from_user.id)
    await state.clear()
    await message.answer(t(lang, "reg_cancelled"), reply_markup=_kb_main(lang))


@router.message(StateFilter(Reg.name))
async def reg_name(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await _unavailable(message, lang, "reason_enter_name")
        return
    if txt in _all("btn_start_form"):
        await message.answer(t(lang, "reg_name_prompt"), reply_markup=_kb_cancel_reg(lang))
        return
    await _ensure_user(uid)
    await _update_user(uid, name=txt.strip()[:20])
    await state.set_state(Reg.age)
    await message.answer(t(lang, "reg_age_prompt"), reply_markup=_kb_cancel_reg(lang))


@router.message(StateFilter(Reg.age))
async def reg_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await _unavailable(message, lang, "reason_enter_age")
        return
    if not txt.isdigit():
        await message.answer(t(lang, "reg_age_invalid"))
        return
    age = int(txt)
    joke = _get_age_joke(age, lang)
    if age <= 15:
        await message.answer(t(lang, "reg_age_too_young", joke=joke))
        return
    if age > 99:
        await message.answer(t(lang, "reg_age_too_old", joke=joke))
        return
    await _update_user(uid, age=age)
    await message.answer(joke)
    await asyncio.sleep(0.5)
    await state.set_state(Reg.gender)
    await message.answer(t(lang, "reg_gender_prompt"), reply_markup=_kb_gender(lang))


@router.message(StateFilter(Reg.gender))
async def reg_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await _unavailable(message, lang, "reason_choose_gender")
        return
    if txt == t(lang, "btn_male"):
        gender = "male"
    elif txt == t(lang, "btn_female"):
        gender = "female"
    elif txt == t(lang, "btn_other"):
        gender = "other"
    else:
        await message.answer(t(lang, "reg_gender_invalid"), reply_markup=_kb_gender(lang))
        return
    await _update_user(uid, gender=gender)
    await state.set_state(Reg.mode)
    await message.answer(t(lang, "reg_mode_prompt"), reply_markup=_kb_mode(lang))


@router.message(StateFilter(Reg.mode))
async def reg_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    txt = message.text or ""
    if txt.startswith("/") or txt in BLOCKED_TEXTS:
        await _unavailable(message, lang, "reason_choose_mode")
        return
    if txt == t(lang, "btn_mode_simple"):
        mode = "simple"
    elif txt == t(lang, "btn_mode_flirt"):
        mode = "flirt"
    elif txt == t(lang, "btn_mode_kink"):
        mode = "kink"
    else:
        await message.answer(t(lang, "reg_mode_invalid"), reply_markup=_kb_mode(lang))
        return
    # Проверка возраста для Kink
    if mode == "kink":
        u = await _get_user(uid)
        age = u.get("age", 0) if u else 0
        if age and age < 18:
            await message.answer(t(lang, "reg_kink_age"), reply_markup=_kb_mode(lang))
            return
    await _update_user(uid, mode=mode)
    await state.clear()
    await message.answer(t(lang, "reg_done"), reply_markup=_kb_main(lang))
    # Онбординг-тур для новых пользователей
    u_check = await _get_user(uid)
    if u_check and u_check.get("total_chats", 0) == 0:
        await message.answer(t(lang, "welcome_tour"))
        await _log_ab_event(uid, "onboarding_shown")
    # Автозапуск поиска
    if _use_redis:
        q_free = await redis_state.get_queue_members(mode, False)
        q_prem = await redis_state.get_queue_members(mode, True)
        q_len = len(q_free) + len(q_prem)
    else:
        q_len = len(_get_fb_queue(mode, False)) + len(_get_fb_queue(mode, True))
    status = t(lang, "queue_searching")
    await message.answer(
        t(lang, "queue_info", mode=t(lang, f"mode_{mode}"), count=q_len, status=status),
        reply_markup=_kb_cancel_search(lang)
    )
    await _do_find(uid, state)


# ======================== Interest selection ========================

@router.callback_query(F.data.startswith("int:"), StateFilter(Reg.interests))
async def reg_interest(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    sel = data.get("temp_interests", [])
    mode = data.get("reg_mode", "simple")
    if val == "done":
        if not sel:
            await callback.answer(t(lang, "reg_interests_min"), show_alert=True)
            return
        await _update_user(uid, interests=",".join(sel))
        await state.clear()
        try:
            await callback.message.edit_text(t(lang, "reg_done"))
        except Exception:
            pass
        await callback.answer()
        # Онбординг-тур для новых пользователей
        u = await _get_user(uid)
        if u and u.get("total_chats", 0) == 0:
            await callback.message.answer(t(lang, "welcome_tour"))
            await _log_ab_event(uid, "onboarding_shown")
        mode = u.get("mode", "simple") if u else "simple"
        if _use_redis:
            q_free = await redis_state.get_queue_members(mode, False)
            q_prem = await redis_state.get_queue_members(mode, True)
            q_len = len(q_free) + len(q_prem)
        else:
            q_len = len(_get_fb_queue(mode, False)) + len(_get_fb_queue(mode, True))
        await callback.message.answer(
            t(lang, "queue_info", mode=t(lang, f"mode_{mode}"), count=q_len, status=t(lang, "queue_searching")),
            reply_markup=_kb_cancel_search(lang)
        )
        await _do_find(uid, state)
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
        await callback.message.edit_reply_markup(reply_markup=_kb_interests(mode, sel, lang))
    except Exception:
        pass


@router.message(StateFilter(Reg.interests))
async def reg_interest_text(message: types.Message, state: FSMContext):
    lang = await _get_lang(message.from_user.id)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "reg_cancelled"), reply_markup=_kb_main(lang))
        return
    await message.answer(t(lang, "reg_interests_invalid"))


# ======================== /restart (alias for /start) ========================

@router.message(Command("restart"), StateFilter("*"))
async def cmd_restart(message: types.Message, state: FSMContext):
    await cmd_start(message, state)
