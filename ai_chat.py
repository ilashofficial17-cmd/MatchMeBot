import os
import asyncio
import aiohttp
import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import AIChat, Chat, Reg
from keyboards import kb_main, kb_ai_characters, kb_ai_chat, kb_cancel_search
from locales import t, TEXTS

router = Router()
logger = logging.getLogger("matchme")

AI_LIMITS = {
    "basic":   {"free": 20,  "premium": None, "plus": None},
    "premium": {"free": 0,   "premium": None, "plus": None},
}

# Персонажи будут добавлены по блокам
AI_CHARACTERS = {}

# All language variants for button text matching
def _all(key):
    return {TEXTS[lang][key] for lang in TEXTS if key in TEXTS[lang]}

# ====================== Injected dependencies ======================
_bot = None
_ai_sessions = None
_last_ai_msg = None
_pairing_lock = None
_get_all_queues = None
_active_chats = None
_get_user = None
_ensure_user = None
_get_premium_tier = None
_update_user = None
_cmd_find = None
_show_settings = None


def init(*, bot, ai_sessions, last_ai_msg, pairing_lock, get_all_queues,
         active_chats, get_user, ensure_user, get_premium_tier, update_user,
         cmd_find, show_settings):
    global _bot, _ai_sessions, _last_ai_msg, _pairing_lock, _get_all_queues
    global _active_chats, _get_user, _ensure_user, _get_premium_tier
    global _update_user, _cmd_find, _show_settings
    _bot = bot
    _ai_sessions = ai_sessions
    _last_ai_msg = last_ai_msg
    _pairing_lock = pairing_lock
    _get_all_queues = get_all_queues
    _active_chats = active_chats
    _get_user = get_user
    _ensure_user = ensure_user
    _get_premium_tier = get_premium_tier
    _update_user = update_user
    _cmd_find = cmd_find
    _show_settings = show_settings


async def _lang(uid: int) -> str:
    u = await _get_user(uid)
    return (u.get("lang") or "ru") if u else "ru"


def get_ai_limit(char_tier: str, user_tier) -> int | None:
    """Message limit per day. None = unlimited."""
    tier_key = user_tier or "free"
    return AI_LIMITS.get(char_tier, {}).get(tier_key, 10)


async def ask_venice(character_id: str, history: list, user_message: str, lang: str = "ru") -> str:
    if not VENICE_API_KEY:
        return t(lang, "ai_unavailable")
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
                    return t(lang, "ai_no_funds")
                else:
                    logger.warning(f"Venice API error: status={resp.status}")
                    return t(lang, "ai_error")
    except Exception as e:
        logger.error(f"Venice API connection error: {e}")
        return t(lang, "ai_connection_error")


# ====================== AI MENU ======================
async def _show_ai_menu(message: types.Message, state: FSMContext, uid: int):
    lang = await _lang(uid)
    user_tier = await _get_premium_tier(uid)
    u = await _get_user(uid)
    mode = u.get("mode", "simple") if u else "simple"
    await state.set_state(AIChat.choosing)
    await state.update_data(ai_show_mode=mode)
    await message.answer(t(lang, "ai_menu"), reply_markup=kb_ai_characters(user_tier, mode, lang))


