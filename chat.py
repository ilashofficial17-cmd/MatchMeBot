"""
chat.py — Chat relay, end_chat, mutual match, complaints, gifts, rate handlers.

Extracted from bot.py. All external dependencies injected via init().
The do_find reference is set later via set_do_find() after matching.py is ready.
"""

import asyncio
import random
import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice,
)

from states import Chat, Complaint, Reg
from locales import t, TEXTS
import redis_state
import moderation
from ai_utils import translate_message
from constants import (
    GIFTS, STOP_WORDS, get_price, get_chat_topics, MAX_BONUS_ENERGY,
    filter_ads as _filter_ads,
)

logger = logging.getLogger("matchme")

router = Router()

# ── Dependency slots (populated by init()) ─────────────────────────────
_bot = None
_dp = None
_db_pool = None
_use_redis = False
_admin_id: int = 0

# Fallback dicts (non-Redis mode)
_fb_active_chats = None
_fb_pairing_lock = None
_get_all_queues = None
_fb_last_msg_time = None
_fb_chat_logs = None
_fb_mutual_likes = None
_fb_liked_chats = None

# Helper functions
_get_user = None
_get_lang = None
_update_user = None
_increment_user = None
_is_premium = None
_get_premium_tier = None
_cleanup = None
_get_rating = None
_notify_achievements = None
_quest_progress = None
_log_ab_event = None
_check_achievements = None
_send_ad_message = None
_log_ad_event = None
_check_rate_limit = None

# Keyboards
_kb_main = None
_kb_chat = None
_kb_cancel_search = None
_kb_after_chat = None
_kb_channel_bonus = None
_kb_complaint = None
_kb_complaint_action = None

# Cross-module dependency (set via set_do_find after matching.init())
_do_find = None

# Local in-memory state
msg_count: dict = {}
translate_notice_sent: set = set()
gift_prompt_sent: set = set()
_last_relay_msg_id: dict = {}


def _all(key):
    """All language variants for a locale key — for F.text.in_() filters."""
    return {TEXTS[lang][key] for lang in TEXTS if key in TEXTS[lang]}


def set_do_find(fn):
    """Post-init setter to break circular dependency with matching.py."""
    global _do_find
    _do_find = fn


def init(
    *,
    bot,
    dp,
    db_pool,
    use_redis,
    admin_id,
    # fallback dicts
    fb_active_chats,
    fb_pairing_lock,
    get_all_queues,
    fb_last_msg_time,
    fb_chat_logs,
    fb_mutual_likes,
    fb_liked_chats,
    # helper functions
    get_user,
    get_lang,
    update_user,
    increment_user,
    is_premium,
    get_premium_tier,
    cleanup,
    get_rating,
    notify_achievements,
    quest_progress,
    log_ab_event,
    check_achievements,
    send_ad_message,
    log_ad_event,
    # keyboards
    kb_main,
    kb_chat,
    kb_cancel_search,
    kb_after_chat,
    kb_channel_bonus,
    kb_complaint,
    kb_complaint_action,
    check_rate_limit=None,
):
    global _bot, _dp, _db_pool, _use_redis, _admin_id
    global _fb_active_chats, _fb_pairing_lock, _get_all_queues
    global _fb_last_msg_time, _fb_chat_logs, _fb_mutual_likes, _fb_liked_chats
    global _get_user, _get_lang, _update_user, _increment_user
    global _is_premium, _get_premium_tier, _cleanup, _get_rating
    global _notify_achievements, _quest_progress, _log_ab_event
    global _check_achievements, _send_ad_message, _log_ad_event, _check_rate_limit
    global _kb_main, _kb_chat, _kb_cancel_search, _kb_after_chat
    global _kb_channel_bonus, _kb_complaint, _kb_complaint_action

    _bot = bot
    _dp = dp
    _db_pool = db_pool
    _use_redis = use_redis
    _admin_id = admin_id

    _fb_active_chats = fb_active_chats
    _fb_pairing_lock = fb_pairing_lock
    _get_all_queues = get_all_queues
    _fb_last_msg_time = fb_last_msg_time
    _fb_chat_logs = fb_chat_logs
    _fb_mutual_likes = fb_mutual_likes
    _fb_liked_chats = fb_liked_chats

    _get_user = get_user
    _get_lang = get_lang
    _update_user = update_user
    _increment_user = increment_user
    _is_premium = is_premium
    _get_premium_tier = get_premium_tier
    _cleanup = cleanup
    _get_rating = get_rating
    _notify_achievements = notify_achievements
    _quest_progress = quest_progress
    _log_ab_event = log_ab_event
    _check_achievements = check_achievements
    _send_ad_message = send_ad_message
    _log_ad_event = log_ad_event
    _check_rate_limit = check_rate_limit

    _kb_main = kb_main
    _kb_chat = kb_chat
    _kb_cancel_search = kb_cancel_search
    _kb_after_chat = kb_after_chat
    _kb_channel_bonus = kb_channel_bonus
    _kb_complaint = kb_complaint
    _kb_complaint_action = kb_complaint_action


