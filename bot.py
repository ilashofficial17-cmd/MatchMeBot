import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

users = {}
waiting_queue_simple = []
waiting_queue_flirt = []
waiting_queue_kink = []
active_chats = {}
pairing_lock = asyncio.Lock()

class Registration(StatesGroup):
    language = State()
    name = State()
    age = State()
    gender = State()
    mode = State()
    interests = State()

class Searching(StatesGroup):
    waiting = State()
    chatting = State()

TEXTS = {
    "ru": {
        "welcome": "👋 Привет! Добро пожаловать в MatchMe",
        "enter_name": "Как тебя зовут? (будет видно собеседнику)",
        "enter_age": "Сколько тебе лет?",
        "choose_gender": "Выбери свой пол:",
        "choose_mode": "Выбери режим общения:",
        "choose_interests": "Напиши через запятую 1–3 интереса:",
        "profile_saved": "✅ Анкета сохранена!",
        "searching": "🔍 Ищем собеседника...",
        "found": "✅ Собеседник найден!",
        "chat_ended": "💔 Чат завершён.",
        "partner_left": "😔 Собеседник покинул чат.",
        "male": "👨 Парень",
        "female": "👩 Девушка",
        "age_error": "Пожалуйста введи число от 16 до 99",
        "need_profile": "Сначала заполни анкету",
        "mode_simple": "1️⃣ Просто общение",
        "mode_flirt": "2️⃣ Флирт",
        "mode_kink": "3️⃣ Kink / ролевые (18+)",
        "hint_simple": "Разговор по душам, Юмор и мемы, Советы по жизни",
        "hint_flirt": "Лёгкий флирт, Комплименты, Секстинг",
        "hint_kink": "BDSM, Bondage, Roleplay, Dominance/Sub, Foot fetish, Pet play",
        "cancel_search": "❌ Поиск отменён",
        "not_in_search": "Ты не в поиске",
        "not_in_chat": "Ты не в чате",
        "already_in_chat": "Ты уже в чате!",
        "restart_done": "🔄 Бот полностью перезапущен!",
        "help": "🆘 Помощь:\nНажимай кнопки меню.\nЕсли что-то сломалось — нажми «🔄 Перезапустить»",
        "online_count": "👥 Сейчас онлайн в режиме {mode}: {count} человек\n\n🔍 Начинаем поиск...",
        "profile_text": "👤 Твой профиль:\nИмя: {name}\nВозраст: {age}\nПол: {gender}\nРежим: {mode}\nИнтересы: {interests}",
        "partner_profile": "👤 Собеседник найден!\nИмя: {name}\nВозраст: {age}\nПол: {gender}\nРежим: {mode}\nИнтересы: {interests}",
        "gender_male": "Парень",
        "gender_female": "Девушка",
    },
    "en": {
        "welcome": "👋 Hi! Welcome to MatchMe",
        "enter_name": "What's your name? (visible to your partner)",
        "enter_age": "How old are you?",
        "choose_gender": "Choose your gender:",
        "choose_mode": "Choose chat mode:",
        "choose_interests": "Write 1–3 interests separated by comma:",
        "profile_saved": "✅ Profile saved!",
        "searching": "🔍 Looking for a partner...",
        "found": "✅ Partner found!",
        "chat_ended": "💔 Chat ended.",
        "partner_left": "😔 Your partner left the chat.",
        "male": "👨 Male",
        "female": "👩 Female",
        "age_error": "Please enter a number between 16 and 99",
        "need_profile": "Please fill out your profile first",
        "mode_simple": "1️⃣ Just chatting",
        "mode_flirt": "2️⃣ Flirt",
        "mode_kink": "3️⃣ Kink / roleplay (18+)",
        "hint_simple": "Deep talks, Humor & memes, Life advice",
        "hint_flirt": "Light flirt, Compliments, Sexting",
        "hint_kink": "BDSM, Bondage, Roleplay, Dominance/Sub, Foot fetish, Pet play",
        "cancel_search": "❌ Search cancelled",
        "not_in_search": "You are not searching",
        "not_in_chat": "You are not in a chat",
        "already_in_chat": "You are already in a chat!",
        "restart_done": "🔄 Bot restarted!",
        "help": "🆘 Help:\nUse the menu buttons.\nIf something breaks — press «🔄 Restart»",
        "online_count": "👥 Online in {mode} mode: {count} people\n\n🔍 Searching...",
        "profile_text": "👤 Your profile:\nName: {name}\nAge: {age}\nGender: {gender}\nMode: {mode}\nInterests: {interests}",
        "partner_profile": "👤 Partner found!\nName: {name}\nAge: {age}\nGender: {gender}\nMode: {mode}\nInterests: {interests}",
        "gender_male": "Male",
        "gender_female": "Female",
    }
}

