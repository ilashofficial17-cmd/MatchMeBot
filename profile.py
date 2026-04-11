"""Profile, settings, and utility handlers — extracted from bot.py."""

import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from states import Reg, Chat, EditProfile, ResetProfile, AIChat
from locales import t, TEXTS

import redis_state

logger = logging.getLogger("matchme")

router = Router()

# ── Module-level refs (set by init()) ──────────────────────────────────
_bot = None
_db_pool = None
_use_redis = False
_admin_id: int = 0

# Helper functions
_get_user = None
_get_lang = None
_update_user = None
_is_premium = None
_get_premium_tier = None
_get_rating = None
_get_premium_badge = None
_get_age_joke = None
_cleanup = None
_needs_onboarding = None
_unavailable = None
_kb_settings_fn = None

# Fallback state (used only when Redis unavailable)
_get_all_queues = None
_fb_ai_sessions = None

# Keyboards
_kb_main = None
_kb_cancel_reg = None
_kb_gender = None
_kb_mode = None
_kb_interests = None
_kb_search_gender = None
_kb_edit = None
_kb_energy_shop = None
_kb_premium = None

# Constants
_LEVEL_THRESHOLDS = None
_LEVEL_NAMES = None
_STREAK_BONUSES = None

# Public reference (ai_chat.py needs it at module level after init)
show_settings = None


def _all(key):
    """All language variants for a locale key — for F.text.in_() filters."""
    return {TEXTS[lang][key] for lang in TEXTS if key in TEXTS[lang]}


async def _is_in_queue(uid: int) -> bool:
    """Check whether *uid* is currently in a search queue."""
    if _use_redis:
        return await redis_state.is_in_queue(uid)
    if _get_all_queues is not None:
        return any(uid in q for q in _get_all_queues())
    return False


async def _clear_ai_if_active(uid: int, state: FSMContext):
    """If the user is inside an AI-chat session, tear it down."""
    current = await state.get_state()
    if current in (AIChat.choosing.state, AIChat.chatting.state):
        if _use_redis:
            await redis_state.delete_ai_session(uid)
        elif _fb_ai_sessions is not None:
            _fb_ai_sessions.pop(uid, None)
        await state.clear()


def init(
    *,
    bot,
    db_pool,
    use_redis,
    admin_id,
    # helpers
    get_user,
    get_lang,
    update_user,
    is_premium,
    get_premium_tier,
    get_rating,
    get_premium_badge,
    get_age_joke,
    cleanup,
    needs_onboarding_fn,
    unavailable_fn,
    kb_settings_fn,
    # keyboards
    kb_main,
    kb_cancel_reg,
    kb_gender,
    kb_mode,
    kb_interests,
    kb_search_gender,
    kb_edit,
    kb_energy_shop,
    kb_premium,
    # constants
    LEVEL_THRESHOLDS,
    LEVEL_NAMES,
    STREAK_BONUSES,
    # fallback state
    get_all_queues=None,
    fb_ai_sessions=None,
):
    global _bot, _db_pool, _use_redis, _admin_id
    global _get_user, _get_lang, _update_user, _is_premium, _get_premium_tier
    global _get_rating, _get_premium_badge, _get_age_joke, _cleanup
    global _needs_onboarding, _unavailable, _kb_settings_fn
    global _kb_main, _kb_cancel_reg, _kb_gender, _kb_mode
    global _kb_interests, _kb_search_gender, _kb_edit, _kb_energy_shop, _kb_premium
    global _LEVEL_THRESHOLDS, _LEVEL_NAMES, _STREAK_BONUSES
    global _get_all_queues, _fb_ai_sessions
    global show_settings

    _bot = bot
    _db_pool = db_pool
    _use_redis = use_redis
    _admin_id = admin_id

    _get_all_queues = get_all_queues
    _fb_ai_sessions = fb_ai_sessions

    _get_user = get_user
    _get_lang = get_lang
    _update_user = update_user
    _is_premium = is_premium
    _get_premium_tier = get_premium_tier
    _get_rating = get_rating
    _get_premium_badge = get_premium_badge
    _get_age_joke = get_age_joke
    _cleanup = cleanup
    _needs_onboarding = needs_onboarding_fn
    _unavailable = unavailable_fn
    _kb_settings_fn = kb_settings_fn

    _kb_main = kb_main
    _kb_cancel_reg = kb_cancel_reg
    _kb_gender = kb_gender
    _kb_mode = kb_mode
    _kb_interests = kb_interests
    _kb_search_gender = kb_search_gender
    _kb_edit = kb_edit
    _kb_energy_shop = kb_energy_shop
    _kb_premium = kb_premium

    _LEVEL_THRESHOLDS = LEVEL_THRESHOLDS
    _LEVEL_NAMES = LEVEL_NAMES
    _STREAK_BONUSES = STREAK_BONUSES

    # Expose at module level so ai_chat.py can reference it after init()
    show_settings = _show_settings


