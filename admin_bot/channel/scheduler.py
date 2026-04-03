"""
Admin Bot — цикл авто-постинга в канал.
Перенесено из channel_bot.py: channel_poster().
"""

import asyncio
import logging
from datetime import datetime

from admin_bot.config import CHANNEL_ID, CHANNEL_SCHEDULE, MILESTONE_THRESHOLDS
from admin_bot.db import db_pool, get_stat, set_stat
from admin_bot.channel.content import (
    CHANNEL_GENERATORS, generate_poll, generate_milestone,
    last_milestone_threshold,
)
import admin_bot.channel.content as content_module

logger = logging.getLogger("admin-bot")

# Время последнего поста по рубрике (in-memory)
last_channel_post = {}


async def channel_poster():
    """Основной цикл авто-постинга — проверяет расписание каждые 10 минут."""
    from admin_bot.main import admin_bot

    await asyncio.sleep(30)

    # Восстанавливаем milestone из БД
    try:
        content_module.last_milestone_threshold = await get_stat("last_milestone_threshold", 0)
        if content_module.last_milestone_threshold == 0:
            async with db_pool.acquire() as conn:
                total = await conn.fetchval("SELECT COUNT(*) FROM users")
            for t in MILESTONE_THRESHOLDS:
                if total >= t:
                    content_module.last_milestone_threshold = t
            await set_stat("last_milestone_threshold", content_module.last_milestone_threshold)
    except Exception:
        pass

    logger.info("Channel poster запущен")

    while True:
        await asyncio.sleep(600)

        enabled = await get_stat("channel_poster_enabled", 1)
        if not enabled:
            continue

        now = datetime.now()
        hour = now.hour

        rubrics = CHANNEL_SCHEDULE.get(hour, [])
        for rubric in rubrics:
            last = last_channel_post.get(rubric)
            if last and (now - last).total_seconds() < 3600:
                continue
            if rubric == "poll" and now.day % 2 != 0:
                continue
            if rubric == "weekly_recap" and now.weekday() != 6:
                continue
            try:
                if rubric == "poll":
                    question, options = await generate_poll()
                    await admin_bot.send_poll(CHANNEL_ID, question=question, options=options, is_anonymous=True)
                    last_channel_post[rubric] = now
                    logger.info(f"Channel poll posted: {question}")
                elif rubric in CHANNEL_GENERATORS:
                    text = await CHANNEL_GENERATORS[rubric]()
                    if text:
                        await admin_bot.send_message(CHANNEL_ID, text)
                        last_channel_post[rubric] = now
                        logger.info(f"Channel post [{rubric}] sent")
            except Exception as e:
                logger.error(f"Channel poster error [{rubric}]: {e}")

        # Milestone
        try:
            milestone_text = await generate_milestone()
            if milestone_text:
                await admin_bot.send_message(CHANNEL_ID, milestone_text)
                logger.info("Channel milestone posted")
        except Exception as e:
            logger.error(f"Channel milestone error: {e}")
