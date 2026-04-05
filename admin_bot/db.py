"""
Admin Bot — база данных: пул, хелперы, SQL миграции.
Перенесено из channel_bot.py + новые таблицы из спеки.
"""

import asyncpg
import logging

from admin_bot.config import DATABASE_URL

logger = logging.getLogger("admin-bot")

db_pool = None


async def init_db():
    """Создаёт пул и выполняет миграции."""
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        # Таблица bot_stats (из channel_bot.py)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Начальные значения
        for k, v in [("online_pairs", 0), ("searching_count", 0),
                      ("channel_poster_enabled", 1), ("last_milestone_threshold", 0)]:
            await conn.execute(
                "INSERT INTO bot_stats (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", k, v
            )

        # Таблица команд от админ-бота к основному боту
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_commands (
                id SERIAL PRIMARY KEY,
                command TEXT NOT NULL,
                target_uid BIGINT NOT NULL,
                params JSONB DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                executed_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_admin_commands_status
            ON admin_commands (status) WHERE status = 'pending'
        """)

        # Таблица ролей
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_roles (
                uid BIGINT PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'moderator',
                added_by BIGINT,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Таблица тикетов саппорта
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id SERIAL PRIMARY KEY,
                uid BIGINT NOT NULL,
                username TEXT,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                admin_reply TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                resolved_at TIMESTAMP
            )
        """)

        # Таблица стоп-слов (управление через админ-бота)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS stop_words (
                id SERIAL PRIMARY KEY,
                word TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Начальные стоп-слова (из moderation.py)
        _initial_hard = [
            "мне 12", "мне 13", "мне 14", "мне 15",
            "школьница ищу", "школьник ищу", "порно за деньги",
            "детское порно", "цп продаю", "малолетка",
        ]
        _initial_suspect = [
            "предлагаю услуги", "оказываю услуги", "интим услуги",
            "escort", "эскорт", "проститутка",
            "вирт за деньги", "вирт платно", "за донат",
            "подпишись на канал", "перейди по ссылке", "мой канал",
            "казино", "ставки на спорт", "заработок в телеграм",
            "крипта х10", "пассивный доход", "продаю фото", "продаю видео",
            "продаю интим", "купи подписку", "пиши в лс за", "скидка на услуги",
        ]
        for w in _initial_hard:
            await conn.execute(
                "INSERT INTO stop_words (word, type) VALUES ($1, 'hard_ban') ON CONFLICT (word) DO NOTHING", w
            )
        for w in _initial_suspect:
            await conn.execute(
                "INSERT INTO stop_words (word, type) VALUES ($1, 'suspect') ON CONFLICT (word) DO NOTHING", w
            )


async def get_stat(key, default=0):
    """Читает значение из bot_stats."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM bot_stats WHERE key=$1", key)
        return row["value"] if row else default


async def set_stat(key, value):
    """Записывает значение в bot_stats (upsert)."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bot_stats (key, value, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value=$2, updated_at=NOW()", key, value
        )


async def get_rubric_mode(rubric: str) -> str:
    """Возвращает режим рубрики: 'auto' или 'moderated'.
    Сначала проверяет bot_stats, потом дефолт из config."""
    from admin_bot.config import RUBRIC_MODE
    stat = await get_stat(f"rubric_mode:{rubric}", -1)
    if stat == -1:
        return RUBRIC_MODE.get(rubric, "auto")
    return "moderated" if stat else "auto"


async def set_rubric_mode(rubric: str, mode: str):
    """Сохраняет режим рубрики в bot_stats (0=auto, 1=moderated)."""
    await set_stat(f"rubric_mode:{rubric}", 1 if mode == "moderated" else 0)
