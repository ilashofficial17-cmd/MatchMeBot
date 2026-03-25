import asyncio
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ====================== ХРАНИЛИЩА ======================
users = {}           # uid -> профиль
active_chats = {}    # uid -> partner_uid
waiting_anon = []    # базовая анонимная очередь
waiting_simple = []  # просто общение
waiting_flirt = []   # флирт
waiting_kink = []    # kink
last_msg_time = {}
msg_count = {}
ban_list = {}        # uid -> datetime разбана
complaints = {}      # uid -> список жалоб
pairing_lock = asyncio.Lock()

# ====================== СОСТОЯНИЯ ======================
class Reg(StatesGroup):
    language = State()
    name = State()
    age = State()
    gender = State()
    mode = State()
    interests = State()

class Chat(StatesGroup):
    waiting = State()
    chatting = State()

class Rules(StatesGroup):
    waiting = State()

class Complaint(StatesGroup):
    reason = State()

class EditProfile(StatesGroup):
    field = State()
    name = State()
    age = State()
    gender = State()
    mode = State()
    interests = State()

# ====================== ТЕКСТЫ ======================
WELCOME_TEXT = (
    "👋 Привет! Я MatchMe — анонимный чат для общения, флирта и знакомств.\n\n"
    "🇷🇺 Нажми кнопку для продолжения\n"
    "🇬🇧 Click button to continue\n\n"
    "💬 Найди своего собеседника прямо сейчас!"
)

RULES_RU = """📜 Правила MatchMe:

✅ Что разрешено:
• Общение, флирт, ролевые игры (18+)
• Уважительное общение
• Использование кнопок жалобы при нарушениях

❌ Что запрещено:
• Спам, реклама, продажа чего-либо
• Контент с несовершеннолетними — немедленный бан
• Угрозы, оскорбления, травля
• Злоупотребление кнопкой жалобы (бан за ложные жалобы)
• Sharing личных данных без согласия

⚠️ Система банов:
• 1-я жалоба: предупреждение
• 2-я жалоба: бан 3 часа
• 3-я жалоба: бан 24 часа
• 4-я жалоба: перманентный бан

Kink-режим только для 18+. Нажимая «Принять», ты подтверждаешь что тебе есть 18 лет для Kink-режима.

Нажми ✅ Принять правила для продолжения."""

RULES_EN = """📜 MatchMe Rules:

✅ Allowed:
• Communication, flirting, roleplay (18+)
• Respectful interaction
• Using report button for violations

❌ Prohibited:
• Spam, advertising, selling
• Content involving minors — immediate ban
• Threats, insults, harassment
• Abuse of report button (ban for false reports)
• Sharing personal data without consent

⚠️ Ban system:
• 1st report: warning
• 2nd report: 3 hour ban
• 3rd report: 24 hour ban
• 4th report: permanent ban

Press ✅ Accept Rules to continue."""

INTERESTS_MAP = {
    "simple": ["Разговор по душам 🗣", "Юмор и мемы 😂", "Советы по жизни 💡", "Музыка 🎵", "Игры 🎮"],
    "flirt":  ["Лёгкий флирт 😏", "Комплименты 💌", "Секстинг 🔥", "Виртуальные свидания 💑", "Флирт и игры 🎭"],
    "kink":   ["BDSM 🖤", "Bondage 🔗", "Roleplay 🎭", "Dom/Sub ⛓", "Pet play 🐾", "Другой фетиш ✨"],
}

MODE_NAMES = {"simple": "Просто общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}

# ====================== КЛАВИАТУРЫ ======================
def kb_lang():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]
    ], resize_keyboard=True)

def kb_rules():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Принять правила")]
    ], resize_keyboard=True)

def kb_search_type():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡ Анонимный поиск")],
        [KeyboardButton(text="🔍 Поиск по анкете")],
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="⚙️ Настройки поиска")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)

def kb_gender():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨 Парень"), KeyboardButton(text="👩 Девушка")],
        [KeyboardButton(text="⚧ Другое / Небинарный")]
    ], resize_keyboard=True)