@router.message(F.text.in_(_all("btn_ai_chat")), StateFilter("*"))
@router.message(Command("ai"), StateFilter("*"))
async def ai_menu(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _lang(uid)
    current = await state.get_state()
    if current == Chat.chatting.state:
        await message.answer(t(lang, "ai_in_live_chat"))
        return
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await message.answer(t(lang, "ai_complete_profile"))
        return
    await _ensure_user(uid)
    u = await _get_user(uid)
    if not u or not u.get("name"):
        await state.set_state(Reg.name)
        await message.answer(t(lang, "ai_profile_required"), reply_markup=kb_main(lang))
        return
    await _show_ai_menu(message, state, uid)


@router.callback_query(F.data.startswith("aichar:"), StateFilter(AIChat.choosing))
async def choose_ai_character(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _lang(uid)
    char_id = callback.data.split(":", 1)[1]
    if char_id == "back":
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
        await state.clear()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception: pass
        await callback.message.answer(t(lang, "btn_home"), reply_markup=kb_main(lang))
        await callback.answer()
        return
    if char_id in ("power_soon", "vip_locked"):
        msg = t(lang, "ai_vip_required") if char_id == "vip_locked" else t(lang, "ai_power_soon")
        await callback.answer(msg, show_alert=True)
        return
    if char_id == "all":
        user_tier = await _get_premium_tier(uid)
        await state.update_data(ai_show_mode="any")
        try:
            await callback.message.edit_reply_markup(reply_markup=kb_ai_characters(user_tier, "any", lang))
        except Exception: pass
        await callback.answer()
        return
    if char_id not in AI_CHARACTERS:
        await callback.answer(t(lang, "ai_char_not_found"), show_alert=True)
        return
    char = AI_CHARACTERS[char_id]
    user_tier = await _get_premium_tier(uid)
    limit = get_ai_limit(char["tier"], user_tier)
    _ai_sessions[uid] = {"character": char_id, "history": [], "msg_count": 0}
    _last_ai_msg[uid] = datetime.now()
    await state.set_state(AIChat.chatting)
    limit_text = t(lang, "ai_unlimited") if limit is None else t(lang, "ai_limit_info", limit=limit)
    tier_icon = "🔥" if char["tier"] == "premium" else "✅"
    try:
        await callback.message.edit_text(
            t(lang, "ai_chatting_with",
              name=f"{tier_icon} {t(lang, char['name_key'])}",
              description=t(lang, char["desc_key"]),
              limit_text=limit_text)
        )
    except Exception: pass
    await callback.message.answer(t(lang, "ai_chat_active"), reply_markup=kb_ai_chat(lang))
    greeting = await ask_venice(char_id, [], t(lang, "ai_greeting"), lang)
    if greeting:
        _ai_sessions[uid]["history"].append({"role": "assistant", "content": greeting})
        await callback.message.answer(f"{char['emoji']} {greeting}")
    await callback.answer()


@router.message(StateFilter(AIChat.choosing))
async def ai_choosing_text(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _lang(uid)
    txt = message.text or ""
    if txt in {t(lang, "btn_end_ai_chat"), t(lang, "btn_home")}:
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
        await state.clear()
        await message.answer(t(lang, "btn_home"), reply_markup=kb_main(lang))
        return
    if txt == t(lang, "btn_change_char"):
        await message.answer(t(lang, "ai_select_from_buttons"))
        return
    if txt == t(lang, "btn_find_live"):
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
        await state.clear()
        await message.answer(t(lang, "searching"), reply_markup=kb_cancel_search(lang))
        await _cmd_find(message, state)
        return
    await message.answer(t(lang, "ai_select_from_buttons"))


@router.message(StateFilter(AIChat.chatting))
async def ai_chat_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _lang(uid)
    txt = message.text or ""
    if txt == t(lang, "btn_end_ai_chat"):
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
        await state.clear()
        await message.answer(t(lang, "ai_ended"), reply_markup=kb_main(lang))
        return
    if txt == t(lang, "btn_change_char"):
        _ai_sessions.pop(uid, None)
        user_tier = await _get_premium_tier(uid)
        u = await _get_user(uid)
        mode = u.get("mode", "simple") if u else "simple"
        await state.set_state(AIChat.choosing)
        await message.answer(t(lang, "ai_select_char"), reply_markup=kb_ai_characters(user_tier, mode, lang))
        return
    if txt == t(lang, "btn_find_live"):
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
        await state.clear()
        await message.answer(t(lang, "searching"), reply_markup=kb_cancel_search(lang))
        await _cmd_find(message, state)
        return
    if txt == t(lang, "btn_home"):
        _ai_sessions.pop(uid, None)
        await state.clear()
        await message.answer(t(lang, "btn_home"), reply_markup=kb_main(lang))
        return
    if uid not in _ai_sessions:
        await state.clear()
        await message.answer(t(lang, "ai_session_lost"), reply_markup=kb_main(lang))
        return
    session = _ai_sessions[uid]
    char_id = session["character"]
    char = AI_CHARACTERS[char_id]
    user_tier = await _get_premium_tier(uid)
    char_tier = char["tier"]
    limit = get_ai_limit(char_tier, user_tier)
    u = await _get_user(uid)
    counter_field = f"ai_msg_{char_tier}"
    current_count = u.get(counter_field, 0) if u else 0
    reset_time = u.get("ai_messages_reset") if u else None
    if reset_time and (datetime.now() - reset_time).total_seconds() > 86400:
        await _update_user(uid, ai_msg_basic=0, ai_msg_premium=0, ai_messages_reset=datetime.now())
        current_count = 0
    ai_bonus = u.get("ai_bonus", 0) if u else 0
    effective_limit = (limit + ai_bonus) if limit is not None else None
    if effective_limit is not None and current_count >= effective_limit:
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
        await state.clear()
        if user_tier == "premium":
            limit_msg = t(lang, "ai_limit_plus", limit=limit)
            upsell_btn = "buy:plus_1m"
        else:
            limit_msg = t(lang, "ai_limit_basic", limit=limit)
            upsell_btn = "buy:1m"
        await message.answer(
            limit_msg,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(lang, "ai_buy_sub"), callback_data=upsell_btn)],
                [InlineKeyboardButton(text=t(lang, "btn_find_live"), callback_data="goto:find")],
                [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="goto:menu")]
            ])
        )
        return
    _last_ai_msg[uid] = datetime.now()
    await _bot.send_chat_action(uid, "typing")
    await _update_user(uid, last_seen=datetime.now())
    session["history"].append({"role": "user", "content": txt})
    response = await ask_venice(char_id, session["history"][:-1], txt, lang)
    session["history"].append({"role": "assistant", "content": response})
    session["msg_count"] += 1
    new_count = current_count + 1
    if limit is not None and new_count > limit and ai_bonus > 0:
        await _update_user(uid, **{counter_field: new_count, "ai_bonus": ai_bonus - 1})
    else:
        await _update_user(uid, **{counter_field: new_count})
    remaining = ""
    if effective_limit is not None:
        left = max(effective_limit - new_count, 0)
        if 0 < left <= 3:
            remaining = f"\n\n{t(lang, 'ai_remaining', left=left)}"
    await message.answer(f"{char['emoji']} {response}{remaining}")