# ====================== CHAT HELPERS ======================
async def save_chat_to_db(uid1, uid2, chat_type="profile"):
    try:
        async with _db_pool.acquire() as conn:
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
        async with _db_pool.acquire() as conn:
            if uid2:
                await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1 OR uid1=$2", uid1, uid2)
            else:
                await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1", uid1)
    except Exception as e:
        logger.error(f"remove_chat_from_db failed: {e}")


def get_chat_key(uid1, uid2):
    return (min(uid1, uid2), max(uid1, uid2))


async def log_message_async(uid1, uid2, sender_uid, text):
    if _use_redis:
        await redis_state.log_message(uid1, uid2, sender_uid, text)
    else:
        key = get_chat_key(uid1, uid2)
        if key not in _fb_chat_logs:
            _fb_chat_logs[key] = []
        _fb_chat_logs[key].append({
            "sender": sender_uid,
            "text": text[:200],
            "time": datetime.now().strftime("%H:%M:%S")
        })
        if len(_fb_chat_logs[key]) > 10:
            _fb_chat_logs[key] = _fb_chat_logs[key][-10:]


async def get_chat_log_text(uid1, uid2):
    if _use_redis:
        logs = await redis_state.get_chat_log(uid1, uid2)
    else:
        key = get_chat_key(uid1, uid2)
        logs = _fb_chat_logs.get(key, [])
    if not logs:
        return "Переписка пуста"
    lines = []
    for msg in logs:
        sender = "Жалобщик" if msg["sender"] == uid1 else "Обвиняемый"
        lines.append(f"[{msg['time']}] {sender}: {msg['text']}")
    return "\n".join(lines)


async def check_stop_words(uid1, uid2):
    if _use_redis:
        logs = await redis_state.get_chat_log(uid1, uid2)
    else:
        key = get_chat_key(uid1, uid2)
        logs = _fb_chat_logs.get(key, [])
    all_text = " ".join(msg["text"].lower() for msg in logs)
    found = [w for w in STOP_WORDS if w.lower() in all_text]
    return len(found) > 0, found


async def clear_chat_log(uid1, uid2):
    if _use_redis:
        await redis_state.delete_chat_log(uid1, uid2)
    else:
        key = get_chat_key(uid1, uid2)
        if key in _fb_chat_logs:
            del _fb_chat_logs[key]


