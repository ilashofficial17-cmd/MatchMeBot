"""
matching.py — Extracted matching/search logic from bot.py.

All external dependencies are injected via init().
"""

import asyncio
import random
import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import Reg, Chat, AIChat
from locales import t, TEXTS

import redis_state
from ai_characters import AI_CHARACTERS

logger = logging.getLogger("matchme")

router = Router()

# ── Dependency-injection slots (populated by init()) ──
_bot = None
_dp = None           # needed for dp.storage
_db_pool = None
_use_redis = False

# Fallback dicts / helpers
_fb_active_chats = None
_fb_pairing_lock = None
_get_all_queues = None
_get_fb_queue = None
_fb_waiting_anon = None
_fb_last_msg_time = None
_fb_ai_sessions = None

# Helper functions
_get_user = None
_get_lang = None
_ensure_user = None
_update_user = None
_increment_user = None
_is_premium = None
_get_premium_tier = None
_is_banned = None
_cleanup = None
_needs_onboarding = None
_unavailable = None
_get_rating = None
_update_streak = None
_notify_achievements_fn = None
_quest_progress_fn = None
_log_ab_event = None
_grant_referral_bonus = None
_get_online_count = None
_save_chat_to_db = None
_get_premium_badge = None
_check_rate_limit = None  # monitoring.check_rate_limit or None

# Keyboards
_kb_main = None
_kb_cancel_search = None
_kb_ai_chat = None
_kb_chat = None
_kb_cancel_reg = None


def _all(key):
    """All language variants for a locale key — for F.text.in_() filters."""
    return {TEXTS[lang][key] for lang in TEXTS if key in TEXTS[lang]}


# Smart character suggestion: match AI character to user's search mode
_MODE_CHARS = {
    "simple": ["luna", "max_simple"],
    "flirt": ["mia", "kai"],
    "kink": ["lilit", "eva"],
}


def init(
    *,
    bot,
    dp,
    db_pool,
    use_redis,
    # Fallback dicts
    fb_active_chats,
    fb_pairing_lock,
    get_all_queues,
    get_fb_queue,
    fb_waiting_anon,
    fb_last_msg_time,
    fb_ai_sessions,
    # Helper functions
    get_user,
    get_lang,
    ensure_user,
    update_user,
    increment_user,
    is_premium,
    get_premium_tier,
    is_banned,
    cleanup,
    needs_onboarding,
    unavailable,
    get_rating,
    update_streak,
    notify_achievements_fn,
    quest_progress_fn,
    log_ab_event,
    grant_referral_bonus,
    get_online_count,
    save_chat_to_db,
    get_premium_badge,
    check_rate_limit=None,
    # Keyboards
    kb_main,
    kb_cancel_search,
    kb_ai_chat,
    kb_chat,
    kb_cancel_reg,
):
    global _bot, _dp, _db_pool, _use_redis
    global _fb_active_chats, _fb_pairing_lock, _get_all_queues, _get_fb_queue
    global _fb_waiting_anon, _fb_last_msg_time, _fb_ai_sessions
    global _get_user, _get_lang, _ensure_user, _update_user, _increment_user
    global _is_premium, _get_premium_tier, _is_banned, _cleanup
    global _needs_onboarding, _unavailable, _get_rating, _update_streak
    global _notify_achievements_fn, _quest_progress_fn, _log_ab_event
    global _grant_referral_bonus, _get_online_count, _save_chat_to_db
    global _get_premium_badge, _check_rate_limit
    global _kb_main, _kb_cancel_search, _kb_ai_chat, _kb_chat, _kb_cancel_reg

    _bot = bot
    _dp = dp
    _db_pool = db_pool
    _use_redis = use_redis

    _fb_active_chats = fb_active_chats
    _fb_pairing_lock = fb_pairing_lock
    _get_all_queues = get_all_queues
    _get_fb_queue = get_fb_queue
    _fb_waiting_anon = fb_waiting_anon
    _fb_last_msg_time = fb_last_msg_time
    _fb_ai_sessions = fb_ai_sessions

    _get_user = get_user
    _get_lang = get_lang
    _ensure_user = ensure_user
    _update_user = update_user
    _increment_user = increment_user
    _is_premium = is_premium
    _get_premium_tier = get_premium_tier
    _is_banned = is_banned
    _cleanup = cleanup
    _needs_onboarding = needs_onboarding
    _unavailable = unavailable
    _get_rating = get_rating
    _update_streak = update_streak
    _notify_achievements_fn = notify_achievements_fn
    _quest_progress_fn = quest_progress_fn
    _log_ab_event = log_ab_event
    _grant_referral_bonus = grant_referral_bonus
    _get_online_count = get_online_count
    _save_chat_to_db = save_chat_to_db
    _get_premium_badge = get_premium_badge
    _check_rate_limit = check_rate_limit

    _kb_main = kb_main
    _kb_cancel_search = kb_cancel_search
    _kb_ai_chat = kb_ai_chat
    _kb_chat = kb_chat
    _kb_cancel_reg = kb_cancel_reg