# ====================== GOTO CALLBACKS ======================
@router.callback_query(F.data.startswith("goto:"), StateFilter("*"))
async def goto_action(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _lang(uid)
    action = callback.data.split(":", 1)[1]
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    if action == "ai":
        async with _pairing_lock:
            for q in _get_all_queues():
                q.discard(uid)
        await state.clear()
        await _show_ai_menu(callback.message, state, uid)
    elif action == "settings":
        await _show_settings(callback.message, state)
    elif action == "wait":
        await callback.answer(t(lang, "ai_waiting_continue"))
        return
    elif action == "find":
        _ai_sessions.pop(uid, None)
        async with _pairing_lock:
            for q in _get_all_queues():
                q.discard(uid)
        await state.clear()
        await callback.message.answer(t(lang, "searching"), reply_markup=kb_cancel_search(lang))
        await _cmd_find(callback.message, state)
    elif action == "menu":
        await state.clear()
        await callback.message.answer(t(lang, "btn_home"), reply_markup=kb_main(lang))
    await callback.answer()


# ====================== AI QUICK START (from search) ======================
@router.callback_query(F.data.startswith("ai:start:"), StateFilter("*"))
async def ai_quick_start(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang = await _lang(uid)
    char_id = callback.data.split(":", 2)[2]
    if char_id not in AI_CHARACTERS:
        await callback.answer(t(lang, "ai_char_not_found"), show_alert=True)
        return
    async with _pairing_lock:
        for q in _get_all_queues():
            q.discard(uid)
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    char = AI_CHARACTERS[char_id]
    user_tier = await _get_premium_tier(uid)
    limit = get_ai_limit(char["tier"], user_tier)
    _ai_sessions[uid] = {"character": char_id, "history": [], "msg_count": 0}
    _last_ai_msg[uid] = datetime.now()
    await state.set_state(AIChat.chatting)
    limit_text = t(lang, "ai_unlimited") if limit is None else t(lang, "ai_limit_info", limit=limit)
    await callback.message.answer(
        t(lang, "ai_quick_start",
          name=t(lang, char["name_key"]),
          description=t(lang, char["desc_key"]),
          limit_text=limit_text),
        reply_markup=kb_ai_chat(lang)
    )
    greeting = await ask_venice(char_id, [], t(lang, "ai_greeting"), lang)
    if greeting:
        _ai_sessions[uid]["history"].append({"role": "assistant", "content": greeting})
        await callback.message.answer(f"{char['emoji']} {greeting}")
    await callback.answer()