def t(uid, key, **kwargs):
    lang = users.get(uid, {}).get("lang", "ru")
    text = TEXTS[lang].get(key, key)
    return text.format(**kwargs) if kwargs else text

def get_main_menu(lang="ru"):
    if lang == "ru":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🔍 Найти собеседника")],
            [KeyboardButton(text="👤 Мой профиль")],
            [KeyboardButton(text="🔄 Перезапустить")],
            [KeyboardButton(text="❓ Помощь")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🔍 Find partner")],
            [KeyboardButton(text="👤 My profile")],
            [KeyboardButton(text="🔄 Restart")],
            [KeyboardButton(text="❓ Help")]
        ], resize_keyboard=True)

def get_chat_menu(lang="ru"):
    if lang == "ru":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🔄 Следующий собеседник")],
            [KeyboardButton(text="❌ Завершить чат")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🔄 Next partner")],
            [KeyboardButton(text="❌ End chat")]
        ], resize_keyboard=True)

def get_cancel_search_menu(lang="ru"):
    if lang == "ru":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="❌ Отменить поиск")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="❌ Cancel search")]
        ], resize_keyboard=True)

def get_lang(uid):
    return users.get(uid, {}).get("lang", "ru")

def get_mode_text(mode, lang):
    modes = {
        "ru": {"simple": "Просто общение", "flirt": "Флирт", "kink": "Kink / ролевые"},
        "en": {"simple": "Just chatting", "flirt": "Flirt", "kink": "Kink / roleplay"}
    }
    return modes[lang].get(mode, "—")

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]
    ], resize_keyboard=True)
    await message.answer("🌐 Выбери язык / Choose language:", reply_markup=kb)
    await state.set_state(Registration.language)

@dp.message(F.text.in_(["🔄 Перезапустить", "🔄 Restart"]))
async def cmd_restart(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    for q in [waiting_queue_simple, waiting_queue_flirt, waiting_queue_kink]:
        if uid in q:
            q.remove(uid)
    if uid in active_chats:
        partner = active_chats.pop(uid, None)
        if partner:
            active_chats.pop(partner, None)
    lang = get_lang(uid)
    await message.answer(t(uid, "restart_done"))
    await cmd_start(message, state)

# ====================== РЕГИСТРАЦИЯ ======================
@dp.message(Registration.language)
async def choose_language(message: types.Message, state: FSMContext):
    lang = "ru" if "Русский" in message.text else "en"
    users[message.from_user.id] = {"lang": lang}
    await state.update_data(lang=lang)
    await message.answer(TEXTS[lang]["welcome"], reply_markup=ReplyKeyboardRemove())
    await message.answer(TEXTS[lang]["enter_name"])
    await state.set_state(Registration.name)

@dp.message(Registration.name)
async def enter_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    uid = message.from_user.id
    await message.answer(t(uid, "enter_age"))
    await state.set_state(Registration.age)

@dp.message(Registration.age)
async def enter_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer(t(uid, "age_error"))
        return
    await state.update_data(age=int(message.text))
    lang = get_lang(uid)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=TEXTS[lang]["male"]), KeyboardButton(text=TEXTS[lang]["female"])]
    ], resize_keyboard=True)
    await message.answer(t(uid, "choose_gender"), reply_markup=kb)
    await state.set_state(Registration.gender)

