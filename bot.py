import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хранилище
users = {}
waiting_queue = []
active_chats = {}

class Registration(StatesGroup):
    language = State()
    name = State()
    age = State()
    gender = State()

class Searching(StatesGroup):
    waiting = State()
    chatting = State()

TEXTS = {
    "ru": {
        "welcome": "👋 Привет! Я MatchMe — анонимный чат для знакомств.\n\nДавай заполним анкету!",
        "enter_name": "Как тебя зовут? (будет видно собеседнику)",
        "enter_age": "Сколько тебе лет?",
        "choose_gender": "Выбери свой пол:",
        "profile_saved": "✅ Анкета сохранена!\n\nНапиши /find чтобы найти собеседника\nНапиши /profile чтобы посмотреть анкету",
        "searching": "🔍 Ищем собеседника...\nНапиши /stop чтобы отменить поиск",
        "found": "✅ Собеседник найден! Можете общаться анонимно.\nНапиши /stop чтобы завершить чат",
        "stopped_searching": "❌ Поиск отменён",
        "chat_ended": "💔 Чат завершён\n\nНапиши /find чтобы найти нового собеседника",
        "partner_left": "😔 Собеседник покинул чат\n\nНапиши /find чтобы найти нового",
        "male": "👨 Парень",
        "female": "👩 Девушка",
        "profile": "👤 Твоя анкета:\nИмя: {name}\nВозраст: {age}\nПол: {gender}",
        "age_error": "Пожалуйста введи число от 16 до 99",
        "already_chatting": "Ты уже в чате! Напиши /stop чтобы завершить",
        "need_profile": "Сначала заполни анкету! Напиши /start",
    },
    "en": {
        "welcome": "👋 Hi! I'm MatchMe — anonymous chat for meeting people.\n\nLet's fill out your profile!",
        "enter_name": "What's your name? (will be visible to your partner)",
        "enter_age": "How old are you?",
        "choose_gender": "Choose your gender:",
        "profile_saved": "✅ Profile saved!\n\nType /find to find a partner\nType /profile to view your profile",
        "searching": "🔍 Looking for a partner...\nType /stop to cancel",
        "found": "✅ Partner found! You can chat anonymously.\nType /stop to end the chat",
        "stopped_searching": "❌ Search cancelled",
        "chat_ended": "💔 Chat ended\n\nType /find to find a new partner",
        "partner_left": "😔 Your partner left the chat\n\nType /find to find a new one",
        "male": "👨 Male",
        "female": "👩 Female",
        "profile": "👤 Your profile:\nName: {name}\nAge: {age}\nGender: {gender}",
        "age_error": "Please enter a number between 16 and 99",
        "already_chatting": "You're already in a chat! Type /stop to end it",
        "need_profile": "Please fill out your profile first! Type /start",
    }
}

def t(user_id, key, **kwargs):
    lang = users.get(user_id, {}).get("lang", "ru")
    text = TEXTS[lang].get(key, key)
    return text.format(**kwargs) if kwargs else text

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English")]
    ], resize_keyboard=True)
    await message.answer("🌐 Выбери язык / Choose language:", reply_markup=kb)
    await state.set_state(Registration.language)

@dp.message(Registration.language)
async def choose_language(message: types.Message, state: FSMContext):
    lang = "ru" if "Русский" in message.text else "en"
    users[message.from_user.id] = {"lang": lang}
    await state.update_data(lang=lang)
    await message.answer(t(message.from_user.id, "welcome"), reply_markup=ReplyKeyboardRemove())
    await message.answer(t(message.from_user.id, "enter_name"))
    await state.set_state(Registration.name)

@dp.message(Registration.name)
async def enter_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(t(message.from_user.id, "enter_age"))
    await state.set_state(Registration.age)

@dp.message(Registration.age)
async def enter_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (16 <= int(message.text) <= 99):
        await message.answer(t(message.from_user.id, "age_error"))
        return
    await state.update_data(age=int(message.text))
    lang = users[message.from_user.id]["lang"]
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=TEXTS[lang]["male"]), KeyboardButton(text=TEXTS[lang]["female"])]
    ], resize_keyboard=True)
    await message.answer(t(message.from_user.id, "choose_gender"), reply_markup=kb)
    await state.set_state(Registration.gender)