# ====================== END CHAT ======================
async def end_chat(uid, state, go_next=False):
    if _use_redis:
        partner = await redis_state.disconnect(uid)
    else:
        async with _fb_pairing_lock:
            partner = _fb_active_chats.pop(uid, None)
            if partner:
                _fb_active_chats.pop(partner, None)
            for q in _get_all_queues():
                q.discard(uid)
    if partner:
        await remove_chat_from_db(uid, partner)
        await clear_chat_log(uid, partner)
        translate_notice_sent.discard((uid, partner))
        translate_notice_sent.discard((partner, uid))
        gift_prompt_sent.discard((uid, partner))
        gift_prompt_sent.discard((partner, uid))

        my_lang = await _get_lang(uid)
        p_lang = await _get_lang(partner)
        rate_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'⭐' * i}", callback_data=f"rate:{partner}:{i}") for i in range(1, 6)],
        ])
        p_rate_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'⭐' * i}", callback_data=f"rate:{uid}:{i}") for i in range(1, 6)],
        ])
        try:
            await _bot.send_message(uid, t(my_lang, "chat_ended_rate"), reply_markup=rate_kb)
            await _bot.send_message(uid, t(my_lang, "after_chat_propose"), reply_markup=_kb_after_chat(partner, my_lang))
        except Exception:
            pass

        try:
            await _bot.send_message(partner, t(p_lang, "chat_ended_rate"), reply_markup=p_rate_kb)
            await _bot.send_message(partner, t(p_lang, "after_chat_propose"), reply_markup=_kb_after_chat(uid, p_lang))
            pkey = StorageKey(bot_id=_bot.id, chat_id=partner, user_id=partner)
            await FSMContext(_dp.storage, key=pkey).clear()
        except Exception:
            pass

        # Upsell after every 3rd chat
        asyncio.create_task(_send_upsell_after_chat(uid, partner))
    else:
        lang = await _get_lang(uid)
        await _bot.send_message(uid, t(lang, "chat_ended"), reply_markup=_kb_main(lang))
    await state.clear()

    if go_next and partner:
        await asyncio.sleep(0.5)
        if _use_redis:
            if await redis_state.is_in_chat(uid):
                return
        else:
            if uid in _fb_active_chats:
                return
        u = await _get_user(uid)
        if u and u.get("mode"):
            lang = (u.get("lang") or "ru")
            mode = u["mode"]
            if _use_redis:
                q_free = await redis_state.get_queue_members(mode, False)
                q_prem = await redis_state.get_queue_members(mode, True)
                q_len = len(q_free) + len(q_prem)
            else:
                # Fallback: count members in both queues for the mode
                q_len = 0
                for q in _get_all_queues():
                    q_len += len(q)
            await _bot.send_message(
                uid,
                t(lang, "queue_info", mode=t(lang, f"mode_{mode}"), count=q_len, status=t(lang, "queue_searching")),
                reply_markup=_kb_cancel_search(lang)
            )
            if _do_find:
                await _do_find(uid, state)


async def _send_upsell_after_chat(uid, partner):
    """Smart post-chat upsell:
    Chat 1: propose channel subscription (3 days Premium bonus)
    Chat 2: nothing
    Chat 3,6,9,...: Premium upsell
    Chat 5: Premium trial (one-time)
    Chat 4,8,12,...: partner ad
    """
    await asyncio.sleep(3)
    for target_uid in (uid, partner):
        if _use_redis:
            if await redis_state.is_in_chat(target_uid):
                continue
        else:
            if target_uid in _fb_active_chats:
                continue
        u = await _get_user(target_uid)
        chats = u.get("total_chats", 0) if u else 0
        # Chat #1 → channel subscription bonus
        if chats == 1 and u and not u.get("channel_bonus_used") and not await _is_premium(target_uid):
            try:
                lang = await _get_lang(target_uid)
                await _bot.send_message(
                    target_uid,
                    t(lang, "channel_bonus"),
                    reply_markup=_kb_channel_bonus(lang),
                )
            except Exception:
                pass
            continue
        if await _is_premium(target_uid):
            continue
        if chats <= 2:
            continue
        # Chat #5 → trial offer
        if chats == 5 and u and not u.get("trial_used"):
            try:
                lang = await _get_lang(target_uid)
                await _bot.send_message(
                    target_uid,
                    t(lang, "trial_offer"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=t(lang, "btn_activate_trial"), callback_data="trial:activate")]
                    ]),
                )
                await _log_ab_event(target_uid, "trial_shown")
            except Exception:
                pass
        # Every 3rd chat → premium upsell
        elif chats % 3 == 0:
            try:
                lang = await _get_lang(target_uid)
                await _bot.send_message(
                    target_uid,
                    t(lang, "upsell"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=t(lang, "prem_compare"), callback_data="buy:info")]
                    ]),
                )
                await _log_ab_event(target_uid, "upsell_shown")
            except Exception:
                pass
        # Every 6th chat → partner ad
        elif chats % 6 == 0:
            await _send_ad_message(target_uid)


