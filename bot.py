import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher(storage=MemoryStorage())

users = {}

waiting_queue_simple = []
waiting_queue_flirt = []
waiting_queue_kink = []

active_chats = {}

last_message_time = {}

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

"welcome":"👋 Привет! Добро пожаловать в MatchMe",

"enter_name":"Как тебя зовут?",

"enter_age":"Сколько тебе лет?",

"choose_gender":"Выбери пол:",

"choose_mode":"Выбери режим:",

"choose_interests":"Выбери интересы:",

"profile_saved":"✅ Анкета сохранена",

"found":"✅ Собеседник найден",

"complain_sent":"Жалоба отправлена",

"male":"👨 Парень",

"female":"👩 Девушка",

"age_error":"16-99",

}

}


def get_main_menu():

    return ReplyKeyboardMarkup(

keyboard=[

[KeyboardButton(text="🔍 Найти собеседника")],

[KeyboardButton(text="👤 Мой профиль")],

[KeyboardButton(text="🔄 Перезапустить")],

[KeyboardButton(text="❓ Помощь")]

],

resize_keyboard=True

)


def get_chat_menu():

    return ReplyKeyboardMarkup(

keyboard=[

[KeyboardButton(text="🔄 Следующий собеседник")],

[KeyboardButton(text="❌ Завершить чат")],

[KeyboardButton(text="🚩 Пожаловаться")]

],

resize_keyboard=True

)


def get_cancel_search_menu():

    return ReplyKeyboardMarkup(

keyboard=[[KeyboardButton(text="❌ Отменить поиск")]],

resize_keyboard=True

)


async def set_commands():

    commands=[

BotCommand(command="find",description="Найти"),

BotCommand(command="next",description="Следующий"),

BotCommand(command="stop",description="Стоп"),

BotCommand(command="profile",description="Профиль")

]

    await bot.set_my_commands(commands)


@dp.message(Command("start"))
async def cmd_start(message:types.Message,state:FSMContext):

    await state.clear()

    kb=ReplyKeyboardMarkup(

keyboard=[[KeyboardButton(text="🇷🇺 Русский")]],

resize_keyboard=True

)

    await message.answer("Выбери язык",reply_markup=kb)

    await state.set_state(Registration.language)


@dp.message(Registration.language)
async def choose_language(message:types.Message,state:FSMContext):

    users[message.from_user.id]={"lang":"ru"}

    await message.answer("Имя?",reply_markup=ReplyKeyboardRemove())

    await state.set_state(Registration.name)


@dp.message(Registration.name)
async def enter_name(message:types.Message,state:FSMContext):

    await state.update_data(name=message.text)

    await message.answer("Возраст?")

    await state.set_state(Registration.age)


@dp.message(Registration.age)
async def enter_age(message:types.Message,state:FSMContext):

    if not message.text.isdigit():

        await message.answer("Число")

        return

    age=int(message.text)

    if age<16 or age>99:

        await message.answer("16-99")

        return

    await state.update_data(age=age)

    kb=ReplyKeyboardMarkup(

keyboard=[

[KeyboardButton(text="👨 Парень"),

KeyboardButton(text="👩 Девушка")]

],

resize_keyboard=True

)

    await message.answer("Пол:",reply_markup=kb)

    await state.set_state(Registration.gender)


@dp.message(Registration.gender)
async def enter_gender(message:types.Message,state:FSMContext):

    data=await state.get_data()

    uid=message.from_user.id

    gender="male" if "Парень" in message.text else "female"

    users[uid].update({

"name":data["name"],

"age":data["age"],

"gender":gender

})

    kb=ReplyKeyboardMarkup(

keyboard=[

[KeyboardButton(text="1️⃣ Просто общение")],

[KeyboardButton(text="2️⃣ Флирт")],

[KeyboardButton(text="3️⃣ Kink")]

],

resize_keyboard=True

)

    await message.answer("Режим:",reply_markup=kb)

    await state.set_state(Registration.mode)


@dp.message(Registration.mode)
async def choose_mode(message:types.Message,state:FSMContext):

    uid=message.from_user.id

    text=message.text

    if "1" in text:

        mode="simple"

        interests=["Разговор","Юмор","Советы"]

    elif "2" in text:

        mode="flirt"

        interests=["Флирт","Комплименты","Секстинг"]

    else:

        mode="kink"

        interests=["BDSM","Roleplay","Dom/Sub"]

    users[uid]["mode"]=mode

    users[uid]["temp_interests"]=[]

    kb=InlineKeyboardMarkup(

inline_keyboard=[

[InlineKeyboardButton(

text=i,

callback_data=f"interest:{i}"

)]

for i in interests

]

)

    kb.inline_keyboard.append(

[InlineKeyboardButton(

text="✅ Готово",

callback_data="done"

)]

)

    await message.answer("Интересы:",reply_markup=kb)

    await state.set_state(Registration.interests)


