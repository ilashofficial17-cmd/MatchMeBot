"""
Funnel Bot 2 — Chat Funnel, статическая продающая страница.
Показывает преимущества + живой онлайн из БД. Кнопка в @MyMatchMeBot.
"""

import os
import asyncio
import logging

import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("chat-funnel-bot")

TOKEN = os.environ["FUNNEL_CHAT_TOKEN_RU"]
DATABASE_URL = os.environ["DATABASE_URL"]

KB_MAIN_BOT = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🚀 Начать общение", url="https://t.me/MyMatchMeBot")]
])

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def get_online_count() -> int:
    """Получить количество людей онлайн из bot_stats."""
    try:
        conn = await asyncpg.connect(DATABASE_URL, timeout=10)
        try:
            pairs = await conn.fetchval(
                "SELECT value FROM bot_stats WHERE key='online_pairs'"
            ) or 0
            searching = await conn.fetchval(
                "SELECT value FROM bot_stats WHERE key='searching_count'"
            ) or 0
            return pairs * 2 + searching
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"DB error: {e}")
        return 0


def build_landing(online: int) -> str:
    online_text = f"🔥 {online} человек онлайн прямо сейчас\n\n" if online > 0 else ""
    return (
        f"🎭 Анонимный чат — общайся без масок\n\n"
        f"{online_text}"
        f"Что тебя ждёт:\n"
        f"💬 Случайный собеседник за секунды\n"
        f"🎭 Полная анонимность\n"
        f"💋 3 режима: общение, флирт, kink\n"
        f"🤖 15+ AI-персонажей для практики\n"
        f"⚡ Бесплатно, без регистрации\n\n"
        f"Готов попробовать? 👇"
    )


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    online = await get_online_count()
    await message.answer(build_landing(online), reply_markup=KB_MAIN_BOT)


@dp.message(F.text)
async def handle_any(message: types.Message):
    online = await get_online_count()
    await message.answer(build_landing(online), reply_markup=KB_MAIN_BOT)


async def main():
    logger.info("Chat Funnel Bot запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
