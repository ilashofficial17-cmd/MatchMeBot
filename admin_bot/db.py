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