# ====================== CORE MATCHING ======================

async def do_find(uid, state):
    # Rate limit: max 3 searches per 60 seconds
    if _check_rate_limit is not None:
        lang_rl = await _get_lang(uid)
        if not await _check_rate_limit(uid, "search", 3, 60):
            try:
                await _bot.send_message(uid, t(lang_rl, "rate_limited"))
            except Exception:
                pass
            return False
    if _use_redis:
        if await redis_state.is_in_chat(uid):
            return False
    else:
        if uid in _fb_active_chats:
            return False
    u = await _get_user(uid)
    if not u or not u.get("mode"): return False
    mode = u["mode"]
    my_lang = u.get("lang") or "ru"
    user_premium = await _is_premium(uid)
    my_interests = set(filter(None, u.get("interests", "").split(","))) if u.get("interests") else set()
    my_rating = _get_rating(u)
    my_shadow = u.get("shadow_ban", False)
    cross = u.get("accept_cross_mode", False)
    search_gender = u.get("search_gender", "any")
    search_age_min = u.get("search_age_min", 16) or 16
    search_age_max = u.get("search_age_max", 99) or 99
    my_search_range = u.get("search_range", "local")
    my_age = u.get("age") or 0

    queue_configs = [(mode, True), (mode, False)]
    if cross and mode == "flirt":
        queue_configs += [("kink", True), ("kink", False)]
    elif cross and mode == "kink":
        queue_configs += [("flirt", True), ("flirt", False)]

    candidates = []

    if _use_redis:
        # ── Фаза 1: Redis-фильтрация (без DB) ──
        available_by_queue = {}
        for q_mode, q_prem in queue_configs:
            qkey = redis_state.queue_key(q_mode, q_prem)
            raw = await redis_state.redis_pool.srandmember(qkey, 50)
            if not raw:
                continue
            pids = [int(m) for m in raw if int(m) != uid]
            if not pids:
                continue
            pipe = redis_state.redis_pool.pipeline()
            for pid in pids:
                pipe.exists(f"mm:chat:active:{pid}")
            results = await pipe.execute()
            free = [pid for pid, busy in zip(pids, results) if not busy]
            if free:
                available_by_queue[qkey] = free

        # ── Фаза 2: Batch DB-обогащение + фильтрация ──
        all_pids = []
        pid_to_qkey = {}
        for qkey, pids in available_by_queue.items():
            for pid in pids[:20]:
                if pid not in pid_to_qkey:
                    all_pids.append(pid)
                    pid_to_qkey[pid] = qkey

        if all_pids:
            rows = await _db_pool.fetch(
                "SELECT * FROM users WHERE uid = ANY($1::bigint[])", all_pids
            )
            for pu in (dict(r) for r in rows):
                pid = pu["uid"]
                if not pu.get("name") or not pu.get("gender") or not pu.get("mode"):
                    continue
                if pu.get("ban_until"):
                    ban_v = pu["ban_until"]
                    if ban_v == "permanent":
                        continue
                    try:
                        if datetime.now() < datetime.fromisoformat(ban_v):
                            continue
                    except Exception:
                        pass
                p_lang_val = pu.get("lang") or "ru"
                p_search_range = pu.get("search_range", "local")
                if my_lang != p_lang_val and my_search_range == "local" and p_search_range == "local":
                    continue
                p_shadow = pu.get("shadow_ban", False)
                if my_shadow != p_shadow:
                    continue
                if search_gender != "any" and pu.get("gender") != search_gender:
                    continue
                p_search_gender = pu.get("search_gender", "any")
                if p_search_gender != "any" and u.get("gender") != p_search_gender:
                    continue
                p_age = pu.get("age") or 0
                if p_age and (p_age < search_age_min or p_age > search_age_max):
                    continue
                p_age_min = pu.get("search_age_min", 16) or 16
                p_age_max = pu.get("search_age_max", 99) or 99
                if my_age and (my_age < p_age_min or my_age > p_age_max):
                    continue
                p_mode = pu.get("mode", "simple")
                if mode == "simple" and p_mode != "simple":
                    continue
                if p_mode != mode and not pu.get("accept_cross_mode", False):
                    continue
                p_interests = set(filter(None, pu.get("interests", "").split(","))) if pu.get("interests") else set()
                common = len(my_interests & p_interests)
                rating_diff = abs(_get_rating(pu) - my_rating)
                p_premium = await _is_premium(pid)
                priority = 0 if p_premium else 1
                candidates.append((pid, common, rating_diff, priority, pid_to_qkey[pid]))
    else:
        # ── Fallback: in-memory очереди (без Redis) ──
        for q_mode, q_prem in queue_configs:
            q_obj = _get_fb_queue(q_mode, q_prem)
            q_members = set(q_obj)
            for pid in q_members:
                if pid == uid:
                    continue
                if pid in _fb_active_chats:
                    continue
                pu = await _get_user(pid)
                if not pu or not pu.get("name") or not pu.get("gender") or not pu.get("mode"):
                    continue
                if pu.get("ban_until"):
                    ban_v = pu["ban_until"]
                    if ban_v == "permanent":
                        continue
                    try:
                        if datetime.now() < datetime.fromisoformat(ban_v):
                            continue
                    except Exception:
                        pass
                p_lang_val = pu.get("lang") or "ru"
                p_search_range = pu.get("search_range", "local")
                if my_lang != p_lang_val and my_search_range == "local" and p_search_range == "local":
                    continue
                p_shadow = pu.get("shadow_ban", False)
                if my_shadow != p_shadow:
                    continue
                if search_gender != "any" and pu.get("gender") != search_gender:
                    continue
                p_search_gender = pu.get("search_gender", "any")
                if p_search_gender != "any" and u.get("gender") != p_search_gender:
                    continue
                p_age = pu.get("age") or 0
                if p_age and (p_age < search_age_min or p_age > search_age_max):
                    continue
                p_age_min = pu.get("search_age_min", 16) or 16
                p_age_max = pu.get("search_age_max", 99) or 99
                if my_age and (my_age < p_age_min or my_age > p_age_max):
                    continue
                p_mode = pu.get("mode", "simple")
                if mode == "simple" and p_mode != "simple":
                    continue
                if p_mode != mode and not pu.get("accept_cross_mode", False):
                    continue
                p_interests = set(filter(None, pu.get("interests", "").split(","))) if pu.get("interests") else set()
                common = len(my_interests & p_interests)
                rating_diff = abs(_get_rating(pu) - my_rating)
                p_premium = await _is_premium(pid)
                priority = 0 if p_premium else 1
                candidates.append((pid, common, rating_diff, priority, _get_fb_queue(q_mode, q_prem)))

    if candidates:
        candidates.sort(key=lambda x: (x[3], -x[1], x[2]))

    # Атомарное спаривание
    partner = None
    if _use_redis:
        if await redis_state.is_in_chat(uid):
            await redis_state.remove_from_queues(uid)
            return True
        for cand_pid, _, _, _, cand_qkey in candidates:
            result = await redis_state.try_pair(uid, cand_pid, cand_qkey)
            if result == 1:
                partner = cand_pid
                break
        if not partner:
            await redis_state.add_to_queue(uid, mode, user_premium)
    else:
        async with _fb_pairing_lock:
            if uid in _fb_active_chats:
                for q in _get_all_queues():
                    q.discard(uid)
                return True
            for cand_pid, _, _, _, cand_q in candidates:
                if cand_pid not in _fb_active_chats and cand_pid in cand_q:
                    partner = cand_pid
                    cand_q.discard(partner)
                    break
            if partner:
                _fb_active_chats[uid] = partner
                _fb_active_chats[partner] = uid
                _fb_last_msg_time[uid] = _fb_last_msg_time[partner] = datetime.now()
            else:
                q = _get_fb_queue(mode, user_premium)
                q.add(uid)

    # Все await-операции — ПОСЛЕ лока
    if partner:
        await state.set_state(Chat.chatting)
        pkey = StorageKey(bot_id=_bot.id, chat_id=partner, user_id=partner)
        p_fsm = FSMContext(_dp.storage, key=pkey)
        await p_fsm.set_state(Chat.chatting)
        await _save_chat_to_db(uid, partner, "profile")
        pu = await _get_user(partner)
        await _increment_user(uid, total_chats=1)
        await _increment_user(partner, total_chats=1)
        asyncio.create_task(_grant_referral_bonus(uid))
        asyncio.create_task(_grant_referral_bonus(partner))
        asyncio.create_task(_notify_achievements_fn(uid))
        asyncio.create_task(_notify_achievements_fn(partner))
        asyncio.create_task(_quest_progress_fn(uid, "chat"))
        asyncio.create_task(_quest_progress_fn(partner, "chat"))
        my_lang = (u.get("lang") or "ru") if u else "ru"
        p_lang = (pu.get("lang") or "ru") if pu else "ru"
        p_badge = await _get_premium_badge(partner)
        my_badge = await _get_premium_badge(uid)

        def _interests_str(row, lang):
            raw = (row.get("interests") or "").split(",") if row else []
            keys = [k.strip() for k in raw if k.strip()]
            return ", ".join(t(lang, k) for k in keys) or "—"

        await _bot.send_message(uid,
            t(my_lang, "partner_found",
              badge=p_badge,
              name=pu.get("name", "—"),
              age=pu.get("age", "?"),
              gender=t(my_lang, f"gender_{pu.get('gender', 'other')}"),
              interests=_interests_str(pu, my_lang),
              rating=_get_rating(pu))
        )
        await _bot.send_message(partner,
            t(p_lang, "partner_found",
              badge=my_badge,
              name=u.get("name", "—"),
              age=u.get("age", "?"),
              gender=t(p_lang, f"gender_{u.get('gender', 'other')}"),
              interests=_interests_str(u, p_lang),
              rating=_get_rating(u))
        )
        await _bot.send_message(uid, t(my_lang, "chat_start"), reply_markup=_kb_chat(my_lang))
        await _bot.send_message(partner, t(p_lang, "chat_start"), reply_markup=_kb_chat(p_lang))
        return True
    else:
        await state.set_state(Chat.waiting)
        asyncio.create_task(notify_no_partner(uid))
        return False