# ====================== СТАТИСТИКА ======================
@router.message(Command("stats"), StateFilter("*"))
async def cmd_stats(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state):
        return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    u = await _get_user(uid)
    if not u:
        await message.answer(t(lang, "not_registered"))
        return
    user_premium = await _is_premium(uid)
    if user_premium:
        if uid == _admin_id or u.get("premium_until") == "permanent":
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
        rating=_get_rating(u),
        warns_line=warns_line,
        days=days_in_bot,
        premium=premium_text
    ))


# ====================== РЕФЕРАЛЬНАЯ ПРОГРАММА ======================
@router.message(Command("referral"), StateFilter("*"))
async def cmd_referral(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state):
        return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    if await _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
    ref_link = f"https://t.me/MyMatchMeBot?start=ref_{uid}"
    # Считаем сколько рефералов привёл
    count = 0
    if _db_pool:
        async with _db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as cnt FROM users WHERE referred_by=$1 AND referral_bonus_given=TRUE", uid)
            count = row["cnt"] if row else 0
    await message.answer(t(lang, "referral_info", link=ref_link, count=count))


# ====================== СБРОС ПРОФИЛЯ ======================
@router.message(Command("reset"), StateFilter("*"))
async def cmd_reset(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    current = await state.get_state()
    if current == Chat.chatting.state:
        await _unavailable(message, lang, "reason_finish_chat")
        return
    await state.set_state(ResetProfile.confirm)
    await message.answer(
        t(lang, "reset_confirm"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_accept_rules"), callback_data="reset:confirm")],
            [InlineKeyboardButton(text=t(lang, "btn_cancel_reg"), callback_data="reset:cancel")],
        ])
    )


@router.callback_query(F.data == "reset:confirm", StateFilter(ResetProfile.confirm))
async def reset_confirm(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    try:
        await _cleanup(uid, state)
        async with _db_pool.acquire() as conn:
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


@router.callback_query(F.data == "reset:cancel", StateFilter(ResetProfile.confirm))
async def reset_cancel(callback: types.CallbackQuery, state: FSMContext):
    lang = await _get_lang(callback.from_user.id)
    await state.clear()
    try:
        await callback.message.edit_text(t(lang, "reset_cancelled"))
    except Exception:
        pass
    await callback.message.answer(t(lang, "reset_back"), reply_markup=_kb_main(lang))
    await callback.answer()


# ====================== ПРОФИЛЬ ======================
@router.message(F.text.in_(_all("btn_profile")), StateFilter("*"))
@router.message(Command("profile"), StateFilter("*"))
async def _show_profile(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state):
        return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await _unavailable(message, lang, "reason_finish_form")
        return
    if current == Chat.chatting.state:
        await _unavailable(message, lang, "reason_in_chat_stop")
        return
    if await _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
    from db import ensure_user
    await ensure_user(uid)
    u = await _get_user(uid)
    if not u or not u.get("name"):
        await message.answer(t(lang, "profile_not_filled"), reply_markup=_kb_main(lang))
        return
    user_tier = await _get_premium_tier(uid)
    show_badge = u.get("show_premium", True)
    if user_tier:
        if uid == _admin_id or u.get("premium_until") == "permanent":
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
    if level < len(_LEVEL_THRESHOLDS) - 1:
        next_threshold = _LEVEL_THRESHOLDS[level + 1]
        current_threshold = _LEVEL_THRESHOLDS[level]
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
        rating=_get_rating(u),
        likes=u.get("likes", 0),
        chats=total_chats,
        warns_line=warns_line,
        premium_line=premium_line,
        level_info=level_info,
        streak_info=streak_info,
        progress_info=progress_info,
    )
    await message.answer(profile_text, reply_markup=_kb_edit(lang, show_premium_btn=not user_tier))


