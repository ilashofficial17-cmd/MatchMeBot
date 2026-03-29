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

router = Router()
logger = logging.getLogger("matchme")

VENICE_API_KEY = os.environ.get("VENICE_API_KEY")
VENICE_API_URL = "https://api.venice.ai/api/v1/chat/completions"

AI_LIMITS = {
    "basic":   {"free": 20,  "premium": None, "plus": None},
    "premium": {"free": 10,  "premium": 50,   "plus": None},
}

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

# ====================== Инжектируемые зависимости ======================
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


def get_ai_limit(char_tier: str, user_tier) -> int | None:
    """Лимит сообщений/день. None = безлимит."""
    tier_key = user_tier or "free"
    return AI_LIMITS.get(char_tier, {}).get(tier_key, 10)


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


# ====================== ИИ СОБЕСЕДНИК ======================
async def _show_ai_menu(message: types.Message, state: FSMContext, uid: int):
    user_tier = await _get_premium_tier(uid)
    u = await _get_user(uid)
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


@router.message(F.text == "🤖 ИИ чат", StateFilter("*"))
@router.message(Command("ai"), StateFilter("*"))
async def ai_menu(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current == Chat.chatting.state:
        await message.answer("⚠️ Сейчас недоступно — ты в чате с живым собеседником.")
        return
    if current in [Reg.name.state, Reg.age.state, Reg.gender.state, Reg.mode.state, Reg.interests.state]:
        await message.answer("⚠️ Сейчас недоступно — сначала заверши анкету.")
        return
    await _ensure_user(uid)
    u = await _get_user(uid)
    if not u or not u.get("name"):
        await state.set_state(Reg.name)
        await message.answer("Сначала заполни анкету!", reply_markup=kb_main())
        return
    await _show_ai_menu(message, state, uid)


@router.callback_query(F.data.startswith("aichar:"), StateFilter(AIChat.choosing))
async def choose_ai_character(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    char_id = callback.data.split(":", 1)[1]
    if char_id == "back":
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
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
        user_tier = await _get_premium_tier(uid)
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
    user_tier = await _get_premium_tier(uid)
    limit = get_ai_limit(char["tier"], user_tier)
    _ai_sessions[uid] = {"character": char_id, "history": [], "msg_count": 0}
    _last_ai_msg[uid] = datetime.now()
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
        _ai_sessions[uid]["history"].append({"role": "assistant", "content": greeting})
        await callback.message.answer(f"{char['emoji']} {greeting}")
    await callback.answer()


@router.message(StateFilter(AIChat.choosing))
async def ai_choosing_text(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""
    if "Завершить чат" in txt or "🏠" in txt or "Главное меню" in txt:
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
        await state.clear()
        await message.answer("🏠 Главное меню", reply_markup=kb_main())
        return
    if "Сменить персонажа" in txt:
        return
    if "Найти живого" in txt:
        _ai_sessions.pop(uid, None)
        await state.clear()
        await message.answer("🔍 Ищем...", reply_markup=kb_cancel_search())
        await _cmd_find(message, state)
        return
    await message.answer("👆 Выбери персонажа из кнопок выше.")


@router.message(StateFilter(AIChat.chatting))
async def ai_chat_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""
    if "Завершить чат" in txt:
        _ai_sessions.pop(uid, None)
        _last_ai_msg.pop(uid, None)
        await state.clear()
        await message.answer("✅ Чат с ИИ завершён.", reply_markup=kb_main())
        return
    if "Сменить персонажа" in txt:
        _ai_sessions.pop(uid, None)
        user_tier = await _get_premium_tier(uid)
        u = await _get_user(uid)
        mode = u.get("mode", "simple") if u else "simple"
        await state.set_state(AIChat.choosing)
        await message.answer("Выбери персонажа:", reply_markup=kb_ai_characters(user_tier, mode))
        return
    if "Найти живого" in txt:
        _ai_sessions.pop(uid, None)
        await state.clear()
        await message.answer("🔍 Ищем...", reply_markup=kb_cancel_search())
        await _cmd_find(message, state)
        return
    if "🏠" in txt or "Главное меню" in txt:
        _ai_sessions.pop(uid, None)
        await state.clear()
        await message.answer("🏠 Главное меню", reply_markup=kb_main())
        return
    if uid not in _ai_sessions:
        await state.clear()
        await message.answer("Сессия потеряна. Начни заново.", reply_markup=kb_main())
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
    _last_ai_msg[uid] = datetime.now()
    await _bot.send_chat_action(uid, "typing")
    await _update_user(uid, last_seen=datetime.now())
    session["history"].append({"role": "user", "content": txt})
    response = await ask_venice(char_id, session["history"][:-1], txt)
    session["history"].append({"role": "assistant", "content": response})
    session["msg_count"] += 1
    new_count = current_count + 1
    if limit is not None and new_count > limit and ai_bonus > 0:
        await _update_user(uid, **{counter_field: new_count, "ai_bonus": ai_bonus - 1})
    else:
        await _update_user(uid, **{counter_field: new_count})
    remaining = ""
    if effective_limit is not None:
        left = effective_limit - new_count
        if left <= 3:
            remaining = f"\n\n_💬 Осталось {left} сообщений_"
    await message.answer(f"{char['emoji']} {response}{remaining}")


# ====================== GOTO CALLBACKS ======================
@router.callback_query(F.data.startswith("goto:"), StateFilter("*"))
async def goto_action(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
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
        await callback.answer("⏳ Продолжаем ждать...")
        return
    elif action == "find":
        _ai_sessions.pop(uid, None)
        async with _pairing_lock:
            for q in _get_all_queues():
                q.discard(uid)
        await state.clear()
        await callback.message.answer("🔍 Ищем...", reply_markup=kb_cancel_search())
        await _cmd_find(callback.message, state)
    elif action == "menu":
        await state.clear()
        await callback.message.answer("🏠 Главное меню", reply_markup=kb_main())
    await callback.answer()


# ====================== AI QUICK START (из поиска) ======================
@router.callback_query(F.data.startswith("ai:start:"), StateFilter("*"))
async def ai_quick_start(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    char_id = callback.data.split(":", 2)[2]
    if char_id not in AI_CHARACTERS:
        await callback.answer("Персонаж не найден.", show_alert=True)
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
    limit_text = "♾ Безлимит" if limit is None else f"💬 Лимит: {limit} сообщений/день"
    await callback.message.answer(
        f"✅ Ты общаешься с {char['name']}\n{char['description']}\n\n{limit_text}",
        reply_markup=kb_ai_chat()
    )
    greeting = await ask_venice(char_id, [], "Поприветствуй собеседника и начни разговор. Коротко, 1-2 предложения на русском.")
    if greeting:
        _ai_sessions[uid]["history"].append({"role": "assistant", "content": greeting})
        await callback.message.answer(f"{char['emoji']} {greeting}")
    await callback.answer()