# ====================== NO-PARTNER TIMEOUT ======================

async def notify_no_partner(uid):
    await asyncio.sleep(30)
    if _use_redis:
        if await redis_state.is_in_chat(uid):
            return
        in_queue = await redis_state.is_in_queue(uid)
    else:
        if uid in _fb_active_chats:
            return
        in_queue = any(uid in q for q in _get_all_queues())
    if in_queue:
        try:
            u = await _get_user(uid)
            mode = u.get("mode", "simple") if u else "simple"
            candidates = _MODE_CHARS.get(mode, _MODE_CHARS["simple"])
            # For kink, check if user has premium (VIP+ required)
            if mode == "kink" and not await _is_premium(uid):
                candidates = _MODE_CHARS["flirt"]
            char_id = random.choice(candidates)
            char = AI_CHARACTERS[char_id]
            lang = await _get_lang(uid)
            name = t(lang, char['name_key'])
            await _bot.send_message(uid,
                t(lang, "no_partner_wait", name=name),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"💬 {name}", callback_data=f"ai:start:{char_id}")],
                    [InlineKeyboardButton(text=t(lang, "btn_settings"), callback_data="goto:settings")],
                    [InlineKeyboardButton(text=t(lang, "ai_waiting_continue"), callback_data="goto:wait")],
                ])
            )
        except Exception: pass