# ====================== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ======================
@router.callback_query(F.data.startswith("edit:"), StateFilter("*"))
async def edit_profile_cb(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    await callback.answer()
    if field == "name":
        await state.set_state(EditProfile.name)
        await callback.message.answer(t(lang, "edit_name_prompt"), reply_markup=_kb_cancel_reg(lang))
    elif field == "age":
        await state.set_state(EditProfile.age)
        await callback.message.answer(t(lang, "edit_age_prompt"), reply_markup=_kb_cancel_reg(lang))
    elif field == "gender":
        await state.set_state(EditProfile.gender)
        await callback.message.answer(t(lang, "edit_gender_prompt"), reply_markup=_kb_gender(lang))
    elif field == "mode":
        await state.set_state(EditProfile.mode)
        await callback.message.answer(t(lang, "edit_mode_prompt"), reply_markup=_kb_mode(lang))
    elif field == "interests":
        u = await _get_user(uid)
        mode = u.get("mode") if u else None
        if not mode:
            await callback.answer(t(lang, "edit_select_mode_first"), show_alert=True)
            return
        await state.set_state(EditProfile.interests)
        await state.update_data(temp_interests=[], edit_mode=mode)
        await callback.message.answer(t(lang, "edit_interests_prompt"), reply_markup=_kb_interests(mode, [], lang))


@router.message(StateFilter(EditProfile.name))
async def edit_name(message: types.Message, state: FSMContext):
    lang = await _get_lang(message.from_user.id)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=_kb_main(lang))
        return
    await _update_user(message.from_user.id, name=message.text.strip()[:20])
    await state.clear()
    await message.answer(t(lang, "edit_name_done"), reply_markup=_kb_main(lang))


@router.message(StateFilter(EditProfile.age))
async def edit_age(message: types.Message, state: FSMContext):
    lang = await _get_lang(message.from_user.id)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=_kb_main(lang))
        return
    if not message.text or not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer(t(lang, "edit_age_invalid"))
        return
    age = int(message.text)
    joke = _get_age_joke(age, lang)
    await _update_user(message.from_user.id, age=age)
    await state.clear()
    await message.answer(t(lang, "edit_age_done", joke=joke), reply_markup=_kb_main(lang))


@router.message(StateFilter(EditProfile.gender))
async def edit_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=_kb_main(lang))
        return
    txt = message.text or ""
    if txt == t(lang, "btn_male"):
        g = "male"
    elif txt == t(lang, "btn_female"):
        g = "female"
    elif txt == t(lang, "btn_other"):
        g = "other"
    else:
        await message.answer(t(lang, "reg_gender_invalid"), reply_markup=_kb_gender(lang))
        return
    await _update_user(uid, gender=g)
    await state.clear()
    await message.answer(t(lang, "edit_gender_done"), reply_markup=_kb_main(lang))