# ====================== MUTUAL MATCH ======================
@router.callback_query(F.data.startswith("mutual:"), ~F.data.func(lambda d: d == "mutual:decline"), StateFilter("*"))
async def mutual_like(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    partner_uid = int(callback.data.split(":", 1)[1])
    # Check partner isn't busy with someone else
    if _use_redis:
        p_partner = await redis_state.get_active_partner(partner_uid)
        partner_busy = p_partner is not None and p_partner != uid
    else:
        partner_busy = partner_uid in _fb_active_chats and _fb_active_chats.get(partner_uid) != uid
    if partner_busy:
        lang = await _get_lang(uid)
        await callback.answer(t(lang, "partner_busy"), show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    # Strip buttons to prevent double-press
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if _use_redis:
        already_mutual = await redis_state.add_mutual_like(uid, partner_uid)
        if already_mutual:
            if await redis_state.is_in_chat(uid) or await redis_state.is_in_chat(partner_uid):
                my_lang_tmp = await _get_lang(uid)
                await callback.answer(t(my_lang_tmp, "mutual_already_in_chat"), show_alert=True)
                return
            await redis_state.set_active_chat(uid, partner_uid)
            await redis_state.set_last_msg_time(uid)
            await redis_state.set_last_msg_time(partner_uid)
    else:
        async with _fb_pairing_lock:
            if uid not in _fb_mutual_likes:
                _fb_mutual_likes[uid] = set()
            already_mutual = partner_uid in _fb_mutual_likes and uid in _fb_mutual_likes.get(partner_uid, set())
            _fb_mutual_likes[uid].add(partner_uid)
            if already_mutual:
                _fb_mutual_likes[uid].discard(partner_uid)
                if partner_uid in _fb_mutual_likes:
                    _fb_mutual_likes[partner_uid].discard(uid)
                if uid in _fb_active_chats or partner_uid in _fb_active_chats:
                    my_lang_tmp = await _get_lang(uid)
                    await callback.answer(t(my_lang_tmp, "mutual_already_in_chat"), show_alert=True)
                    return
                _fb_active_chats[uid] = partner_uid
                _fb_active_chats[partner_uid] = uid
                _fb_last_msg_time[uid] = _fb_last_msg_time[partner_uid] = datetime.now()

    if already_mutual:
        await state.set_state(Chat.chatting)
        pkey = StorageKey(bot_id=_bot.id, chat_id=partner_uid, user_id=partner_uid)
        await FSMContext(_dp.storage, key=pkey).set_state(Chat.chatting)
        await save_chat_to_db(uid, partner_uid, "mutual")
        asyncio.create_task(_notify_achievements(uid))
        asyncio.create_task(_notify_achievements(partner_uid))
        asyncio.create_task(_quest_progress(uid, "chat"))
        asyncio.create_task(_quest_progress(partner_uid, "chat"))

        my_lang = await _get_lang(uid)
        p_lang = await _get_lang(partner_uid)
        await _bot.send_message(uid, t(my_lang, "mutual_match"), reply_markup=_kb_chat(my_lang))
        await _bot.send_message(partner_uid, t(p_lang, "mutual_match"), reply_markup=_kb_chat(p_lang))
    else:
        lang = await _get_lang(uid)
        p_lang = await _get_lang(partner_uid)
        await callback.message.answer(t(lang, "mutual_request_sent"))
        try:
            await _bot.send_message(
                partner_uid,
                t(p_lang, "mutual_request_received"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t(p_lang, "btn_continue"), callback_data=f"mutual:{uid}")],
                    [InlineKeyboardButton(text=t(p_lang, "btn_stop"), callback_data="mutual:decline")],
                ])
            )
        except Exception:
            pass
        asyncio.create_task(_mutual_timeout(uid, partner_uid))

    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data == "mutual:decline", StateFilter("*"))
async def mutual_decline(callback: types.CallbackQuery):
    uid = callback.from_user.id
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    # Clear all mutual likes to this user
    if not _use_redis:
        for key in list(_fb_mutual_likes.keys()):
            _fb_mutual_likes[key].discard(uid)
    # Redis: mutual likes auto-expire via TTL, no cleanup needed
    lang = await _get_lang(callback.from_user.id)
    await callback.answer(t(lang, "mutual_decline_ok"))