def kb_mode():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💬 Просто общение")],
        [KeyboardButton(text="💋 Флирт")],
        [KeyboardButton(text="🔥 Kink / ролевые (18+)")]
    ], resize_keyboard=True)

def kb_interests(mode, selected):
    interests = INTERESTS_MAP.get(mode, [])
    buttons = []
    for interest in interests:
        mark = "✅ " if interest in selected else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{interest}",
            callback_data=f"int:{interest}"
        )])
    buttons.append([InlineKeyboardButton(text="✅ Готово — сохранить", callback_data="int:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_chat():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ Следующий"), KeyboardButton(text="❌ Стоп")],
        [KeyboardButton(text="🚩 Жалоба"), KeyboardButton(text="👍 Лайк")],
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def kb_cancel_search():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Отменить поиск")]
    ], resize_keyboard=True)

def kb_complaint_reasons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔞 Несовершеннолетние", callback_data="rep:minor")],
        [InlineKeyboardButton(text="💰 Спам / Реклама", callback_data="rep:spam")],
        [InlineKeyboardButton(text="😡 Угрозы / Оскорбления", callback_data="rep:abuse")],
        [InlineKeyboardButton(text="🔄 Другое", callback_data="rep:other")],
    ])

def kb_settings(uid):
    u = users.get(uid, {})
    accept_flirt = "✅" if u.get("accept_flirt", True) else "❌"
    accept_kink = "✅" if u.get("accept_kink", False) else "❌"
    accept_simple = "✅" if u.get("accept_simple", True) else "❌"
    only_own = "✅" if u.get("only_own_mode", False) else "❌"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{accept_simple} Принимать из 'Общение'", callback_data="set:simple")],
        [InlineKeyboardButton(text=f"{accept_flirt} Принимать из 'Флирт'", callback_data="set:flirt")],
        [InlineKeyboardButton(text=f"{accept_kink} Принимать из 'Kink'", callback_data="set:kink")],
        [InlineKeyboardButton(text=f"{only_own} Только свой режим (не смешивать)", callback_data="set:only_own")],
    ])

def kb_edit_profile():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit:name")],
        [InlineKeyboardButton(text="🎂 Изменить возраст", callback_data="edit:age")],
        [InlineKeyboardButton(text="⚧ Изменить пол", callback_data="edit:gender")],
        [InlineKeyboardButton(text="💬 Изменить режим", callback_data="edit:mode")],
        [InlineKeyboardButton(text="🎯 Изменить интересы", callback_data="edit:interests")],
    ])

# ====================== УТИЛИТЫ ======================
def get_lang(uid):
    return users.get(uid, {}).get("lang", "ru")

def is_banned(uid):
    if uid in ban_list:
        ban_until = ban_list[uid]
        if ban_until == "permanent":
            return True, "permanent"
        if datetime.now() < ban_until:
            return True, ban_until
        else:
            del ban_list[uid]
    return False, None

def apply_ban(uid):
    count = len([c for c in complaints.get(uid, []) if c.get("counted")])
    if count == 1:
        ban_list[uid] = datetime.now() + timedelta(hours=3)
        return "3 часа"
    elif count == 2:
        ban_list[uid] = datetime.now() + timedelta(hours=24)
        return "24 часа"
    elif count >= 3:
        ban_list[uid] = "permanent"
        return "навсегда"
    return None

def get_queue_for_mode(mode):
    if mode == "simple": return waiting_simple
    if mode == "flirt": return waiting_flirt
    if mode == "kink": return waiting_kink
    return waiting_anon

def get_rating(uid):
    u = users.get(uid, {})
    likes = u.get("likes", 0)
    dislikes = u.get("dislikes", 0)
    return likes - dislikes

async def cleanup_user(uid, state=None):
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink]:
        if uid in q:
            q.remove(uid)
    partner = active_chats.pop(uid, None)
    if partner:
        active_chats.pop(partner, None)
    if state:
        await state.clear()
    return partner

