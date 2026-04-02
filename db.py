"""
MatchMe Bot — Data access layer.
All database helper functions extracted from bot.py.
"""
from datetime import datetime

# Injected at runtime by bot.py
_db_pool = None
_admin_id = None


def init(db_pool, admin_id):
    global _db_pool, _admin_id
    _db_pool = db_pool
    _admin_id = admin_id


async def get_user(uid):
    if not _db_pool:
        return None
    async with _db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
        return dict(row) if row else None


async def get_lang(uid) -> str:
    u = await get_user(uid)
    return (u.get("lang") or "ru") if u else "ru"


async def ensure_user(uid):
    if not _db_pool:
        return
    async with _db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", uid)
        if uid == _admin_id:
            await conn.execute(
                "UPDATE users SET premium_until='permanent' WHERE uid=$1 AND premium_until IS NULL", uid
            )


async def update_user(uid, **kwargs):
    if not kwargs or not _db_pool:
        return
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs))
    vals = list(kwargs.values())
    async with _db_pool.acquire() as conn:
        await conn.execute(f"UPDATE users SET {sets} WHERE uid=$1", uid, *vals)


async def increment_user(uid, **kwargs):
    """Атомарный инкремент полей: increment_user(uid, likes=1, total_chats=1)"""
    if not kwargs or not _db_pool:
        return
    sets = ", ".join(f"{k}={k}+${i+2}" for i, k in enumerate(kwargs))
    vals = list(kwargs.values())
    async with _db_pool.acquire() as conn:
        await conn.execute(f"UPDATE users SET {sets} WHERE uid=$1", uid, *vals)


async def get_ai_history(uid: int, character_id: str, limit: int = 20) -> list:
    if not _db_pool:
        return []
    async with _db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM ai_history "
            "WHERE uid=$1 AND character_id=$2 ORDER BY created_at DESC LIMIT $3",
            uid, character_id, limit
        )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def save_ai_message(uid: int, character_id: str, role: str, content: str):
    if not _db_pool:
        return
    async with _db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO ai_history (uid, character_id, role, content) VALUES ($1, $2, $3, $4)",
            uid, character_id, role, content
        )
        await conn.execute("""
            DELETE FROM ai_history WHERE id IN (
                SELECT id FROM ai_history WHERE uid=$1 AND character_id=$2
                ORDER BY created_at DESC OFFSET 20
            )
        """, uid, character_id)


async def clear_ai_history(uid: int, character_id: str = None):
    if not _db_pool:
        return
    async with _db_pool.acquire() as conn:
        if character_id:
            await conn.execute(
                "DELETE FROM ai_history WHERE uid=$1 AND character_id=$2", uid, character_id
            )
        else:
            await conn.execute("DELETE FROM ai_history WHERE uid=$1", uid)


async def get_ai_notes(uid: int, character_id: str) -> str:
    """Возвращает заметки о пользователе для персонажа."""
    if not _db_pool:
        return ""
    async with _db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT notes FROM ai_notes WHERE uid=$1 AND character_id=$2",
            uid, character_id
        )
    return (row["notes"] if row else "") or ""


async def save_ai_notes(uid: int, character_id: str, notes: str):
    """Сохраняет/обновляет заметки о пользователе для персонажа."""
    if not _db_pool:
        return
    async with _db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ai_notes (uid, character_id, notes, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (uid, character_id)
            DO UPDATE SET notes = $3, updated_at = NOW()
        """, uid, character_id, notes[:500])


async def get_premium_tier(uid):
    """Возвращает 'premium' или None"""
    if uid == _admin_id:
        return "premium"
    u = await get_user(uid)
    if not u:
        return None
    p_until = u.get("premium_until")
    if not p_until:
        return None
    if p_until == "permanent":
        return "premium"
    try:
        if datetime.now() < datetime.fromisoformat(p_until):
            return "premium"
        await update_user(uid, premium_until=None, premium_tier=None)
    except Exception:
        pass
    return None


async def is_premium(uid):
    return (await get_premium_tier(uid)) is not None


async def check_achievements(uid):
    """Проверяет и разблокирует новые ачивки. Возвращает список новых achievement_id."""
    from constants import ACHIEVEMENTS
    if not _db_pool:
        return []
    u = await get_user(uid)
    if not u:
        return []
    new_achievements = []
    async with _db_pool.acquire() as conn:
        existing = await conn.fetch(
            "SELECT achievement_id FROM achievements WHERE uid=$1", uid
        )
        existing_ids = {r["achievement_id"] for r in existing}
        for ach_id, ach in ACHIEVEMENTS.items():
            if ach_id in existing_ids:
                continue
            value = u.get(ach["field"], 0) or 0
            if value >= ach["threshold"]:
                await conn.execute(
                    "INSERT INTO achievements (uid, achievement_id, energy_claimed) "
                    "VALUES ($1, $2, TRUE) ON CONFLICT DO NOTHING",
                    uid, ach_id
                )
                # Начисляем энергию (уменьшаем ai_energy_used)
                energy_used = u.get("ai_energy_used", 0) or 0
                new_energy = max(energy_used - ach["energy"], 0)
                await conn.execute(
                    "UPDATE users SET ai_energy_used=$2 WHERE uid=$1",
                    uid, new_energy
                )
                # Обновляем локальную копию для корректного расчёта следующих ачивок
                u["ai_energy_used"] = new_energy
                new_achievements.append(ach_id)
    return new_achievements
