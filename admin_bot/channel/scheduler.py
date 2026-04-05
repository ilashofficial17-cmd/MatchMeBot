"""
Admin Bot — цикл авто-постинга в канал.
Перенесено из channel_bot.py: channel_poster().
Поддержка двух режимов: auto (сразу в канал) и moderated (превью админу).
"""

import asyncio
import logging
from datetime import datetime
from io import BytesIO

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import (
    CHANNEL_ID, CHANNEL_SCHEDULE, MILESTONE_THRESHOLDS, ADMIN_ID,
)
import admin_bot.db as _db
from admin_bot.db import get_stat, set_stat, get_rubric_mode
from admin_bot.channel.content import (
    CHANNEL_GENERATORS, generate_poll, generate_milestone,
    generate_image, last_milestone_threshold,
)
import admin_bot.channel.content as content_module

logger = logging.getLogger("admin-bot")

# Время последнего поста по рубрике (in-memory)
last_channel_post = {}

# Pending posts на модерации: post_id -> {...}
pending_posts = {}
_next_post_id = 1

# Эмодзи рубрик для UI
RUBRIC_EMOJI = {
    "daily_stats": "📊", "chat_story": "💬", "would_you": "🤔",
    "dating_tip": "💡", "joke": "😂", "poll": "📋",
    "weekly_recap": "📈", "hot_take": "🔥", "night_vibe": "🌙",
    "milestone": "🎯",
}

MAX_REGEN_ATTEMPTS = 3


def _moderation_kb(post_id: int) -> InlineKeyboardMarkup:
    """Inline-клавиатура для preview модерируемого поста."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"chmod:approve:{post_id}"),
            InlineKeyboardButton(text="🔄 Другой", callback_data=f"chmod:regen:{post_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"chmod:edit:{post_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"chmod:dismiss:{post_id}"),
        ],
    ])


async def create_pending_post(rubric: str, text: str, poll_data=None):
    """Создаёт pending post и отправляет preview админу."""
    global _next_post_id
    from admin_bot.main import admin_bot

    post_id = _next_post_id
    _next_post_id += 1

    emoji = RUBRIC_EMOJI.get(rubric, "📝")
    now = datetime.now()
    time_str = now.strftime("%H:%M")

    preview_text = (
        f"📋 Пост на модерации\n\n"
        f"Рубрика: {emoji} {rubric}\n"
        f"Время: {time_str}\n\n"
        f"{'─' * 20}\n"
        f"{text}\n"
        f"{'─' * 20}"
    )

    preview_msg = await admin_bot.send_message(
        ADMIN_ID,
        preview_text,
        reply_markup=_moderation_kb(post_id),
    )

    pending_posts[post_id] = {
        "rubric": rubric,
        "text": text,
        "poll_data": poll_data,
        "preview_msg_id": preview_msg.message_id,
        "created_at": now,
        "attempts": 1,
    }
    logger.info(f"Pending post #{post_id} [{rubric}] sent to admin for moderation")


async def _cleanup_expired():
    """Удаляет pending posts старше 2 часов (auto-dismiss)."""
    from admin_bot.main import admin_bot

    now = datetime.now()
    expired = [
        pid for pid, post in pending_posts.items()
        if (now - post["created_at"]).total_seconds() > 7200
    ]
    for pid in expired:
        post = pending_posts.pop(pid)
        try:
            await admin_bot.edit_message_text(
                chat_id=ADMIN_ID,
                message_id=post["preview_msg_id"],
                text=f"⏰ Пост [{post['rubric']}] отклонён по таймауту (2ч)",
            )
        except Exception:
            pass
        logger.info(f"Pending post #{pid} [{post['rubric']}] auto-dismissed (timeout)")


async def channel_poster():
    """Основной цикл авто-постинга — проверяет расписание каждые 10 минут."""
    from admin_bot.main import admin_bot

    await asyncio.sleep(30)

    # Восстанавливаем milestone из БД
    try:
        content_module.last_milestone_threshold = await get_stat("last_milestone_threshold", 0)
        if content_module.last_milestone_threshold == 0:
            async with _db.db_pool.acquire() as conn:
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

        # Cleanup expired pending posts
        await _cleanup_expired()

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

            # Skip if this rubric already has a pending post
            if any(p["rubric"] == rubric for p in pending_posts.values()):
                continue

            mode = await get_rubric_mode(rubric)

            try:
                if rubric == "poll":
                    poll_data = await generate_poll()
                    question, options = poll_data
                    if mode == "moderated":
                        text = f"📋 Опрос: {question}\n" + "\n".join(f"  • {o}" for o in options)
                        await create_pending_post(rubric, text, poll_data)
                        last_channel_post[rubric] = now
                    else:
                        await admin_bot.send_poll(
                            CHANNEL_ID, question=question,
                            options=options, is_anonymous=True,
                        )
                        last_channel_post[rubric] = now
                        logger.info(f"Channel poll posted: {question}")

                elif rubric in CHANNEL_GENERATORS:
                    text = await CHANNEL_GENERATORS[rubric]()
                    if not text:
                        continue

                    if mode == "moderated":
                        await create_pending_post(rubric, text)
                        last_channel_post[rubric] = now
                    else:
                        # Auto mode — сразу в канал
                        image_bytes = await generate_image(rubric, text)
                        if image_bytes:
                            from aiogram.types import BufferedInputFile
                            photo = BufferedInputFile(image_bytes, filename=f"{rubric}.png")
                            await admin_bot.send_photo(CHANNEL_ID, photo=photo, caption=text)
                            logger.info(f"Channel post [{rubric}] sent with image")
                        else:
                            await admin_bot.send_message(CHANNEL_ID, text)
                            logger.info(f"Channel post [{rubric}] sent")
                        last_channel_post[rubric] = now

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
