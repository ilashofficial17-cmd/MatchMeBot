"""
Admin Bot — streak_and_ai_push_task(): стрик-напоминания + AI miss-you.
Перенесено из admin.py. Отправка через main_bot (BOT_TOKEN).
"""

import asyncio
import logging
from datetime import datetime

from locales import t
from keyboards import kb_main

logger = logging.getLogger("admin-bot")


async def streak_and_ai_push_task(main_bot, db_pool):
    """Каждые 4 часа: стрик-напоминания + AI miss-you + очистка квестов."""
    try:
        from ai_characters import AI_CHARACTERS
    except ImportError:
        AI_CHARACTERS = {}

    while True:
        await asyncio.sleep(14400)
        try:
            async with db_pool.acquire() as conn:
                # 1. Стрик-напоминания
                streak_users = await conn.fetch("""
                    SELECT uid, lang, streak_days, streak_last_date
                    FROM users
                    WHERE streak_days >= 3
                    AND streak_last_date = CURRENT_DATE - 1
                    AND last_seen::date < CURRENT_DATE
                    AND ban_until IS NULL
                    AND (last_reminder IS NULL OR last_reminder < NOW() - INTERVAL '12 hours')
                    LIMIT 50
                """)
                sent_streak = 0
                for row in streak_users:
                    try:
                        u_lang = row.get("lang") or "ru"
                        await main_bot.send_message(
                            row["uid"],
                            t(u_lang, "streak_reminder", days=row["streak_days"]),
                            reply_markup=kb_main(u_lang)
                        )
                        await conn.execute("UPDATE users SET last_reminder = NOW() WHERE uid = $1", row["uid"])
                        sent_streak += 1
                    except Exception:
                        pass

                # 2. AI miss-you
                ai_users = await conn.fetch("""
                    SELECT uid, character_id, lang FROM (
                        SELECT h.uid, h.character_id, u.lang,
                               ROW_NUMBER() OVER (PARTITION BY h.uid ORDER BY COUNT(*) DESC) AS rn
                        FROM ai_history h
                        JOIN users u ON u.uid = h.uid
                        WHERE u.last_seen < NOW() - INTERVAL '48 hours'
                        AND u.last_seen > NOW() - INTERVAL '14 days'
                        AND u.ban_until IS NULL
                        AND (u.last_reminder IS NULL OR u.last_reminder < NOW() - INTERVAL '24 hours')
                        AND h.role = 'user'
                        GROUP BY h.uid, h.character_id, u.lang
                    ) sub WHERE rn = 1
                    LIMIT 30
                """)
                sent_ai = 0
                for row in ai_users:
                    try:
                        char = AI_CHARACTERS.get(row["character_id"])
                        if not char:
                            continue
                        u_lang = row.get("lang") or "ru"
                        char_name = t(u_lang, char["name_key"])
                        await main_bot.send_message(
                            row["uid"],
                            t(u_lang, "ai_miss_you", emoji=char["emoji"], name=char_name),
                            reply_markup=kb_main(u_lang)
                        )
                        await conn.execute("UPDATE users SET last_reminder = NOW() WHERE uid = $1", row["uid"])
                        sent_ai += 1
                    except Exception:
                        pass

            if sent_streak or sent_ai:
                logger.info(f"Push: streak={sent_streak}, ai_miss={sent_ai}")

            # Очистка старых квестов + сброс daily_bonus_claimed
            try:
                async with db_pool.acquire() as conn:
                    await conn.execute("DELETE FROM daily_quests WHERE quest_date < CURRENT_DATE - 7")
                    await conn.execute("UPDATE users SET daily_bonus_claimed = FALSE WHERE daily_bonus_claimed = TRUE")
            except Exception:
                pass

        except Exception as e:
            logger.error(f"streak_and_ai_push_task error: {e}")