@router.message(StateFilter(EditProfile.mode))
async def edit_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=_kb_main(lang))
        return
    txt = message.text or ""
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
    await _update_user(uid, mode=mode, accept_cross_mode=False, interests="")
    await state.set_state(EditProfile.interests)
    await state.update_data(temp_interests=[], edit_mode=mode)
    await message.answer(t(lang, "edit_interests_prompt"), reply_markup=ReplyKeyboardRemove())
    await message.answer("👇", reply_markup=_kb_interests(mode, [], lang))


@router.callback_query(F.data.startswith("int:"), StateFilter(EditProfile.interests))
async def edit_interest(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    sel = data.get("temp_interests", [])
    mode = data.get("edit_mode", "simple")
    if val == "done":
        if not sel:
            await callback.answer(t(lang, "reg_interests_min"), show_alert=True)
            return
        await _update_user(uid, interests=",".join(sel))
        await state.clear()
        try:
            await callback.message.edit_text(t(lang, "edit_interests_done"))
        except Exception:
            pass
        await callback.message.answer(t(lang, "edit_done"), reply_markup=_kb_main(lang))
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
        await callback.message.edit_reply_markup(reply_markup=_kb_interests(mode, sel, lang))
    except Exception:
        pass


@router.message(StateFilter(EditProfile.interests))
async def edit_interest_text(message: types.Message, state: FSMContext):
    lang = await _get_lang(message.from_user.id)
    if message.text in _all("btn_cancel_reg"):
        await state.clear()
        await message.answer(t(lang, "edit_back"), reply_markup=_kb_main(lang))
        return
    await message.answer(t(lang, "reg_interests_invalid"))


# ====================== НАСТРОЙКИ ======================
@router.message(F.text.in_(_all("btn_settings")), StateFilter("*"))
@router.message(Command("settings"), StateFilter("*"))
async def _show_settings(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state):
        return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await _unavailable(message, lang, "reason_finish_anketa")
        return
    if current == Chat.chatting.state:
        await _unavailable(message, lang, "reason_in_chat")
        return
    if await _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
    from db import ensure_user
    await ensure_user(uid)
    await message.answer(t(lang, "settings_title"), reply_markup=await _kb_settings_fn(uid, lang))


@router.callback_query(F.data.startswith("set:"), StateFilter("*"))
async def toggle_setting(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    parts = callback.data.split(":")
    key = parts[1]
    u = await _get_user(uid)
    if key == "gender":
        user_premium = await _is_premium(uid)
        mode = u.get("mode", "simple") if u else "simple"
        if mode != "simple" and not user_premium:
            await callback.answer(t(lang, "settings_gender_locked"), show_alert=True)
            return
        await state.set_state(EditProfile.search_gender)
        await callback.message.answer(t(lang, "settings_gender_prompt"), reply_markup=_kb_search_gender(lang))
        await callback.answer()
        return
    elif key == "gender_locked":
        await callback.answer(t(lang, "settings_premium_only"), show_alert=True)
        return
    elif key == "age" and len(parts) == 4:
        min_age = int(parts[2])
        max_age = int(parts[3])
        await _update_user(uid, search_age_min=min_age, search_age_max=max_age)
        try:
            await callback.message.edit_reply_markup(reply_markup=await _kb_settings_fn(uid, lang))
        except Exception:
            pass
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
        await _update_user(uid, accept_cross_mode=not u.get("accept_cross_mode", False))
    elif key == "show_premium":
        await _update_user(uid, show_premium=not u.get("show_premium", True))
    elif key == "search_range":
        current = u.get("search_range", "local")
        new_val = "global" if current == "local" else "local"
        await _update_user(uid, search_range=new_val)
    elif key == "auto_translate":
        if not await _is_premium(uid):
            await callback.answer(t(lang, "settings_premium_only"), show_alert=True)
            return
        await _update_user(uid, auto_translate=not u.get("auto_translate", True))
    elif key == "translate_locked":
        await callback.answer(t(lang, "settings_translate_locked"), show_alert=True)
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=await _kb_settings_fn(uid, lang))
    except Exception:
        pass
    await callback.answer(t(lang, "settings_changed"))


@router.message(StateFilter(EditProfile.search_gender))
async def set_search_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    txt = message.text or ""
    if txt == t(lang, "btn_back"):
        await state.clear()
        await message.answer(t(lang, "settings_title"), reply_markup=await _kb_settings_fn(uid, lang))
        return
    if txt == t(lang, "btn_find_male"):
        sg = "male"
    elif txt == t(lang, "btn_find_female"):
        sg = "female"
    elif txt == t(lang, "btn_find_other"):
        sg = "other"
    else:
        sg = "any"
    await _update_user(uid, search_gender=sg)
    await state.clear()
    await message.answer(t(lang, "settings_gender_saved"), reply_markup=_kb_main(lang))


# ====================== ЕЖЕДНЕВНЫЕ КВЕСТЫ ======================
@router.message(Command("quests"), StateFilter("*"))
@router.message(F.text.in_(_all("btn_quests")), StateFilter("*"))
async def cmd_quests(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state):
        return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    from db import generate_daily_quests
    quests = await generate_daily_quests(uid)
    if not quests:
        await message.answer(t(lang, "quest_empty"))
        return
    from constants import QUEST_POOL
    name_map = {q["id"]: q["name_key"] for q in QUEST_POOL}
    lines = [t(lang, "quest_title")]
    all_done = True
    for q in quests:
        qid = q["quest_id"]
        name = t(lang, name_map.get(qid, qid))
        progress = q["progress"]
        goal = q["goal"]
        reward = q["reward"]
        if q["claimed"]:
            lines.append(f"  ✅ {name} ({progress}/{goal}) — +{reward}⚡")
        else:
            all_done = False
            lines.append(f"  ▫️ {name} ({progress}/{goal}) — +{reward}⚡")
    if all_done:
        from constants import QUEST_ALL_DONE_BONUS
        lines.append(f"\n🎉 {t(lang, 'quest_all_done', bonus=QUEST_ALL_DONE_BONUS)}")
    await message.answer("\n".join(lines))


# ====================== МАГАЗИН ЭНЕРГИИ ======================
@router.message(Command("energy"), StateFilter("*"))
@router.message(F.text.in_(_all("btn_energy_shop")), StateFilter("*"))
async def cmd_energy_shop(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state):
        return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    u = await _get_user(uid)
    from ai_chat import DAILY_ENERGY, get_energy_info
    from energy_shop import _energy_bar
    user_tier = await _get_premium_tier(uid)
    ai_bonus = u.get("ai_bonus", 0) if u else 0
    _, max_energy = get_energy_info("basic", user_tier, ai_bonus)
    bonus = u.get("bonus_energy", 0) if u else 0
    effective_max = max_energy + bonus
    energy_used = u.get("ai_energy_used", 0) if u else 0
    from datetime import datetime as _dt
    reset_time = u.get("ai_messages_reset") if u else None
    if reset_time and (_dt.now() - reset_time).total_seconds() > 86400:
        energy_used = 0
    energy_left = max(effective_max - energy_used, 0)
    bar = _energy_bar(energy_left, effective_max)
    if reset_time:
        elapsed = (_dt.now() - reset_time).total_seconds()
        remaining = max(0, 86400 - elapsed)
        hrs = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
    else:
        hrs, mins = 24, 0
    await message.answer(
        t(lang, "energy_shop_title", left=energy_left, max=effective_max,
          bar=bar, hours=hrs, mins=mins),
        reply_markup=_kb_energy_shop(lang),
        parse_mode="HTML",
    )


# ====================== ПОМОЩЬ ======================
@router.message(F.text.in_(_all("btn_help")), StateFilter("*"))
@router.message(Command("help"), StateFilter("*"))
async def show_help(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state):
        return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    if await _is_in_queue(uid):
        await message.answer(t(lang, "reason_in_search"))
        return
    await _clear_ai_if_active(uid, state)
    await message.answer(t(lang, "help_text"), reply_markup=_kb_main(lang))