@dp.callback_query(F.data.startswith("interest:"))
async def add_interest(callback:types.CallbackQuery):

    uid=callback.from_user.id

    interest=callback.data.split(":")[1]

    if interest not in users[uid]["temp_interests"]:

        users[uid]["temp_interests"].append(interest)

    await callback.answer("Добавлено")


@dp.callback_query(F.data=="done")
async def finish(callback:types.CallbackQuery,state:FSMContext):

    uid=callback.from_user.id

    users[uid]["interests"]=users[uid]["temp_interests"]

    users[uid].pop("temp_interests")

    await state.clear()

    await callback.message.answer(

"Профиль готов",

reply_markup=get_main_menu()

)


@dp.message(F.text.contains("Найти"))
@dp.message(Command("find"))
async def cmd_find(message:types.Message,state:FSMContext):

    uid=message.from_user.id

    if uid in active_chats:

        return

    mode=users[uid]["mode"]

    if mode=="simple":

        queue=waiting_queue_simple

    elif mode=="flirt":

        queue=waiting_queue_flirt

    else:

        queue=waiting_queue_kink

    async with pairing_lock:

        partner=None

        for i in queue:

            if i!=uid:

                partner=i

                queue.remove(i)

                break

        if partner:

            active_chats[uid]=partner

            active_chats[partner]=uid

            await state.set_state(Searching.chatting)

            key=StorageKey(

bot_id=bot.id,

chat_id=partner,

user_id=partner

)

            await FSMContext(

dp.storage,

key=key

).set_state(

Searching.chatting

)

            await bot.send_message(

uid,

"Найден",

reply_markup=get_chat_menu()

)

            await bot.send_message(

partner,

"Найден",

reply_markup=get_chat_menu()

)

        else:

            if uid not in queue:

                queue.append(uid)

            await state.set_state(Searching.waiting)

            await message.answer(

"Ищем",

reply_markup=get_cancel_search_menu()

)


@dp.message(Searching.chatting)
async def relay(message:types.Message):

    uid=message.from_user.id

    if uid not in active_chats:

        return

    partner=active_chats.get(uid)

    last_message_time[uid]=datetime.now()

    try:

        await bot.send_message(

partner,

message.text

)

    except:

        pass


@dp.message(F.text.contains("Следующий"))
@dp.message(Command("next"))
async def next_partner(message:types.Message,state:FSMContext):

    uid=message.from_user.id

    if uid in active_chats:

        partner=active_chats.pop(uid)

        active_chats.pop(partner,None)

        try:

            await bot.send_message(

partner,

"Собеседник вышел",

reply_markup=get_main_menu()

)

        except:

            pass

    await state.clear()

    await cmd_find(message,state)


@dp.message(F.text.contains("Завершить"))
@dp.message(Command("stop"))
async def stop_chat(message:types.Message,state:FSMContext):

    uid=message.from_user.id

    if uid in active_chats:

        partner=active_chats.pop(uid)

        active_chats.pop(partner,None)

        await message.answer(

"Чат закрыт",

reply_markup=get_main_menu()

)

        try:

            await bot.send_message(

partner,

"Чат закрыт",

reply_markup=get_main_menu()

)

        except:

            pass

    await state.clear()


@dp.message(F.text=="🚩 Пожаловаться")
async def complain(message:types.Message,state:FSMContext):

    uid=message.from_user.id

    if uid in active_chats:

        partner=active_chats.pop(uid)

        active_chats.pop(partner,None)

        await message.answer(

"Жалоба отправлена",

reply_markup=get_main_menu()

)


@dp.message(F.text=="❌ Отменить поиск")
async def cancel_search(message:types.Message,state:FSMContext):

    uid=message.from_user.id

    for q in [

waiting_queue_simple,

waiting_queue_flirt,

waiting_queue_kink

]:

        if uid in q:

            q.remove(uid)

    await state.clear()

    await message.answer(

"Поиск отменён",

reply_markup=get_main_menu()

)


@dp.message(Command("profile"))
async def profile(message:types.Message):

    uid=message.from_user.id

    u=users.get(uid)

    if not u:

        return

    await message.answer(

f"{u['name']} {u['age']}"

)


async def main():

    await set_commands()

    await dp.start_polling(bot)


if __name__=="__main__":

    asyncio.run(main())
