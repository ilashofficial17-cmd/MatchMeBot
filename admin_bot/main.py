"""
Admin Bot — точка входа.
Два экземпляра Bot:
  - main_bot  (BOT_TOKEN)          — для отправки юзерам (background tasks)
  - admin_bot (CHANNEL_BOT_TOKEN)  — для админ-интерфейса и канала
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from admin_bot.config import CHANNEL_BOT_TOKEN, BOT_TOKEN
from admin_bot.db import init_db
import admin_bot.db as _db

# Routers
from admin_bot.channel.router import router as channel_router
from admin_bot.admin.router import router as admin_router
from admin_bot.admin.users import router as users_router
from admin_bot.admin.media import router as media_router
from admin_bot.admin.marketing import router as marketing_router
from admin_bot.admin.stopwords import router as stopwords_router
from admin_bot.admin.broadcast import router as broadcast_router
from admin_bot.moderation.router import router as moderation_router
from admin_bot.moderation.audit import router as audit_router
from admin_bot.support.router import router as support_router

# Tasks
from admin_bot.channel.scheduler import channel_poster
from admin_bot.tasks.reminders import reminder_task
from admin_bot.tasks.winback import winback_task
from admin_bot.tasks.streaks import streak_and_ai_push_task

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("admin-bot")

# Два экземпляра Bot
admin_bot = Bot(token=CHANNEL_BOT_TOKEN)
main_bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

dp = Dispatcher(storage=MemoryStorage())

# Порядок важен: admin_router ловит /admin и admin:* callbacks,
# support/moderation/media/users/marketing — свои callback prefixes,
# channel_router — /start, /post, /toggle и reply-кнопки (должен быть последним)
dp.include_router(admin_router)
dp.include_router(users_router)
dp.include_router(media_router)
dp.include_router(marketing_router)
dp.include_router(stopwords_router)
dp.include_router(broadcast_router)
dp.include_router(moderation_router)
dp.include_router(audit_router)
dp.include_router(support_router)
dp.include_router(channel_router)


# Handle AdminState.waiting_support_reply
from aiogram.filters import StateFilter
from admin_bot.admin.router import AdminState


@dp.message(StateFilter(AdminState.waiting_support_reply))
async def admin_support_reply_handler(message, state):
    from admin_bot.support.router import handle_support_reply
    await handle_support_reply(message, state)


async def set_commands():
    await admin_bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="admin", description="Админ-панель"),
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
    if main_bot and _db.db_pool:
        asyncio.create_task(reminder_task(main_bot, _db.db_pool))
        asyncio.create_task(winback_task(main_bot, _db.db_pool))
        asyncio.create_task(streak_and_ai_push_task(main_bot, _db.db_pool))
    logger.info("MatchMe Admin Bot запущен! (channel + admin + moderation + support + tasks)")
    await dp.start_polling(admin_bot)


if __name__ == "__main__":
    asyncio.run(main())
