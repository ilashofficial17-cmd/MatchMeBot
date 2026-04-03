"""
Admin Bot — точка входа.
Два экземпляра Bot:
  - main_bot  (BOT_TOKEN)          — для отправки юзерам (background tasks в будущем)
  - admin_bot (CHANNEL_BOT_TOKEN)  — для админ-интерфейса и канала
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from admin_bot.config import CHANNEL_BOT_TOKEN, BOT_TOKEN
from admin_bot.db import init_db
from admin_bot.channel.router import router as channel_router
from admin_bot.channel.scheduler import channel_poster

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("admin-bot")

# Два экземпляра Bot
admin_bot = Bot(token=CHANNEL_BOT_TOKEN)
main_bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(channel_router)


async def set_commands():
    await admin_bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="post", description="Создать пост"),
        BotCommand(command="toggle", description="ВКЛ/ВЫКЛ авто-постинг"),
        BotCommand(command="status", description="Статус API"),
        BotCommand(command="stats", description="Статистика канала"),
        BotCommand(command="schedule", description="Расписание постов"),
    ])


async def main():
    await init_db()
    await set_commands()
    asyncio.create_task(channel_poster())
    logger.info("MatchMe Admin Bot запущен!")
    await dp.start_polling(admin_bot)


if __name__ == "__main__":
    asyncio.run(main())