@dp.message(Registration.gender)
async def enter_gender(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = message.from_user.id
    lang = get_lang(uid)
    gender = "male" if any(x in message.text for x in ["Парень", "Male"]) else "female"
    users[uid].update({"name": data["name"], "age": data["age"], "gender": gender})
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=TEXTS[lang]["mode_simple"])],
        [KeyboardButton(text=TEXTS[lang]["mode_flirt"])],
        [KeyboardButton(text=TEXTS[lang]["mode_kink"])]
    ], resize_keyboard=True)
    await message.answer(t(uid, "choose_mode"), reply_markup=kb)
    await state.set_state(Registration.mode)

@dp.message(Registration.mode)
async def choose_mode(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = get_lang(uid)
    text = message.text.lower()
    if "просто" in text or "chatting" in text:
        mode = "simple"
        hint = TEXTS[lang]["hint_simple"]
    elif "флирт" in text or "flirt" in text:
        mode = "flirt"
        hint = TEXTS[lang]["hint_flirt"]
    else:
        mode = "kink"
        hint = TEXTS[lang]["hint_kink"]
    users[uid]["mode"] = mode
    await state.update_data(mode=mode)
    await message.answer(f"✅ {message.text}\n\n{t(uid, 'choose_interests')}\n{hint}")
    await state.set_state(Registration.interests)

@dp.message(Registration.interests)
async def choose_interests(message: types.Message, state: FSMContext):
    interests = [x.strip() for x in message.text.split(",") if x.strip()][:3]
    uid = message.from_user.id
    lang = get_lang(uid)
    users[uid]["interests"] = interests
    await state.clear()
    await message.answer(t(uid, "profile_saved"), reply_markup=get_main_menu(lang))

# ====================== МЕНЮ ======================
@dp.message(F.text.in_(["👤 Мой профиль", "👤 My profile"]))
async def show_profile(message: types.Message):
    uid = message.from_user.id
    if uid not in users or "mode" not in users[uid]:
        await message.answer(t(uid, "need_profile"))
        return
    u = users[uid]
    lang = get_lang(uid)
    gender_text = t(uid, "gender_male") if u["gender"] == "male" else t(uid, "gender_female")
    mode_text = get_mode_text(u["mode"], lang)
    interests_text = ", ".join(u.get("interests", [])) or "—"
    await message.answer(t(uid, "profile_text", name=u["name"], age=u["age"], gender=gender_text, mode=mode_text, interests=interests_text))

@dp.message(F.text.in_(["❓ Помощь", "❓ Help"]))
async def show_help(message: types.Message):
    uid = message.from_user.id
    lang = get_lang(uid)
    await message.answer(t(uid, "help"), reply_markup=get_main_menu(lang))

# ====================== ПОИСК ======================
@dp.message(F.text.in_(["🔍 Найти собеседника", "🔍 Find partner"]))
@dp.message(Command("find"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = get_lang(uid)
    if uid not in users or "mode" not in users[uid]:
        await message.answer(t(uid, "need_profile"))
        return
    if uid in active_chats:
        await message.answer(t(uid, "already_in_chat"))
        return

    mode = users[uid]["mode"]
    mode_text = get_mode_text(mode, lang)

    if mode == "simple":
        online = len(waiting_queue_simple)
    elif mode == "flirt":
        online = len(waiting_queue_flirt)
    else:
        online = len(waiting_queue_kink)

    await message.answer(t(uid, "online_count", mode=mode_text, count=online), reply_markup=get_cancel_search_menu(lang))

    async with pairing_lock:
        partner_id = None
        my_interests = set(users[uid].get("interests", []))

        if mode == "simple":
            queue = waiting_queue_simple
            fallback = None
        elif mode == "flirt":
            queue = waiting_queue_flirt
            fallback = waiting_queue_kink
        else:
            queue = waiting_queue_kink
            fallback = waiting_queue_flirt

        for i in range(len(queue)):
            p_id = queue[i]
            if p_id != uid and set(users[p_id].get("interests", [])) & my_interests:
                partner_id = queue.pop(i)
                break

        if not partner_id and queue:
            for i in range(len(queue)):
                if queue[i] != uid:
                    partner_id = queue.pop(i)
                    break

        if not partner_id and fallback:
            for i in range(len(fallback)):
                if fallback[i] != uid:
                    partner_id = fallback.pop(i)
                    break

        if partner_id:
            active_chats[uid] = partner_id
            active_chats[partner_id] = uid

            await state.set_state(Searching.chatting)
            key = StorageKey(bot_id=bot.id, chat_id=partner_id, user_id=partner_id)
            await FSMContext(dp.storage, key=key).set_state(Searching.chatting)

            p = users.get(partner_id, {})
            p_lang = get_lang(partner_id)
            p_gender = t(partner_id, "gender_male") if p.get("gender") == "male" else t(partner_id, "gender_female")
            p_mode = get_mode_text(p.get("mode", "simple"), p_lang)
            p_interests = ", ".join(p.get("interests", [])) or "—"

            my_gender = t(uid, "gender_male") if users[uid].get("gender") == "male" else t(uid, "gender_female")
            my_mode = get_mode_text(users[uid].get("mode", "simple"), lang)
            my_interests_str = ", ".join(users[uid].get("interests", [])) or "—"

            await bot.send_message(uid, t(uid, "partner_profile", name=p.get("name", "Аноним"), age=p.get("age", "?"), gender=p_gender, mode=p_mode, interests=p_interests))
            await bot.send_message(partner_id, t(partner_id, "partner_profile", name=users[uid].get("name", "Аноним"), age=users[uid].get("age", "?"), gender=my_gender, mode=my_mode, interests=my_interests_str))

            await bot.send_message(uid, t(uid, "found"), reply_markup=get_chat_menu(lang))
            await bot.send_message(partner_id, t(partner_id, "found"), reply_markup=get_chat_menu(p_lang))
        else:
            if mode == "simple":
                waiting_queue_simple.append(uid)
            elif mode == "flirt":
                waiting_queue_flirt.append(uid)
            else:
                waiting_queue_kink.append(uid)
            await state.set_state(Searching.waiting)

# ====================== ОТМЕНА ПОИСКА ======================
@dp.message(F.text.in_(["❌ Отменить поиск", "❌ Cancel search"]))
async def cancel_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = get_lang(uid)
    removed = False
    for q in [waiting_queue_simple, waiting_queue_flirt, waiting_queue_kink]:
        if uid in q:
            q.remove(uid)
            removed = True
            break
    if removed:
        await state.clear()
        await message.answer(t(uid, "cancel_search"), reply_markup=get_main_menu(lang))
    else:
        await message.answer(t(uid, "not_in_search"), reply_markup=get_main_menu(lang))

# ====================== ЧАТ ======================
@dp.message(F.text.in_(["❌ Завершить чат", "❌ End chat", "🔄 Следующий собеседник", "🔄 Next partner"]))
@dp.message(Command("stop"))
async def cmd_stop_or_next(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = get_lang(uid)
    is_next = "Следующий" in (message.text or "") or "Next" in (message.text or "")

    if uid in active_chats:
        partner_id = active_chats.pop(uid, None)
        if partner_id:
            active_chats.pop(partner_id, None)
        await state.clear()
        await message.answer(t(uid, "chat_ended"), reply_markup=get_main_menu(lang))
        try:
            p_lang = get_lang(partner_id)
            await bot.send_message(partner_id, t(partner_id, "partner_left"), reply_markup=get_main_menu(p_lang))
        except:
            pass
        if is_next:
            await asyncio.sleep(0.3)
            await cmd_find(message, state)
    else:
        await message.answer(t(uid, "not_in_chat"), reply_markup=get_main_menu(lang))

@dp.message(Searching.chatting)
async def relay_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await state.clear()
        return
    partner_id = active_chats[uid]
    try:
        await bot.send_chat_action(partner_id, "typing")
    except:
        pass
    try:
        if message.text:
            await bot.send_message(partner_id, message.text)
        elif message.sticker:
            await bot.send_sticker(partner_id, message.sticker.file_id)
        elif message.photo:
            await bot.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption)
        elif message.voice:
            await bot.send_voice(partner_id, message.voice.file_id)
        elif message.video:
            await bot.send_video(partner_id, message.video.file_id, caption=message.caption)
        elif message.video_note:
            await bot.send_video_note(partner_id, message.video_note.file_id)
        elif message.document:
            await bot.send_document(partner_id, message.document.file_id, caption=message.caption)
    except:
        pass

async def main():
    print("🚀 MatchMe Bot запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

        