# ====================== ANONYMOUS SEARCH HANDLER ======================

@router.message(F.text.in_(_all("btn_search")), StateFilter("*"))
async def anon_search(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await _unavailable(message, lang, "reason_finish_form")
        return
    _in_chat = (await redis_state.is_in_chat(uid)) if _use_redis else (uid in _fb_active_chats)
    if current == Chat.chatting.state or _in_chat:
        await _unavailable(message, lang, "reason_in_chat")
        return
    if current == AIChat.chatting.state:
        if _use_redis:
            await redis_state.delete_ai_session(uid)
        else:
            _fb_ai_sessions.pop(uid, None)
    await _cleanup(uid, state)
    banned, until = await _is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer(t(lang, "banned_permanent"))
        else:
            await message.answer(t(lang, "banned_until", until=until.strftime('%H:%M %d.%m.%Y')))
        return
    await _ensure_user(uid)
    online = await _get_online_count()
    online_hint = f"\n🟢 {t(lang, 'online_count', count=online)}" if online > 0 else ""
    await message.answer(t(lang, "searching_anon") + online_hint, reply_markup=_kb_cancel_search(lang))
    # Shadow ban & language check
    u = await _get_user(uid)
    my_shadow = u.get("shadow_ban", False) if u else False
    my_lang = (u.get("lang") or "ru") if u else "ru"
    # Собираем кандидатов ВНЕ лока
    anon_candidates = []
    if _use_redis:
        anon_members = await redis_state.get_queue_members("anon", False)
    else:
        anon_members = set(_fb_waiting_anon)
    for pid in anon_members:
        if pid == uid: continue
        if _use_redis:
            if await redis_state.is_in_chat(pid): continue
        else:
            if pid in _fb_active_chats: continue
        pu = await _get_user(pid)
        if not pu: continue
        if pu.get("shadow_ban", False) != my_shadow: continue
        if (pu.get("lang") or "ru") != my_lang: continue
        anon_candidates.append(pid)
    # Атомарное спаривание
    partner = None
    anon_qkey = redis_state.queue_key("anon", False) if _use_redis else None
    if _use_redis:
        if await redis_state.is_in_chat(uid):
            await redis_state.remove_from_queues(uid)
            return
        for pid in anon_candidates:
            result = await redis_state.try_pair(uid, pid, anon_qkey)
            if result == 1:
                partner = pid
                break
        if not partner:
            await redis_state.add_to_queue(uid, "anon", False)
    else:
        async with _fb_pairing_lock:
            if uid in _fb_active_chats:
                _fb_waiting_anon.discard(uid)
                return
            for pid in anon_candidates:
                if pid not in _fb_active_chats and pid in _fb_waiting_anon:
                    partner = pid
                    _fb_waiting_anon.discard(pid)
                    break
            if partner:
                _fb_active_chats[uid] = partner
                _fb_active_chats[partner] = uid
                _fb_last_msg_time[uid] = _fb_last_msg_time[partner] = datetime.now()
            else:
                _fb_waiting_anon.add(uid)

    # Все await-операции — ПОСЛЕ лока
    if partner:
        await state.set_state(Chat.chatting)
        pkey = StorageKey(bot_id=_bot.id, chat_id=partner, user_id=partner)
        await FSMContext(_dp.storage, key=pkey).set_state(Chat.chatting)
        await _save_chat_to_db(uid, partner, "anon")
        await _increment_user(uid, total_chats=1)
        await _increment_user(partner, total_chats=1)
        asyncio.create_task(_grant_referral_bonus(uid))
        asyncio.create_task(_grant_referral_bonus(partner))
        asyncio.create_task(_notify_achievements_fn(uid))
        asyncio.create_task(_notify_achievements_fn(partner))
        asyncio.create_task(_quest_progress_fn(uid, "chat"))
        asyncio.create_task(_quest_progress_fn(partner, "chat"))
        p_lang = await _get_lang(partner)
        await _bot.send_message(uid, t(lang, "connected"), reply_markup=_kb_chat(lang))
        await _bot.send_message(partner, t(p_lang, "connected"), reply_markup=_kb_chat(p_lang))
    else:
        await state.set_state(Chat.waiting)
        asyncio.create_task(notify_no_partner(uid))


# ====================== PROFILE-BASED SEARCH HANDLER ======================

@router.message(F.text.in_(_all("btn_find")), StateFilter("*"))
@router.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    if await _needs_onboarding(message, state): return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await _unavailable(message, lang, "reason_finish_form")
        return
    _in_chat_f = (await redis_state.is_in_chat(uid)) if _use_redis else (uid in _fb_active_chats)
    if current == Chat.chatting.state or _in_chat_f:
        await _unavailable(message, lang, "reason_in_chat")
        return
    if current == AIChat.chatting.state:
        if _use_redis:
            await redis_state.delete_ai_session(uid)
        else:
            _fb_ai_sessions.pop(uid, None)
    await _cleanup(uid, state)
    await _ensure_user(uid)
    banned, until = await _is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer(t(lang, "banned_permanent"))
        else:
            await message.answer(t(lang, "banned_until", until=until.strftime('%H:%M %d.%m.%Y')))
        return
    u = await _get_user(uid)
    if not u or not u.get("mode"):
        await state.set_state(Reg.age)
        await message.answer(t(lang, "reg_age_prompt"), reply_markup=_kb_cancel_reg(lang))
        return
    mode = u["mode"]
    user_premium = await _is_premium(uid)
    if _use_redis:
        q_free = await redis_state.get_queue_members(mode, False)
        q_prem = await redis_state.get_queue_members(mode, True)
        q_len = len(q_free) + len(q_prem)
    else:
        q_len = len(_get_fb_queue(mode, False)) + len(_get_fb_queue(mode, True))
    status = t(lang, "queue_priority") if user_premium else t(lang, "queue_searching")
    await message.answer(
        t(lang, "queue_info", mode=t(lang, f"mode_{mode}"), count=q_len, status=status),
        reply_markup=_kb_cancel_search(lang)
    )
    await do_find(uid, state)


# ====================== CANCEL SEARCH HANDLER ======================

@router.message(F.text.in_(_all("btn_cancel_search")), StateFilter("*"))
async def cancel_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    if _use_redis:
        removed = await redis_state.is_in_queue(uid)
        await redis_state.remove_from_queues(uid)
    else:
        async with _fb_pairing_lock:
            removed = any(uid in q for q in _get_all_queues())
            for q in _get_all_queues():
                q.discard(uid)
    await state.clear()
    await message.answer(t(lang, "search_cancelled") if removed else t(lang, "not_searching"), reply_markup=_kb_main(lang))
