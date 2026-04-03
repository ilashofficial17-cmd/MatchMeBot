"""
Admin Bot — генераторы контента для канала.
Перенесено из channel_bot.py: ask_claude_channel + все generate_* функции.
"""

import random
import logging
import aiohttp

from admin_bot.config import (
    ANTHROPIC_API_KEY, CHANNEL_STYLE_PROMPT, BOT_USERNAME,
    MODE_NAMES, MILESTONE_THRESHOLDS, POLL_BANK, ADMIN_ID,
)
from admin_bot.db import db_pool, get_stat, set_stat

logger = logging.getLogger("admin-bot")

# Состояние milestone (восстанавливается из БД в scheduler)
last_milestone_threshold = 0


async def ask_claude_channel(system_prompt: str, user_prompt: str) -> str:
    """Отправляет запрос к Claude API для генерации контента канала."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 300,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("content", [])
                    if content and len(content) > 0:
                        return content[0].get("text")
                    return None
                else:
                    logger.warning(f"Claude API error: status={resp.status}")
                    if resp.status in (401, 402, 429):
                        try:
                            from admin_bot.main import admin_bot
                            await admin_bot.send_message(
                                ADMIN_ID,
                                f"⚠️ Claude API ошибка {resp.status}!\n"
                                f"{'Нет денег на балансе' if resp.status == 402 else 'Проблема с ключом' if resp.status == 401 else 'Превышен лимит запросов'}\n"
                                f"AI-контент канала временно недоступен."
                            )
                        except Exception:
                            pass
    except Exception as e:
        logger.error(f"Claude API error: {e}")
    return None


async def generate_daily_stats():
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '24 hours'")
            active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            genders = await conn.fetch("SELECT gender, COUNT(*) as cnt FROM users WHERE gender IS NOT NULL GROUP BY gender")
            modes = await conn.fetch("SELECT mode, COUNT(*) as cnt FROM users WHERE mode IS NOT NULL GROUP BY mode ORDER BY cnt DESC")
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
        g_map = {"male": "парней", "female": "девушек", "other": "other"}
        g_parts = [f"{r['cnt']} {g_map.get(r['gender'], r['gender'])}" for r in genders]
        m_parts = [f"{MODE_NAMES.get(r['mode'], r['mode'])}: {r['cnt']}" for r in modes]
        online = await get_stat("online_pairs", 0)
        searching = await get_stat("searching_count", 0)
        raw_data = (
            f"Всего юзеров: {total}, новых за 24ч: {new_today}, активных: {active}, "
            f"сейчас в чатах: {online} пар, ищут: {searching}, premium: {premiums}, "
            f"пол: {', '.join(g_parts)}, режимы: {', '.join(m_parts)}"
        )
        styled = await ask_claude_channel(
            CHANNEL_STYLE_PROMPT,
            f"Напиши короткий пост со статистикой MatchMe за день. "
            f"Данные: {raw_data}. "
            f"Выдели 2-3 самых интересных факта. Максимум 400 символов."
        )
        if styled:
            return styled
        return (
            f"Нас уже {total} 👥\n"
            f"+{new_today} новых за сегодня, {active} активных\n"
            f"Прямо сейчас: {online} пар в чатах, {searching} ищут\n\n"
            f"@{BOT_USERNAME}"
        )
    except Exception as e:
        logger.error(f"generate_daily_stats error: {e}")
        return None


async def generate_peak_hour():
    online = await get_stat("online_pairs", 0)
    searching = await get_stat("searching_count", 0)
    if online + searching < 1:
        return None
    styled = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        f"Сейчас в MatchMe {online} пар общаются, {searching} ищут собеседника. "
        f"Напиши 2-3 строки — зацепи, чтобы захотелось зайти. Максимум 200 символов."
    )
    if styled:
        return styled
    return (
        f"{online} пар сейчас болтают, {searching} ждут собеседника\n"
        f"Самое время зайти 👉 @{BOT_USERNAME}"
    )


async def generate_dating_tip():
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        "Один короткий совет про общение в анонимных чатах. "
        "Конкретный, полезный, без воды. Максимум 3 строки текста + пример. Максимум 350 символов."
    )
    if text:
        return text
    tips = [
        f"Не начинай с «привет, как дела». Задай вопрос, на который интересно ответить.\n\n@{BOT_USERNAME}",
        f"Первое впечатление — это первые 3 сообщения. Не трать их на «м/ж?»\n\n@{BOT_USERNAME}",
        f"Юмор работает лучше комплиментов. Рассмеши — и разговор пойдёт сам.\n\n@{BOT_USERNAME}",
    ]
    return random.choice(tips)


async def generate_joke():
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        "Короткая шутка или ироничное наблюдение про онлайн-знакомства и анонимные чаты. "
        "Формат: 1-3 строки, как пост друга в соцсети. Без натужного юмора. Максимум 250 символов."
    )
    if text:
        return text
    jokes = [
        f"Анонимный чат — единственное место, где «расскажи о себе» звучит как квест 🎮\n\n@{BOT_USERNAME}",
        f"Когда написал «привет» и ждёшь ответ как результат экзамена 😅\n\n@{BOT_USERNAME}",
        f"В анонимном чате каждый разговор — как первое свидание. Только без кофе ☕\n\n@{BOT_USERNAME}",
    ]
    return random.choice(jokes)


async def generate_poll():
    return random.choice(POLL_BANK)


async def generate_milestone():
    global last_milestone_threshold
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
        current = 0
        for t in MILESTONE_THRESHOLDS:
            if total >= t:
                current = t
        if current > last_milestone_threshold and last_milestone_threshold > 0:
            last_milestone_threshold = current
            await set_stat("last_milestone_threshold", current)
            styled = await ask_claude_channel(
                CHANNEL_STYLE_PROMPT,
                f"MatchMe достиг {current} пользователей (сейчас {total}). "
                f"Напиши короткий искренний пост-благодарность. 2-3 строки, без пафоса. Максимум 250 символов."
            )
            if styled:
                return styled
            return (
                f"Нас уже {current}+ ❤️\n"
                f"Спасибо, что вы с нами\n\n"
                f"@{BOT_USERNAME}"
            )
        last_milestone_threshold = current
    except Exception as e:
        logger.error(f"generate_milestone error: {e}")
    return None


async def generate_weekly_recap():
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'")
            active_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '7 days'")
            ages = await conn.fetch("""
                SELECT CASE WHEN age BETWEEN 16 AND 19 THEN '16-19'
                            WHEN age BETWEEN 20 AND 25 THEN '20-25'
                            WHEN age BETWEEN 26 AND 35 THEN '26-35'
                            ELSE '36+' END as bracket, COUNT(*) as cnt
                FROM users WHERE age IS NOT NULL GROUP BY bracket ORDER BY bracket
            """)
            top_mode = await conn.fetchrow("SELECT mode, COUNT(*) as cnt FROM users WHERE mode IS NOT NULL GROUP BY mode ORDER BY cnt DESC LIMIT 1")
        age_parts = [f"{r['bracket']}: {r['cnt']}" for r in ages]
        mode_text = MODE_NAMES.get(top_mode['mode'], '?') if top_mode else "—"
        raw_data = (
            f"Всего: {total}, новых за неделю: {new_week}, активных за неделю: {active_week}, "
            f"топ режим: {mode_text}, возрасты: {', '.join(age_parts)}"
        )
        styled = await ask_claude_channel(
            CHANNEL_STYLE_PROMPT,
            f"Итоги недели MatchMe. Данные: {raw_data}. "
            f"Выдели 2-3 ключевых момента, добавь короткий вывод. Максимум 400 символов."
        )
        if styled:
            return styled
        return (
            f"Итоги недели\n\n"
            f"Всего: {total}, новых: +{new_week}\n"
            f"Активных: {active_week}, топ режим: {mode_text}\n\n"
            f"@{BOT_USERNAME}"
        )
    except Exception as e:
        logger.error(f"generate_weekly_recap error: {e}")
        return None


CHANNEL_GENERATORS = {
    "daily_stats": generate_daily_stats,
    "peak_hour": generate_peak_hour,
    "dating_tip": generate_dating_tip,
    "joke": generate_joke,
    "weekly_recap": generate_weekly_recap,
}
