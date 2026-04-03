"""
Admin Bot — reminder_task(): напоминания неактивным юзерам.
Перенесено из admin.py. Отправка через main_bot (BOT_TOKEN).
"""

import asyncio
import random
import logging
from datetime import datetime

from locales import t
from keyboards import kb_main

logger = logging.getLogger("admin-bot")

REMINDER_TEMPLATES = {
    "ru": [
        "🔥 Сейчас онлайн {n} человек — самое время для поиска!",
        "💬 Давно не заходил? У нас новые пользователи ждут общения!",
        "🤖 Попробуй AI собеседника — {char} ждёт тебя!",
        "👋 Давно тебя не было! В MatchMe сейчас {n} человек онлайн. Заходи пообщаться!",
        "💬 {char} скучает по тебе! Зайди продолжить разговор.",
    ],
    "en": [
        "🔥 {n} people are online now — perfect time to find someone!",
        "💬 Haven't been here in a while? New users are waiting!",
        "🤖 Try an AI companion — {char} is waiting for you!",
        "👋 We miss you! {n} people are online on MatchMe right now. Come chat!",
        "💬 {char} misses you! Come back to continue the conversation.",
    ],
    "es": [
        "🔥 ¡{n} personas en línea ahora — el momento perfecto para buscar!",
        "💬 ¿Hace tiempo que no vienes? ¡Nuevos usuarios te esperan!",
        "🤖 Prueba un compañero IA — ¡{char} te espera!",
        "👋 ¡Te extrañamos! Hay {n} personas en línea en MatchMe. ¡Ven a chatear!",
        "💬 ¡{char} te extraña! Vuelve a continuar la conversación.",
    ],
}


async def reminder_task(main_bot, db_pool):
    """Каждые 2 часа — напоминания неактивным юзерам."""
    try:
        from ai_characters import AI_CHARACTERS
    except ImportError:
        AI_CHARACTERS = {}

    while True:
        await asyncio.sleep(7200)
        try:
            from admin_bot.db import get_stat
            online_count = await get_stat("online_pairs", 0) + await get_stat("searching_count", 0)
            char_data = random.choice(list(AI_CHARACTERS.values())) if AI_CHARACTERS else {"name_key": "ai_char"}
            char_name = t("ru", char_data["name_key"])
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT uid, lang, ai_msg_basic, ai_msg_premium, premium_until, last_seen
                    FROM users
                    WHERE last_seen < NOW() - INTERVAL '24 hours'
                    AND (last_reminder IS NULL OR last_reminder < NOW() - INTERVAL '24 hours')
                    AND ban_until IS NULL
                    AND accepted_rules = TRUE
                    ORDER BY last_seen DESC
                    LIMIT 30
                """)
            sent = 0
            for row in rows:
                uid = row["uid"]
                try:
                    days_inactive = 0
                    if row["last_seen"]:
                        days_inactive = (datetime.now() - row["last_seen"]).days
                    is_prem = bool(row.get("premium_until"))
                    used_ai = (row.get("ai_msg_basic", 0) >= 15 or row.get("ai_msg_premium", 0) >= 8)
                    u_lang = row.get("lang") or "ru"
                    u_char_name = t(u_lang, char_data["name_key"])
                    if days_inactive >= 3 and used_ai and not is_prem:
                        await main_bot.send_message(uid, t(u_lang, "reminder_ai_bonus"), reply_markup=kb_main(u_lang))
                        async with db_pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE users SET ai_bonus = LEAST(ai_bonus + 5, 15), last_reminder = NOW() WHERE uid = $1", uid
                            )
                    else:
                        templates = REMINDER_TEMPLATES.get(u_lang, REMINDER_TEMPLATES["ru"])
                        template = random.choice(templates)
                        text = template.format(n=max(online_count, 3), char=u_char_name)
                        await main_bot.send_message(uid, text, reply_markup=kb_main(u_lang))
                        async with db_pool.acquire() as conn:
                            await conn.execute("UPDATE users SET last_reminder = NOW() WHERE uid = $1", uid)
                    sent += 1
                except Exception:
                    pass
            if sent:
                logger.info(f"Напоминания: отправлено {sent}")
        except Exception as e:
            logger.error(f"reminder_task error: {e}")