async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Начать / перезапустить"),
        BotCommand(command="find", description="Найти собеседника"),
        BotCommand(command="stop", description="Завершить чат"),
        BotCommand(command="next", description="Следующий собеседник"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="settings", description="Настройки поиска"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(commands)

# ====================== СТАРТ ======================
@dp.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await cleanup_user(uid, state)

    banned, until = is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer("🚫 Ты заблокирован навсегда за нарушение правил.")
        else:
            await message.answer(f"🚫 Ты заблокирован до {until.strftime('%H:%M %d.%m.%Y')}")
        return

    if not users.get(uid, {}).get("accepted_rules"):
        users.setdefault(uid, {})
        await state.set_state(Rules.waiting)
        await message.answer(WELCOME_TEXT, reply_markup=kb_lang())
    else:
        await message.answer("👋 С возвращением! Что хочешь сделать?", reply_markup=kb_search_type())

# ====================== ВЫБОР ЯЗЫКА ======================
@dp.message(StateFilter(Rules.waiting), F.text.in_(["🇷🇺 Русский", "🇬🇧 English"]))
async def choose_lang_rules(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = "ru" if "Русский" in message.text else "en"
    users[uid]["lang"] = lang
    rules_text = RULES_RU if lang == "ru" else RULES_EN
    await message.answer(rules_text, reply_markup=kb_rules())

# ====================== ПРИНЯТИЕ ПРАВИЛ ======================
@dp.message(StateFilter(Rules.waiting), F.text == "✅ Принять правила")
async def accept_rules(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    users[uid]["accepted_rules"] = True
    await state.clear()
    await message.answer(
        "✅ Правила приняты!\n\nВыбери как хочешь искать собеседника:",
        reply_markup=kb_search_type()
    )

# ====================== АНОНИМНЫЙ ПОИСК ======================
@dp.message(F.text == "⚡ Анонимный поиск", StateFilter("*"))
async def anon_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await cleanup_user(uid, state)

    banned, until = is_banned(uid)
    if banned:
        await message.answer("🚫 Ты заблокирован.")
        return

    users.setdefault(uid, {})["anon_mode"] = True
    await message.answer("⚡ Ищем анонимного собеседника...", reply_markup=kb_cancel_search())

    async with pairing_lock:
        partner = None
        for i, pid in enumerate(waiting_anon):
            if pid != uid:
                partner = waiting_anon.pop(i)
                break

        if partner:
            active_chats[uid] = partner
            active_chats[partner] = uid
            last_msg_time[uid] = last_msg_time[partner] = datetime.now()

            await state.set_state(Chat.chatting)
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).set_state(Chat.chatting)

            await bot.send_message(uid, "👤 Вы соединены с анонимным собеседником!\nМожете начинать общение. Удачи! 🎉", reply_markup=kb_chat())
            await bot.send_message(partner, "👤 Вы соединены с анонимным собеседником!\nМожете начинать общение. Удачи! 🎉", reply_markup=kb_chat())
        else:
            waiting_anon.append(uid)
            await state.set_state(Chat.waiting)

# ====================== ПОИСК ПО АНКЕТЕ ======================
@dp.message(F.text == "🔍 Поиск по анкете", StateFilter("*"))
async def full_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await cleanup_user(uid, state)
    u = users.get(uid, {})
    if u.get("name") and u.get("mode"):
        await cmd_find(message, state)
    else:
        await state.set_state(Reg.name)
        await message.answer("📝 Давай заполним анкету!\n\nКак тебя зовут?", reply_markup=ReplyKeyboardRemove())

# ====================== РЕГИСТРАЦИЯ ======================
@dp.message(StateFilter(Reg.name))
async def reg_name(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    users.setdefault(uid, {})["name"] = message.text.strip()[:20]
    await state.set_state(Reg.age)
    await message.answer("🎂 Сколько тебе лет?")

@dp.message(StateFilter(Reg.age))
async def reg_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not message.text.isdigit():
        await message.answer("❗ Введи число.")
        return
    age = int(message.text)
    if age < 16:
        await message.answer("❌ Тебе должно быть минимум 16 лет для использования бота.\n\nЕсли ты ошибся — введи правильный возраст.")
        return
    if age > 99:
        await message.answer("❗ Введи реальный возраст (16–99).")
        return
    users[uid]["age"] = age
    await state.set_state(Reg.gender)
    await message.answer("⚧ Выбери свой пол:", reply_markup=kb_gender())

@dp.message(StateFilter(Reg.gender))
async def reg_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text
    if "Парень" in txt:
        gender = "male"
    elif "Девушка" in txt:
        gender = "female"
    else:
        gender = "other"
    users[uid]["gender"] = gender
    await state.set_state(Reg.mode)
    await message.answer("💬 Выбери режим общения:", reply_markup=kb_mode())

@dp.message(StateFilter(Reg.mode))
async def reg_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text.lower()
    if "общение" in txt:
        mode = "simple"
    elif "флирт" in txt:
        mode = "flirt"
    else:
        mode = "kink"
    users[uid]["mode"] = mode
    users[uid]["temp_interests"] = []
    await state.set_state(Reg.interests)
    await message.answer(
        "🎯 Выбери 1–3 интереса (нажимай кнопки, потом «Готово»):",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer("👇", reply_markup=kb_interests(mode, []))

@dp.callback_query(F.data.startswith("int:"), StateFilter(Reg.interests))
async def reg_interest_pick(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    val = callback.data.split(":", 1)[1]
    if val == "done":
        interests = users[uid].get("temp_interests", [])
        if not interests:
            await callback.answer("Выбери хотя бы один интерес!", show_alert=True)
            return
        users[uid]["interests"] = interests
        users[uid].pop("temp_interests", None)
        await state.clear()
        await callback.message.edit_text("✅ Интересы сохранены!")
        await callback.message.answer("✅ Анкета заполнена! Начинаем поиск...", reply_markup=kb_search_type())
        await callback.answer()
        fake_msg = callback.message
        fake_msg.from_user = callback.from_user
        await cmd_find(fake_msg, state)
        return

    sel = users[uid].setdefault("temp_interests", [])
    if val in sel:
        sel.remove(val)
        await callback.answer(f"Убрано: {val}")
    elif len(sel) < 3:
        sel.append(val)
        await callback.answer(f"Добавлено: {val}")
    else:
        await callback.answer("Максимум 3 интереса!", show_alert=True)
        return

    mode = users[uid].get("mode", "simple")
    await callback.message.edit_reply_markup(reply_markup=kb_interests(mode, sel))

# ====================== ПОИСК ======================
@dp.message(F.text.in_(["🔍 Найти собеседника"]), StateFilter("*"))
@dp.message(Command("find"), StateFilter("*"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id

    banned, until = is_banned(uid)
    if banned:
        if until == "permanent":
            await message.answer("🚫 Ты заблокирован навсегда.")
        else:
            await message.answer(f"🚫 Ты заблокирован до {until.strftime('%H:%M %d.%m.%Y')}")
        return

    if uid in active_chats:
        await message.answer("Ты уже в чате! Используй /stop чтобы завершить.")
        return

    u = users.get(uid, {})
    if not u.get("mode"):
        await message.answer("Сначала заполни анкету!", reply_markup=kb_search_type())
        return

    mode = u["mode"]
    my_rating = get_rating(uid)
    my_interests = set(u.get("interests", []))
    only_own = u.get("only_own_mode", False)
    accept_simple = u.get("accept_simple", True)
    accept_flirt = u.get("accept_flirt", True)
    accept_kink = u.get("accept_kink", mode == "kink")

    online = len(get_queue_for_mode(mode))
    await message.answer(
        f"👥 В режиме {MODE_NAMES[mode]}: {online} чел. в очереди\n\n🔍 Ищем подходящего собеседника...",
        reply_markup=kb_cancel_search()
    )

    async with pairing_lock:
        partner = None

        def can_pair(pid):
            if pid == uid: return False
            pu = users.get(pid, {})
            p_mode = pu.get("mode", "")
            if only_own and p_mode != mode: return False
            p_accept = True
            if mode == "simple" and not pu.get("accept_simple", True): p_accept = False
            if mode == "flirt" and not pu.get("accept_flirt", True): p_accept = False
            if mode == "kink" and not pu.get("accept_kink", p_mode == "kink"): p_accept = False
            return p_accept

        def rating_diff(pid):
            return abs(get_rating(pid) - my_rating)

        # Собираем кандидатов
        queues_to_check = [get_queue_for_mode(mode)]
        if not only_own:
            if mode == "flirt" and accept_kink: queues_to_check.append(waiting_kink)
            if mode == "kink" and accept_flirt: queues_to_check.append(waiting_flirt)

        candidates = []
        for q in queues_to_check:
            for pid in q:
                if can_pair(pid):
                    # Совпадение интересов
                    p_interests = set(users.get(pid, {}).get("interests", []))
                    common = len(my_interests & p_interests)
                    candidates.append((pid, common, rating_diff(pid), q))

        if candidates:
            # Сортируем: сначала по совпадению интересов (больше = лучше), потом по рейтингу
            candidates.sort(key=lambda x: (-x[1], x[2]))
            best = candidates[0]
            partner = best[0]
            best[3].remove(partner)

        if partner:
            active_chats[uid] = partner
            active_chats[partner] = uid
            last_msg_time[uid] = last_msg_time[partner] = datetime.now()

            await state.set_state(Chat.chatting)
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).set_state(Chat.chatting)

            p = users.get(partner, {})
            g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
            p_profile = (
                f"👤 Собеседник найден!\n"
                f"Имя: {p.get('name', 'Аноним')}\n"
                f"Возраст: {p.get('age', '?')}\n"
                f"Пол: {g_map.get(p.get('gender', ''), '?')}\n"
                f"Режим: {MODE_NAMES.get(p.get('mode', ''), '—')}\n"
                f"Интересы: {', '.join(p.get('interests', [])) or '—'}\n"
                f"⭐ Рейтинг: {get_rating(partner)}"
            )
            my_profile = (
                f"👤 Собеседник найден!\n"
                f"Имя: {u.get('name', 'Аноним')}\n"
                f"Возраст: {u.get('age', '?')}\n"
                f"Пол: {g_map.get(u.get('gender', ''), '?')}\n"
                f"Режим: {MODE_NAMES.get(u.get('mode', ''), '—')}\n"
                f"Интересы: {', '.join(u.get('interests', [])) or '—'}\n"
                f"⭐ Рейтинг: {get_rating(uid)}"
            )

            await bot.send_message(uid, p_profile)
            await bot.send_message(partner, my_profile)
            await bot.send_message(uid, "✅ Начинайте общение!", reply_markup=kb_chat())
            await bot.send_message(partner, "✅ Начинайте общение!", reply_markup=kb_chat())
        else:
            q = get_queue_for_mode(mode)
            if uid not in q:
                q.append(uid)
            await state.set_state(Chat.waiting)
            asyncio.create_task(no_partner_notify(uid))

async def no_partner_notify(uid):
    await asyncio.sleep(60)
    if uid in (waiting_simple + waiting_flirt + waiting_kink + waiting_anon):
        try:
            await bot.send_message(
                uid,
                "😔 Похоже, сейчас никого нет в сети по твоим интересам.\n\nМожешь:\n• Подождать ещё\n• Изменить настройки поиска (/settings)\n• Попробовать другой режим",
                reply_markup=kb_search_type()
            )
        except:
            pass

# ====================== ЧАТ ======================
@dp.message(StateFilter(Chat.chatting))
async def relay(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text or ""

    # Кнопки чата
    if "Следующий" in txt or txt == "⏭ Следующий":
        await end_chat(uid, state, go_next=True)
        return
    if "Стоп" in txt or "❌" in txt:
        await end_chat(uid, state, go_next=False)
        return
    if "Жалоба" in txt or "🚩" in txt:
        await state.set_state(Complaint.reason)
        await message.answer("🚩 Укажи причину жалобы:", reply_markup=kb_complaint_reasons())
        return
    if "Лайк" in txt or "👍" in txt:
        await give_like(uid, message)
        return
    if "Главное меню" in txt or "🏠" in txt:
        await end_chat(uid, state, go_next=False)
        return

    if uid not in active_chats:
        await state.clear()
        await message.answer("Ты не в чате.", reply_markup=kb_search_type())
        return

    partner = active_chats[uid]

    # Антифлуд
    now = datetime.now()
    msg_count.setdefault(uid, [])
    msg_count[uid] = [t for t in msg_count[uid] if (now - t).total_seconds() < 5]
    if len(msg_count[uid]) >= 5:
        await message.answer("⚠️ Не спамь! Подожди немного.")
        return
    msg_count[uid].append(now)
    last_msg_time[uid] = last_msg_time[partner] = now

    try:
        if message.text:
            await bot.send_message(partner, message.text)
        elif message.sticker:
            await bot.send_sticker(partner, message.sticker.file_id)
        elif message.photo:
            await bot.send_photo(partner, message.photo[-1].file_id, caption=message.caption)
        elif message.voice:
            await bot.send_voice(partner, message.voice.file_id)
        elif message.video:
            await bot.send_video(partner, message.video.file_id, caption=message.caption)
        elif message.video_note:
            await bot.send_video_note(partner, message.video_note.file_id)
        elif message.document:
            await bot.send_document(partner, message.document.file_id, caption=message.caption)
        elif message.audio:
            await bot.send_audio(partner, message.audio.file_id)
    except:
        pass

async def end_chat(uid, state, go_next=False):
    partner = active_chats.pop(uid, None)
    if partner:
        active_chats.pop(partner, None)
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink]:
        if uid in q: q.remove(uid)
    await state.clear()

    await bot.send_message(uid, "💔 Чат завершён.", reply_markup=kb_search_type())
    if partner:
        try:
            await bot.send_message(partner, "😔 Собеседник покинул чат.", reply_markup=kb_search_type())
            pkey = StorageKey(bot_id=bot.id, chat_id=partner, user_id=partner)
            await FSMContext(dp.storage, key=pkey).clear()
        except:
            pass

    if go_next:
        class FakeMsg:
            from_user = type("u", (), {"id": uid})()
            text = ""
        await cmd_find(FakeMsg(), state)

# ====================== ЛАЙК ======================
async def give_like(uid, message):
    if uid not in active_chats:
        await message.answer("Ты не в чате.")
        return
    partner = active_chats[uid]
    users.setdefault(partner, {})
    users[partner]["likes"] = users[partner].get("likes", 0) + 1
    users.setdefault(uid, {})
    users[uid]["dislikes"] = users[uid].get("dislikes", 0)  # just init
    await message.answer("👍 Лайк отправлен!")
    try:
        await bot.send_message(partner, "👍 Твой собеседник поставил тебе лайк!")
    except:
        pass

# ====================== ЖАЛОБА ======================
@dp.callback_query(F.data.startswith("rep:"), StateFilter(Complaint.reason))
async def handle_complaint(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    reason = callback.data.split(":", 1)[1]
    reason_text = {
        "minor": "Несовершеннолетние",
        "spam": "Спам / Реклама",
        "abuse": "Угрозы / Оскорбления",
        "other": "Другое"
    }.get(reason, "Другое")

    partner = active_chats.get(uid)
    if not partner:
        await callback.message.edit_text("Ты не в чате.")
        await state.clear()
        return

    # Сохраняем жалобу
    complaints.setdefault(partner, []).append({
        "from": uid,
        "reason": reason_text,
        "time": datetime.now(),
        "counted": True
    })

    ban_msg = apply_ban(partner)

    await callback.message.edit_text(f"🚩 Жалоба отправлена. Причина: {reason_text}")

    # Завершаем чат
    active_chats.pop(uid, None)
    active_chats.pop(partner, None)
    await state.clear()

    await bot.send_message(uid, "Чат завершён после жалобы.", reply_markup=kb_search_type())

    if ban_msg:
        try:
            await bot.send_message(
                partner,
                f"🚫 На тебя поступила жалоба ({reason_text}).\nТы заблокирован на {ban_msg}.",
                reply_markup=ReplyKeyboardRemove()
            )
        except:
            pass
    else:
        try:
            await bot.send_message(partner, "⚠️ На тебя поступила жалоба. Будь внимательнее!", reply_markup=kb_search_type())
        except:
            pass

    await callback.answer()

# ====================== ОТМЕНА ПОИСКА ======================
@dp.message(F.text == "❌ Отменить поиск", StateFilter("*"))
async def cancel_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    removed = False
    for q in [waiting_anon, waiting_simple, waiting_flirt, waiting_kink]:
        if uid in q:
            q.remove(uid)
            removed = True
    await state.clear()
    if removed:
        await message.answer("❌ Поиск отменён.", reply_markup=kb_search_type())
    else:
        await message.answer("Ты не в поиске.", reply_markup=kb_search_type())

# ====================== СТОП ======================
@dp.message(Command("stop"), StateFilter("*"))
async def cmd_stop(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await end_chat(uid, state, go_next=False)

@dp.message(Command("next"), StateFilter("*"))
async def cmd_next(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await end_chat(uid, state, go_next=True)

# ====================== ПРОФИЛЬ ======================
@dp.message(F.text == "👤 Мой профиль", StateFilter("*"))
@dp.message(Command("profile"), StateFilter("*"))
async def show_profile(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    u = users.get(uid, {})
    if not u.get("name"):
        await message.answer("Анкета не заполнена. Нажми '🔍 Поиск по анкете'", reply_markup=kb_search_type())
        return
    g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
    text = (
        f"👤 Твой профиль:\n"
        f"Имя: {u.get('name', '—')}\n"
        f"Возраст: {u.get('age', '—')}\n"
        f"Пол: {g_map.get(u.get('gender', ''), '—')}\n"
        f"Режим: {MODE_NAMES.get(u.get('mode', ''), '—')}\n"
        f"Интересы: {', '.join(u.get('interests', [])) or '—'}\n"
        f"⭐ Рейтинг: {get_rating(uid)}\n"
        f"👍 Лайков: {u.get('likes', 0)}"
    )
    await message.answer(text, reply_markup=kb_edit_profile())

# ====================== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ======================
@dp.callback_query(F.data.startswith("edit:"))
async def edit_profile(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    await callback.answer()

    if field == "name":
        await state.set_state(EditProfile.name)
        await callback.message.answer("✏️ Введи новое имя:")
    elif field == "age":
        await state.set_state(EditProfile.age)
        await callback.message.answer("🎂 Введи новый возраст:")
    elif field == "gender":
        await state.set_state(EditProfile.gender)
        await callback.message.answer("⚧ Выбери пол:", reply_markup=kb_gender())
    elif field == "mode":
        await state.set_state(EditProfile.mode)
        await callback.message.answer("💬 Выбери режим:", reply_markup=kb_mode())
    elif field == "interests":
        mode = users.get(uid, {}).get("mode", "simple")
        users[uid]["temp_interests"] = []
        await state.set_state(EditProfile.interests)
        await callback.message.answer("🎯 Выбери интересы:", reply_markup=kb_interests(mode, []))

@dp.message(StateFilter(EditProfile.name))
async def edit_name(message: types.Message, state: FSMContext):
    users[message.from_user.id]["name"] = message.text.strip()[:20]
    await state.clear()
    await message.answer("✅ Имя обновлено!", reply_markup=kb_search_type())

@dp.message(StateFilter(EditProfile.age))
async def edit_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer("❗ Введи число от 16 до 99")
        return
    users[uid]["age"] = int(message.text)
    await state.clear()
    await message.answer("✅ Возраст обновлён!", reply_markup=kb_search_type())

@dp.message(StateFilter(EditProfile.gender))
async def edit_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text
    if "Парень" in txt: users[uid]["gender"] = "male"
    elif "Девушка" in txt: users[uid]["gender"] = "female"
    else: users[uid]["gender"] = "other"
    await state.clear()
    await message.answer("✅ Пол обновлён!", reply_markup=kb_search_type())

@dp.message(StateFilter(EditProfile.mode))
async def edit_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    txt = message.text.lower()
    if "общение" in txt: users[uid]["mode"] = "simple"
    elif "флирт" in txt: users[uid]["mode"] = "flirt"
    else: users[uid]["mode"] = "kink"
    users[uid]["temp_interests"] = []
    mode = users[uid]["mode"]
    await state.set_state(EditProfile.interests)
    await message.answer("🎯 Теперь выбери интересы для нового режима:", reply_markup=kb_interests(mode, []))

@dp.callback_query(F.data.startswith("int:"), StateFilter(EditProfile.interests))
async def edit_interest_pick(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    val = callback.data.split(":", 1)[1]
    if val == "done":
        interests = users[uid].get("temp_interests", [])
        if not interests:
            await callback.answer("Выбери хотя бы один!", show_alert=True)
            return
        users[uid]["interests"] = interests
        users[uid].pop("temp_interests", None)
        await state.clear()
        await callback.message.edit_text("✅ Интересы обновлены!")
        await callback.message.answer("Профиль обновлён!", reply_markup=kb_search_type())
        await callback.answer()
        return

    sel = users[uid].setdefault("temp_interests", [])
    if val in sel:
        sel.remove(val)
        await callback.answer(f"Убрано: {val}")
    elif len(sel) < 3:
        sel.append(val)
        await callback.answer(f"Добавлено: {val}")
    else:
        await callback.answer("Максимум 3!", show_alert=True)
        return

    mode = users[uid].get("mode", "simple")
    await callback.message.edit_reply_markup(reply_markup=kb_interests(mode, sel))

# ====================== НАСТРОЙКИ ======================
@dp.message(F.text == "⚙️ Настройки поиска", StateFilter("*"))
@dp.message(Command("settings"), StateFilter("*"))
async def show_settings(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await message.answer(
        "⚙️ Настройки поиска:\n\nВыбери от кого хочешь получать запросы:",
        reply_markup=kb_settings(uid)
    )

@dp.callback_query(F.data.startswith("set:"))
async def toggle_setting(callback: types.CallbackQuery):
    uid = callback.from_user.id
    key = callback.data.split(":", 1)[1]
    u = users.setdefault(uid, {})

    if key == "simple":
        u["accept_simple"] = not u.get("accept_simple", True)
    elif key == "flirt":
        u["accept_flirt"] = not u.get("accept_flirt", True)
    elif key == "kink":
        u["accept_kink"] = not u.get("accept_kink", False)
    elif key == "only_own":
        u["only_own_mode"] = not u.get("only_own_mode", False)

    await callback.message.edit_reply_markup(reply_markup=kb_settings(uid))
    await callback.answer("✅ Настройка изменена")

# ====================== ПОМОЩЬ ======================
@dp.message(F.text == "❓ Помощь", StateFilter("*"))
@dp.message(Command("help"), StateFilter("*"))
async def show_help(message: types.Message, state: FSMContext):
    await message.answer(
        "🆘 Помощь:\n\n"
        "⚡ Анонимный поиск — быстро найти собеседника без анкеты\n"
        "🔍 Поиск по анкете — поиск по режиму и интересам\n"
        "⚙️ Настройки — настрой от кого получать запросы\n"
        "👤 Профиль — посмотри и отредактируй анкету\n\n"
        "Во время чата:\n"
        "⏭ Следующий — найти другого собеседника\n"
        "❌ Стоп — завершить чат\n"
        "🚩 Жалоба — пожаловаться на нарушение\n"
        "👍 Лайк — поставить лайк собеседнику\n\n"
        "Если что-то сломалось — напиши /start",
        reply_markup=kb_search_type()
    )

# ====================== ТАЙМЕР НЕАКТИВНОСТИ ======================
async def inactivity_checker():
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        to_end = []
        for uid, partner in list(active_chats.items()):
            if uid < partner:  # чтобы не обрабатывать пару дважды
                last = max(last_msg_time.get(uid, now), last_msg_time.get(partner, now))
                if (now - last).total_seconds() > 420:  # 7 минут
                    to_end.append((uid, partner))

        for uid, partner in to_end:
            active_chats.pop(uid, None)
            active_chats.pop(partner, None)
            try:
                await bot.send_message(uid, "⏰ Чат завершён из-за неактивности (7 минут).", reply_markup=kb_search_type())
            except: pass
            try:
                await bot.send_message(partner, "⏰ Чат завершён из-за неактивности (7 минут).", reply_markup=kb_search_type())
            except: pass

# ====================== ЗАПУСК ======================
async def main():
    await set_bot_commands()
    asyncio.create_task(inactivity_checker())
    print("🚀 MatchMe запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

