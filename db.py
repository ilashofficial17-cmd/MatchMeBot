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


async def generate_daily_quests(uid):
    """Генерирует 3 квеста на сегодня (если ещё не созданы). Возвращает список квестов."""
    import hashlib
    from constants import QUEST_POOL
    if not _db_pool:
        return []
    today = datetime.now().date()
    async with _db_pool.acquire() as conn:
        existing = await conn.fetch(
            "SELECT quest_id, progress, goal, reward, claimed FROM daily_quests "
            "WHERE uid=$1 AND quest_date=$2", uid, today
        )
        if existing:
            return [dict(r) for r in existing]
        # Детерминистичный выбор 3 квестов на основе uid + date
        seed = hashlib.md5(f"{uid}:{today}".encode()).hexdigest()
        seed_int = int(seed[:8], 16)
        indices = []
        pool = list(range(len(QUEST_POOL)))
        for i in range(min(3, len(pool))):
            idx = seed_int % len(pool)
            indices.append(pool.pop(idx))
            seed_int = seed_int // (len(pool) + 1) + i + 1
        quests = [QUEST_POOL[i] for i in sorted(indices)]
        for q in quests:
            await conn.execute(
                "INSERT INTO daily_quests (uid, quest_date, quest_id, progress, goal, reward) "
                "VALUES ($1, $2, $3, 0, $4, $5) ON CONFLICT DO NOTHING",
                uid, today, q["id"], q["goal"], q["reward"]
            )
        return [{"quest_id": q["id"], "progress": 0, "goal": q["goal"],
                 "reward": q["reward"], "claimed": False} for q in quests]


async def increment_quest(uid, quest_type):
    """Инкрементирует прогресс квестов заданного типа. Авто-claim при достижении goal.
    Возвращает список claimed quest_id."""
    from constants import QUEST_POOL, QUEST_ALL_DONE_BONUS
    if not _db_pool:
        return []
    today = datetime.now().date()
    # Определяем quest_id по типу
    type_to_ids = {q["type"]: q["id"] for q in QUEST_POOL}
    target_id = type_to_ids.get(quest_type)
    if not target_id:
        return []
    claimed_ids = []
    async with _db_pool.acquire() as conn:
        # Инкремент прогресса
        row = await conn.fetchrow(
            "UPDATE daily_quests SET progress = LEAST(progress + 1, goal) "
            "WHERE uid=$1 AND quest_date=$2 AND quest_id=$3 AND claimed=FALSE "
            "RETURNING progress, goal, reward, quest_id",
            uid, today, target_id
        )
        if row and row["progress"] >= row["goal"]:
            # Авто-claim
            await conn.execute(
                "UPDATE daily_quests SET claimed=TRUE "
                "WHERE uid=$1 AND quest_date=$2 AND quest_id=$3",
                uid, today, target_id
            )
            # Начисляем энергию
            await conn.execute(
                "UPDATE users SET ai_energy_used = GREATEST(ai_energy_used - $2, 0) WHERE uid=$1",
                uid, row["reward"]
            )
            claimed_ids.append(row["quest_id"])
            # Проверяем: все 3 квеста выполнены? Бонус
            all_quests = await conn.fetch(
                "SELECT claimed FROM daily_quests WHERE uid=$1 AND quest_date=$2",
                uid, today
            )
            all_done = all(r["claimed"] for r in all_quests) and len(all_quests) >= 3
            if all_done:
                # Проверяем что daily_bonus ещё не начислен
                u = await conn.fetchrow("SELECT daily_bonus_claimed FROM users WHERE uid=$1", uid)
                if u and not u["daily_bonus_claimed"]:
                    await conn.execute(
                        "UPDATE users SET ai_energy_used = GREATEST(ai_energy_used - $2, 0), "
                        "daily_bonus_claimed = TRUE WHERE uid=$1",
                        uid, QUEST_ALL_DONE_BONUS
                    )
                    claimed_ids.append("all_done")
    return claimed_ids