async def _mutual_timeout(uid, partner_uid):
    await asyncio.sleep(600)  # 10 minutes
    if _use_redis:
        # Redis: auto-expires via TTL
        pass
    else:
        if uid in _fb_mutual_likes and partner_uid in _fb_mutual_likes[uid]:
            _fb_mutual_likes[uid].discard(partner_uid)
    try:
        lang = await _get_lang(uid)
        await _bot.send_message(uid, t(lang, "mutual_no_response"))
    except Exception:
        pass


# ====================== RELAY (main chat message forwarding) ======================
@router.message(StateFilter(Chat.chatting))
async def relay(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if _last_relay_msg_id.get(uid) == message.message_id:
        return
    _last_relay_msg_id[uid] = message.message_id
    lang = await _get_lang(uid)
    txt = message.text or ""
    if txt == t(lang, "btn_next") or "⏭" in txt:
        await end_chat(uid, state, go_next=True)
        return
    if txt == t(lang, "btn_stop"):
        await end_chat(uid, state, go_next=False)
        return
    if txt == t(lang, "btn_complaint") or "🚩" in txt:
        await state.set_state(Complaint.reason)
        await message.answer(t(lang, "complaint_prompt"), reply_markup=_kb_complaint(lang))
        return
    if txt == t(lang, "btn_like") or "👍" in txt:
        partner = (await redis_state.get_active_partner(uid)) if _use_redis else _fb_active_chats.get(uid)
        if partner:
            chat_key = get_chat_key(uid, partner)
            if _use_redis:
                already_liked = await redis_state.is_liked(uid, f"{chat_key[0]}:{chat_key[1]}")
            else:
                already_liked = (uid, chat_key) in _fb_liked_chats
            if already_liked:
                await message.answer(t(lang, "like_already"))
                return
            if _use_redis:
                await redis_state.set_liked(uid, f"{chat_key[0]}:{chat_key[1]}")
            else:
                _fb_liked_chats.add((uid, chat_key))
            await _increment_user(partner, likes=1)
            asyncio.create_task(_notify_achievements(partner))
            asyncio.create_task(_quest_progress(uid, "like"))
            await message.answer(t(lang, "like_sent"))
            try:
                p_lang = await _get_lang(partner)
                await _bot.send_message(partner, t(p_lang, "like_received"))
            except Exception:
                pass
        return
    if txt == t(lang, "btn_topic") or "🎲" in txt:
        partner = (await redis_state.get_active_partner(uid)) if _use_redis else _fb_active_chats.get(uid)
        if partner:
            topics = get_chat_topics(lang)
            idx = random.randrange(len(topics))
            topic = topics[idx]
            await message.answer(t(lang, "topic_sent", topic=topic))
            try:
                p_lang = await _get_lang(partner)
                p_topics = get_chat_topics(p_lang)
                p_topic = p_topics[idx] if idx < len(p_topics) else topic
                await _bot.send_message(partner, t(p_lang, "topic_received", topic=p_topic))
            except Exception:
                pass
        return
    if txt == t(lang, "btn_home") or "🏠" in txt:
        await end_chat(uid, state, go_next=False)
        return
    if txt.startswith("/start"):
        await end_chat(uid, state, go_next=False)
        return
    partner = (await redis_state.get_active_partner(uid)) if _use_redis else _fb_active_chats.get(uid)
    if not partner:
        await state.clear()
        await message.answer(t(lang, "not_in_chat"), reply_markup=_kb_main(lang))
        return
    if message.text:
        await log_message_async(uid, partner, uid, message.text)
        # Real-time AI moderation
        mod_result = await moderation.check_message(message.text, uid)
        if mod_result:
            if mod_result["action"] == "hard_ban":
                logger.warning(f"HARD BAN trigger uid={uid}: {mod_result['reason']}")
                await _update_user(uid, ban_until="permanent")
                await end_chat(uid, state, go_next=False)
                await message.answer(t(lang, "hardban"))
                try:
                    await _bot.send_message(
                        _admin_id,
                        f"🚨 Авто-бан!\nUID: {uid}\n{mod_result['reason']}\nТекст: {message.text[:200]}"
                    )
                except Exception:
                    pass
                return
            elif mod_result["action"] == "shadow_ban":
                u_check = await _get_user(uid)
                if not u_check or not u_check.get("shadow_ban"):
                    logger.info(f"AI shadow ban uid={uid}: {mod_result['reason']}")
                    await _update_user(uid, shadow_ban=True)
                    try:
                        await _bot.send_message(
                            _admin_id,
                            f"🤖 AI shadow ban\nUID: {uid}\n{mod_result['reason']}\nТекст: {message.text[:200]}"
                        )
                    except Exception:
                        pass
                # Don't forward the offending message (silently drop)
                return
    now = datetime.now()
    # Update last_seen
    await _update_user(uid, last_seen=now)
    msg_count.setdefault(uid, [])
    msg_count[uid] = [ts for ts in msg_count[uid] if (now - ts).total_seconds() < 5]
    if len(msg_count[uid]) >= 5:
        await message.answer(t(lang, "spam_warning"))
        return
    msg_count[uid].append(now)
    if _use_redis:
        await redis_state.set_last_msg_time(uid)
        await redis_state.set_last_msg_time(partner)
    else:
        _fb_last_msg_time[uid] = _fb_last_msg_time[partner] = now
    # --- Translation for cross-language chats ---
    p_lang = await _get_lang(partner)
    need_translate = lang != p_lang
    partner_premium = False
    partner_auto_translate = True
    if need_translate:
        partner_premium = await _is_premium(partner)
        p_user = await _get_user(partner)
        partner_auto_translate = p_user.get("auto_translate", True) if p_user else True

    async def _translate_text(text):
        """Translate text for partner if needed. Returns formatted or original."""
        if not text or not need_translate:
            return text
        if not partner_premium or not partner_auto_translate:
            # Send one-time notice to non-premium partner
            if (partner, uid) not in translate_notice_sent:
                translate_notice_sent.add((partner, uid))
                try:
                    await _bot.send_message(partner, t(p_lang, "translate_premium_notice"))
                except Exception:
                    pass
            return text
        translated = await translate_message(text, lang, p_lang)
        if translated and translated.strip() != text.strip():
            return f"{translated}\n\n💬 {text}"
        return text

    # --- Gift prompt: premium user sees option to gift non-premium partner ---
    if need_translate and (uid, partner) not in gift_prompt_sent:
        my_premium = await _is_premium(uid)
        if my_premium and not partner_premium:
            gift_prompt_sent.add((uid, partner))
            try:
                await _bot.send_message(
                    uid,
                    t(lang, "gift_prompt"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text=f"🌹 {t(lang, 'gift_rose')} — {get_price('rose', lang)}⭐", callback_data=f"gift:rose:{partner}"),
                            InlineKeyboardButton(text=f"💎 {t(lang, 'gift_diamond')} — {get_price('diamond', lang)}⭐", callback_data=f"gift:diamond:{partner}"),
                        ],
                        [InlineKeyboardButton(text=f"👑 {t(lang, 'gift_crown')} — {get_price('crown', lang)}⭐", callback_data=f"gift:crown:{partner}")],
                    ])
                )
            except Exception:
                pass

    try:
        if message.text:
            relay_text = await _translate_text(message.text)
            await _bot.send_message(partner, relay_text)
        elif message.sticker:
            await _bot.send_sticker(partner, message.sticker.file_id)
        elif message.photo:
            cap = await _translate_text(message.caption)
            sent = await _bot.send_photo(partner, message.photo[-1].file_id, caption=cap)
            try:
                await _bot.set_message_reaction(
                    chat_id=uid,
                    message_id=message.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="📸")],
                )
            except Exception:
                pass
            try:
                await _bot.set_message_reaction(
                    chat_id=partner,
                    message_id=sent.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="😍")],
                )
            except Exception:
                pass
        elif message.voice:
            await _bot.send_voice(partner, message.voice.file_id)
        elif message.video:
            cap = await _translate_text(message.caption)
            sent = await _bot.send_video(partner, message.video.file_id, caption=cap)
            try:
                await _bot.set_message_reaction(
                    chat_id=uid,
                    message_id=message.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="🎬")],
                )
            except Exception:
                pass
            try:
                await _bot.set_message_reaction(
                    chat_id=partner,
                    message_id=sent.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="🔥")],
                )
            except Exception:
                pass
        elif message.video_note:
            sent = await _bot.send_video_note(partner, message.video_note.file_id)
            try:
                await _bot.set_message_reaction(
                    chat_id=partner,
                    message_id=sent.message_id,
                    reaction=[types.ReactionTypeEmoji(emoji="👀")],
                )
            except Exception:
                pass
        elif message.document:
            cap = await _translate_text(message.caption)
            await _bot.send_document(partner, message.document.file_id, caption=cap)
        elif message.audio:
            await _bot.send_audio(partner, message.audio.file_id)
    except Exception as e:
        logger.warning(f"Relay failed {uid}->{partner}: {e}")


