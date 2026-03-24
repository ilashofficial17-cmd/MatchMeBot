import asyncio
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

users = {}
waiting = {
    "friend": [],
    "flirt": [],
    "kink": []
}
active_chats = {}
last_message_time = {}
message_count = {}  # анти-флуд
complaints = {}     # счётчик жалоб
bans = {}           # баны

# ====================== МЕНЮ ======================
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Search")],
            [KeyboardButton(text="⚙ Settings")]
        ],
        resize_keyboard=True
    )

def search_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Stop")]],
        resize_keyboard=True
    )

def chat_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Next")],
            [KeyboardButton(text="❌ Stop")],
            [KeyboardButton(text="🚩 Report")]
        ],
        resize_keyboard=True
    )

def settings_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👨 Male"), KeyboardButton(text="👩 Female")],
            [KeyboardButton(text="🎂 Age")],
            [KeyboardButton(text="🔥 Mode")],
            [KeyboardButton(text="🔙 Back")]
        ],
        resize_keyboard=True
    )

def mode_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🙂 Friend")],
            [KeyboardButton(text="😘 Flirt")],
            [KeyboardButton(text="⛓ Kink")]
        ],
        resize_keyboard=True
    )

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    uid = message.from_user.id
    if uid in bans and bans[uid] > datetime.now():
        await message.answer("🚫 Ты забанен.")
        return

    users[uid] = {
        "gender": "unknown",
        "search_gender": "any",
        "age": 0,
        "mode": "friend",
        "interests": []
    }
    await message.answer("Anonymous chat", reply_markup=main_menu())

# ====================== SETTINGS ======================
@dp.message(F.text == "⚙ Settings")
async def settings(message: Message):
    await message.answer("Settings", reply_markup=settings_menu())

@dp.message(F.text == "👨 Male")
async def set_male(message):
    users[message.from_user.id]["gender"] = "male"
    await message.answer("Gender saved")

@dp.message(F.text == "👩 Female")
async def set_female(message):
    users[message.from_user.id]["gender"] = "female"
    await message.answer("Gender saved")

@dp.message(F.text == "🔥 Mode")
async def mode(message):
    await message.answer("Select mode", reply_markup=mode_menu())

@dp.message(F.text.in_(["🙂 Friend", "😘 Flirt", "⛓ Kink"]))
async def set_mode(message):
    mode_map = {"🙂 Friend": "friend", "😘 Flirt": "flirt", "⛓ Kink": "kink"}
    users[message.from_user.id]["mode"] = mode_map[message.text]
    await message.answer("Mode set")

@dp.message(F.text == "🔙 Back")
async def back(message):
    await message.answer("Menu", reply_markup=main_menu())

# ====================== ПОИСК ======================
@dp.message(F.text == "🔍 Search")
@dp.message(Command("search"))
async def search(message: Message, state: FSMContext):
    uid = message.from_user.id
    if uid in active_chats:
        await message.answer("Already in chat")
        return

    await try_match(uid)

async def try_match(uid):
    mode = users[uid]["mode"]
    queue = waiting[mode]

    for other in queue[:]:
        if other == uid:
            continue
        queue.remove(other)
        connect(uid, other)
        await bot.send_message(uid, "Partner found", reply_markup=chat_menu())
        await bot.send_message(other, "Partner found", reply_markup=chat_menu())
        return True

    queue.append(uid)
    await bot.send_message(uid, "Searching...", reply_markup=search_menu())
    return False

def connect(a, b):
    active_chats[a] = b
    active_chats[b] = a
    last_message_time[a] = last_message_time[b] = datetime.now()

def disconnect(uid):
    if uid in active_chats:
        partner = active_chats.pop(uid)
        active_chats.pop(partner, None)
        return partner
    return None

# ====================== КНОПКИ В ЧАТЕ ======================
@dp.message(F.text == "🔄 Next")
async def next_chat(message: Message):
    uid = message.from_user.id
    partner = disconnect(uid)
    if partner:
        await bot.send_message(partner, "Partner left", reply_markup=main_menu())
    await try_match(uid)

@dp.message(F.text == "❌ Stop")
async def stop(message: Message):
    uid = message.from_user.id
    partner = disconnect(uid)
    if partner:
        await bot.send_message(partner, "Chat ended", reply_markup=main_menu())
    await message.answer("Stopped", reply_markup=main_menu())

@dp.message(F.text == "🚩 Report")
async def report(message: Message):
    uid = message.from_user.id
    if uid not in active_chats:
        await message.answer("You are not in chat")
        return
    partner = active_chats.pop(uid)
    active_chats.pop(partner, None)
    complaints[partner] = complaints.get(partner, 0) + 1
    await message.answer("Report sent. Chat ended.")
    try:
        await bot.send_message(partner, "Someone reported you. Chat ended.")
    except:
        pass
    if complaints.get(partner, 0) >= 3:
        bans[partner] = datetime.now() + timedelta(hours=24)
        await bot.send_message(partner, "You are banned for 24 hours.")

# ====================== ПЕРЕСЫЛКА ======================
@dp.message()
async def relay(message: Message):
    uid = message.from_user.id
    if uid in active_chats:
        partner = active_chats[uid]
        last_message_time[uid] = datetime.now()

        # Анти-флуд
        now = datetime.now()
        if uid not in message_count:
            message_count[uid] = []
        message_count[uid] = [t for t in message_count[uid] if (now - t).total_seconds() < 5]
        message_count[uid].append(now)
        if len(message_count[uid]) > 5:
            await message.answer("Don't spam!")
            return

        await bot.send_message(partner, message.text)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