@dp.message(Registration.gender)
async def enter_gender(message: types.Message, state: FSMContext):
    data = await state.get_data()
    gender = "male" if "Парень" in message.text or "Male" in message.text else "female"
    users[message.from_user.id].update({
        "name": data["name"],
        "age": data["age"],
        "gender": gender,
        "lang": data.get("lang", "ru")
    })
    await state.clear()
    await message.answer(t(message.from_user.id, "profile_saved"), reply_markup=ReplyKeyboardRemove())

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    uid = message.from_user.id
    if uid not in users or "name" not in users[uid]:
        await message.answer(t(uid, "need_profile"))
        return
    u = users[uid]
    lang = u["lang"]
    gender_text = TEXTS[lang]["male"] if u["gender"] == "male" else TEXTS[lang]["female"]
    await message.answer(t(uid, "profile", name=u["name"], age=u["age"], gender=gender_text))

@dp.message(Command("find"))
async def cmd_find(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    print(f"[DEBUG] --- /find от {uid} ---")
    print(f"[DEBUG] Очередь: {waiting_queue}")
    print(f"[DEBUG] Активные чаты: {active_chats}")

    if uid not in users or "name" not in users[uid]:
        await message.answer(t(uid, "need_profile"))
        return

    if uid in active_chats:
        await message.answer(t(uid, "already_chatting"))
        return

    if uid in waiting_queue:
        print(f"[DEBUG] {uid} уже в очереди")
        await message.answer("🔄 Ты уже в поиске! Жди...")
        return

    partner_id = None
    for queued_id in waiting_queue[:]:
        if queued_id != uid:
            partner_id = queued_id
            waiting_queue.remove(queued_id)
            break

    if partner_id:
        print(f"[DEBUG] 🔥 СОЕДИНИЛИ! {uid} <-> {partner_id}")
        active_chats[uid] = partner_id
        active_chats[partner_id] = uid

        await state.set_state(Searching.chatting)

        partner_state = dp.fsm.storage.get_context(bot=bot, chat_id=partner_id, user_id=partner_id)
        await partner_state.set_state(Searching.chatting)

        await bot.send_message(uid, t(uid, "found"))
        await bot.send_message(partner_id, t(partner_id, "found"))
    else:
        waiting_queue.append(uid)
        print(f"[DEBUG] Добавили {uid} в очередь")
        await state.set_state(Searching.waiting)
        await message.answer(t(uid, "searching"))

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    print(f"[DEBUG] --- /stop от {uid} ---")
    print(f"[DEBUG] Очередь: {waiting_queue} | Чаты: {active_chats}")

    if uid in waiting_queue:
        waiting_queue.remove(uid)
        await state.clear()
        print(f"[DEBUG] Убрали {uid} из очереди")
        await message.answer(t(uid, "stopped_searching"))
    elif uid in active_chats:
        partner_id = active_chats.pop(uid)
        active_chats.pop(partner_id, None)
        await state.clear()
        print(f"[DEBUG] Чат завершён {uid} <-> {partner_id}")
        await message.answer(t(uid, "chat_ended"))
        try:
            await bot.send_message(partner_id, t(partner_id, "partner_left"))
        except:
            pass
    else:
        await message.answer(t(uid, "stopped_searching"))

@dp.message(Searching.chatting)
async def relay_message(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in active_chats:
        await state.clear()
        return
    partner_id = active_chats[uid]
    print(f"[DEBUG] Сообщение от {uid} → {partner_id}")

    partner_state = dp.fsm.storage.get_context(bot=bot, chat_id=partner_id, user_id=partner_id)
    await partner_state.set_state(Searching.chatting)

    try:
        if message.text:
            await bot.send_message(partner_id, message.text)
        elif message.sticker:
            await bot.send_sticker(partner_id, message.sticker.file_id)
        elif message.photo:
            await bot.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption)
        elif message.voice:
            await bot.send_voice(partner_id, message.voice.file_id)
    except Exception as e:
        print(f"[ERROR] Ошибка пересылки: {e}")

async def main():
    print("🚀 Бот запущен! Ждём пользователей...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