# ====================== GIFTS IN CHAT ======================
@router.callback_query(F.data.startswith("gift:"), StateFilter("*"))
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
    lang = await _get_lang(uid)
    await _bot.send_invoice(
        chat_id=uid,
        title=t(lang, f"gift_{gift_type}_title"),
        description=t(lang, "gift_desc", days=gift["days"]),
        payload=f"gift_{gift_type}_{partner_uid}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{gift['emoji']} Gift", amount=get_price(gift_type, lang))],
    )
    await callback.answer()


# ====================== COMPLAINTS ======================
@router.callback_query(F.data == "rep:cancel", StateFilter(Complaint.reason))
async def complaint_cancel(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    _in_chat_c = (await redis_state.is_in_chat(uid)) if _use_redis else (uid in _fb_active_chats)
    if _in_chat_c:
        await state.set_state(Chat.chatting)
    else:
        await state.clear()
    try:
        await callback.message.edit_text(t(lang, "complaint_cancelled"))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("rep:"), StateFilter(Complaint.reason))
async def handle_complaint(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    # Rate limit: max 3 complaints per 300 seconds
    if _check_rate_limit:
        if not await _check_rate_limit(uid, "complaint", 3, 300):
            lang_rl = await _get_lang(uid)
            await callback.answer(t(lang_rl, "rate_limited"), show_alert=True)
            return
    reason_map = {
        "minor": "Несовершеннолетние", "spam": "Спам/Реклама",
        "abuse": "Угрозы/Оскорбления", "nsfw": "Пошлятина без согласия", "other": "Другое"
    }
    reason = reason_map.get(callback.data.split(":", 1)[1], "Другое")
    partner = (await redis_state.get_active_partner(uid)) if _use_redis else _fb_active_chats.get(uid)
    lang = await _get_lang(uid)
    if not partner:
        try:
            await callback.message.edit_text(t(lang, "complaint_not_in_chat"))
        except Exception:
            pass
        await state.clear()
        return
    log_text = await get_chat_log_text(uid, partner)
    stop_found, _ = await check_stop_words(uid, partner)
    async with _db_pool.acquire() as conn:
        complaint_id = await conn.fetchval(
            "INSERT INTO complaints_log (from_uid, to_uid, reason, chat_log, stop_words_found) VALUES ($1,$2,$3,$4,$5) RETURNING id",
            uid, partner, reason, log_text, stop_found
        )
        await _increment_user(partner, complaints=1)
    if _use_redis:
        await redis_state.disconnect(uid)
    else:
        async with _fb_pairing_lock:
            _fb_active_chats.pop(uid, None)
            _fb_active_chats.pop(partner, None)
    await remove_chat_from_db(uid, partner)
    await clear_chat_log(uid, partner)
    await state.clear()
    try:
        await callback.message.edit_text(t(lang, "complaint_sent", id=complaint_id))
    except Exception:
        pass
    await _bot.send_message(uid, t(lang, "chat_ended"), reply_markup=_kb_main(lang))
    try:
        p_lang = await _get_lang(partner)
        await _bot.send_message(partner, t(p_lang, "partner_complained"), reply_markup=_kb_main(p_lang))
        pkey = StorageKey(bot_id=_bot.id, chat_id=partner, user_id=partner)
        await FSMContext(_dp.storage, key=pkey).clear()
    except Exception:
        pass
    # AI moderation: complaint review
    ai_result = await moderation.ai_review_complaint(complaint_id)
    if not ai_result:
        # Fallback: AI unavailable → notify admin old-school
        pu = await _get_user(partner)
        ru = await _get_user(uid)
        try:
            await _bot.send_message(
                _admin_id,
                f"🚩 Жалоба #{complaint_id} (AI недоступен)!\n\n"
                f"👤 От: {uid} ({ru.get('name','?') if ru else '?'})\n"
                f"👤 На: {partner} ({pu.get('name','?') if pu else '?'}) | Жалоб: {pu.get('complaints',0) if pu else '?'}\n"
                f"📋 Причина: {reason}\n"
                f"{'⚠️ Стоп-слова найдены!' if stop_found else '✅ Стоп-слова не найдены'}\n"
                f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                reply_markup=_kb_complaint_action(complaint_id, partner, uid, bool(log_text), stop_found)
            )
        except Exception:
            pass
    await callback.answer()


# ====================== STOP / NEXT ======================
@router.message(Command("stop"), StateFilter("*"))
async def cmd_stop(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_lang(uid)
    current = await state.get_state()
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await message.answer(t(lang, "unavailable", reason=t(lang, "reason_finish_anketa")))
        return
    await end_chat(uid, state, go_next=False)


@router.message(Command("next"), StateFilter("*"))
async def cmd_next(message: types.Message, state: FSMContext):
    await end_chat(message.from_user.id, state, go_next=True)


# ====================== NO-OP CALLBACK ======================
@router.callback_query(F.data == "noop", StateFilter("*"))
async def noop(callback: types.CallbackQuery):
    await callback.answer()


# ====================== CHAT RATING ======================
@router.callback_query(F.data.startswith("rate:"), StateFilter("*"))
async def rate_chat(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    parts = callback.data.split(":")
    partner_uid = int(parts[1])
    stars = int(parts[2])
    try:
        async with _db_pool.acquire() as conn:
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
        # Mechanic A: bonus energy for rating (up to 5 times/day)
        u = await _get_user(uid)
        rate_today = u.get("rate_energy_today", 0) if u else 0
        if rate_today < 5:
            cur_bonus = u.get("bonus_energy", 0) if u else 0
            new_bonus = min(cur_bonus + 2, MAX_BONUS_ENERGY)
            await _update_user(uid, bonus_energy=new_bonus, rate_energy_today=rate_today + 1)
            try:
                await callback.message.edit_text(
                    t(lang, "rate_thanks", stars=stars) + "\n" + t(lang, "rate_energy_bonus"))
            except Exception:
                pass
        else:
            try:
                await callback.message.edit_text(t(lang, "rate_thanks", stars=stars))
            except Exception:
                pass
        await callback.answer(t(lang, "rate_thanks", stars=stars))
        # Check achievements after rating
        new_achs = await _check_achievements(uid)
        if new_achs:
            for ach_id in new_achs:
                try:
                    await _bot.send_message(uid, t(lang, f"ach_{ach_id}"))
                except Exception:
                    pass
        asyncio.create_task(_quest_progress(uid, "rate"))
    except Exception:
        await callback.answer()


# ====================== AD CLICK TRACKING ======================
@router.callback_query(F.data.startswith("adclick:"), StateFilter("*"))
async def ad_click_handler(callback: types.CallbackQuery):
    """Track ad click + send link."""
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    parts = callback.data.split(":")
    try:
        idx = int(parts[1])
        source = parts[2] if len(parts) > 2 else "search"
    except (ValueError, IndexError):
        await callback.answer()
        return
    u = await _get_user(uid)
    mode = u.get("mode", "simple") if u else "simple"
    ads = _filter_ads(lang, mode)
    if not ads or idx >= len(ads):
        await callback.answer()
        return
    ad = ads[idx]
    await _log_ad_event(uid, ad["text_key"], "click", source)
    await callback.answer()
    await _bot.send_message(uid, ad["url"], disable_web_page_preview=False)
