"""
Redis state management for MatchMe Chat.
All Redis access is centralized here. Replaces in-memory dicts and asyncio.Lock.
"""

import os
import json
import logging
from datetime import datetime

import redis.asyncio as aioredis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

logger = logging.getLogger("matchme.redis_state")

redis_pool: aioredis.Redis | None = None

# --- Lua script SHAs (loaded at init) ---
_pair_sha: str | None = None
_unpair_sha: str | None = None
_mutual_sha: str | None = None

# 7 hardcoded queue keys (NEVER use KEYS command in Lua)
ALL_QUEUE_KEYS = [
    "mm:queue:anon:free",
    "mm:queue:simple:free",
    "mm:queue:simple:premium",
    "mm:queue:flirt:free",
    "mm:queue:flirt:premium",
    "mm:queue:kink:free",
    "mm:queue:kink:premium",
]

# --- Lua Scripts ---

# PAIR_SCRIPT: atomic pairing — remove from queue + set active chats
# KEYS[1]=uid, KEYS[2]=partner, KEYS[3]=queue_key
# ARGV[1]=now (ISO timestamp)
# Returns: 1=success, -1=uid already in chat, -2=partner already in chat, -3=partner not in queue
PAIR_SCRIPT = """
local uid = KEYS[1]
local partner = KEYS[2]
local queue_key = KEYS[3]

if redis.call('EXISTS', 'mm:chat:active:' .. uid) == 1 then
    return -1
end
if redis.call('EXISTS', 'mm:chat:active:' .. partner) == 1 then
    return -2
end
if redis.call('SISMEMBER', queue_key, partner) == 0 then
    return -3
end

redis.call('SREM', queue_key, partner)
redis.call('SET', 'mm:chat:active:' .. uid, partner)
redis.call('SET', 'mm:chat:active:' .. partner, uid)

-- Remove uid from all queues (hardcoded, no KEYS command)
redis.call('SREM', 'mm:queue:anon:free', uid)
redis.call('SREM', 'mm:queue:simple:free', uid)
redis.call('SREM', 'mm:queue:simple:premium', uid)
redis.call('SREM', 'mm:queue:flirt:free', uid)
redis.call('SREM', 'mm:queue:flirt:premium', uid)
redis.call('SREM', 'mm:queue:kink:free', uid)
redis.call('SREM', 'mm:queue:kink:premium', uid)

local now = ARGV[1]
redis.call('SET', 'mm:chat:lastmsg:' .. uid, now, 'EX', 600)
redis.call('SET', 'mm:chat:lastmsg:' .. partner, now, 'EX', 600)

return 1
"""

# UNPAIR_SCRIPT: atomic disconnect — remove both from active_chats
# KEYS[1]=uid
# Returns: partner uid string or 0 if not in chat
UNPAIR_SCRIPT = """
local uid = KEYS[1]
local partner = redis.call('GET', 'mm:chat:active:' .. uid)
if not partner then
    return 0
end

redis.call('DEL', 'mm:chat:active:' .. uid)
redis.call('DEL', 'mm:chat:active:' .. partner)

-- Remove from all queues (safety)
redis.call('SREM', 'mm:queue:anon:free', uid)
redis.call('SREM', 'mm:queue:simple:free', uid)
redis.call('SREM', 'mm:queue:simple:premium', uid)
redis.call('SREM', 'mm:queue:flirt:free', uid)
redis.call('SREM', 'mm:queue:flirt:premium', uid)
redis.call('SREM', 'mm:queue:kink:free', uid)
redis.call('SREM', 'mm:queue:kink:premium', uid)

redis.call('DEL', 'mm:chat:lastmsg:' .. uid)
redis.call('DEL', 'mm:chat:lastmsg:' .. partner)

return partner
"""

# MUTUAL_SCRIPT: atomic mutual like check
# KEYS[1]=my_key, KEYS[2]=their_key
# ARGV[1]=uid, ARGV[2]=partner
# Returns: 1=mutual, 0=one-sided
MUTUAL_SCRIPT = """
local my_key = KEYS[1]
local their_key = KEYS[2]
local uid = ARGV[1]
local partner = ARGV[2]

redis.call('SADD', my_key, partner)
redis.call('EXPIRE', my_key, 600)

if redis.call('SISMEMBER', their_key, uid) == 1 then
    redis.call('SREM', my_key, partner)
    redis.call('SREM', their_key, uid)
    return 1
end
return 0
"""


def queue_key(mode: str, premium: bool) -> str:
    tier = "premium" if premium else "free"
    return f"mm:queue:{mode}:{tier}"


async def init_redis(url: str | None = None) -> bool:
    """
    Initialize Redis connection pool and load Lua scripts.
    Returns True if Redis is available, False otherwise (fallback to in-memory).
    """
    global redis_pool, _pair_sha, _unpair_sha, _mutual_sha

    url = url or os.environ.get("REDIS_URL")
    if not url:
        logger.warning("REDIS_URL not set — falling back to in-memory storage")
        return False

    try:
        retry = Retry(ExponentialBackoff(cap=2, base=0.1), retries=3)
        redis_pool = aioredis.from_url(
            url,
            decode_responses=True,
            max_connections=30,
            retry_on_timeout=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            health_check_interval=30,
            retry=retry,
            retry_on_error=[ConnectionError, TimeoutError],
        )
        await redis_pool.ping()
        logger.info("Redis connected successfully")

        # Load Lua scripts
        _pair_sha = await redis_pool.script_load(PAIR_SCRIPT)
        _unpair_sha = await redis_pool.script_load(UNPAIR_SCRIPT)
        _mutual_sha = await redis_pool.script_load(MUTUAL_SCRIPT)
        logger.info("Lua scripts loaded")

        return True
    except Exception as e:
        logger.error(f"Redis init failed: {e} — falling back to in-memory storage")
        redis_pool = None
        return False


# ---- Active Chats ----

async def set_active_chat(uid: int, partner: int):
    await redis_pool.set(f"mm:chat:active:{uid}", str(partner))
    await redis_pool.set(f"mm:chat:active:{partner}", str(uid))


async def get_active_partner(uid: int) -> int | None:
    result = await redis_pool.get(f"mm:chat:active:{uid}")
    return int(result) if result else None


async def disconnect(uid: int) -> int | None:
    """Atomic disconnect. Returns partner_uid or None."""
    result = await redis_pool.evalsha(_unpair_sha, 1, str(uid))
    return int(result) if result and result != "0" else None


async def is_in_chat(uid: int) -> bool:
    return await redis_pool.exists(f"mm:chat:active:{uid}") == 1


# ---- Queues ----

async def add_to_queue(uid: int, mode: str, premium: bool):
    key = queue_key(mode, premium)
    await redis_pool.sadd(key, str(uid))


async def remove_from_queues(uid: int):
    """Remove uid from all 7 queues via pipeline."""
    pipe = redis_pool.pipeline()
    for qk in ALL_QUEUE_KEYS:
        pipe.srem(qk, str(uid))
    await pipe.execute()


async def is_in_queue(uid: int) -> bool:
    """Check if uid is in any queue."""
    pipe = redis_pool.pipeline()
    for qk in ALL_QUEUE_KEYS:
        pipe.sismember(qk, str(uid))
    results = await pipe.execute()
    return any(results)


async def get_candidates(mode: str, premium: bool, exclude_uid: int) -> list[int]:
    """Get queue members excluding uid and those already in chat."""
    key = queue_key(mode, premium)
    members = await redis_pool.smembers(key)
    candidates = []
    for m in members:
        pid = int(m)
        if pid == exclude_uid:
            continue
        if await redis_pool.exists(f"mm:chat:active:{pid}"):
            continue
        candidates.append(pid)
    return candidates


async def get_queue_members(mode: str, premium: bool) -> set[int]:
    """Get all members of a specific queue."""
    key = queue_key(mode, premium)
    members = await redis_pool.smembers(key)
    return {int(m) for m in members}


async def try_pair(uid: int, partner: int, qkey: str) -> int:
    """
    Atomic pairing via Lua script.
    Returns: 1=success, -1=uid in chat, -2=partner in chat, -3=partner not in queue
    """
    now = datetime.now().isoformat()
    result = await redis_pool.evalsha(
        _pair_sha, 3,
        str(uid), str(partner), qkey,
        now,
    )
    return int(result)


# ---- Last Message Time ----

async def set_last_msg_time(uid: int):
    """Set last message timestamp with 10 min TTL."""
    now = datetime.now().isoformat()
    await redis_pool.set(f"mm:chat:lastmsg:{uid}", now, ex=600)


async def get_last_msg_time(uid: int) -> datetime | None:
    raw = await redis_pool.get(f"mm:chat:lastmsg:{uid}")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


async def get_all_active_last_msg() -> dict[int, datetime]:
    """Get all last_msg_time entries for inactivity checking.
    Scans active chats and returns their last msg times."""
    result = {}
    cursor = 0
    while True:
        cursor, keys = await redis_pool.scan(
            cursor=cursor, match="mm:chat:active:*", count=200
        )
        for key in keys:
            uid = int(key.split(":")[-1])
            ts = await redis_pool.get(f"mm:chat:lastmsg:{uid}")
            if ts:
                try:
                    result[uid] = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    pass
        if not cursor:
            break
    return result


# ---- Chat Logs ----

async def log_message(uid1: int, uid2: int, sender: int, text: str):
    key = f"mm:chat:log:{min(uid1, uid2)}:{max(uid1, uid2)}"
    msg = json.dumps({
        "sender": sender,
        "text": text[:200],
        "time": datetime.now().strftime("%H:%M:%S"),
    })
    pipe = redis_pool.pipeline()
    pipe.rpush(key, msg)
    pipe.ltrim(key, -10, -1)  # Keep last 10
    pipe.expire(key, 3600)    # TTL 1 hour
    await pipe.execute()


async def get_chat_log(uid1: int, uid2: int) -> list[dict]:
    key = f"mm:chat:log:{min(uid1, uid2)}:{max(uid1, uid2)}"
    raw = await redis_pool.lrange(key, 0, -1)
    return [json.loads(r) for r in raw]


async def delete_chat_log(uid1: int, uid2: int):
    key = f"mm:chat:log:{min(uid1, uid2)}:{max(uid1, uid2)}"
    await redis_pool.delete(key)


# ---- AI Sessions ----

async def create_ai_session(uid: int, char_id: str, history: list):
    key = f"mm:ai:session:{uid}"
    await redis_pool.hset(key, mapping={
        "character": char_id,
        "history": json.dumps(history),
        "msg_count": "0",
    })
    await redis_pool.expire(key, 1800)  # 30 min


async def get_ai_session(uid: int) -> dict | None:
    key = f"mm:ai:session:{uid}"
    data = await redis_pool.hgetall(key)
    if not data:
        return None
    await redis_pool.expire(key, 1800)  # refresh TTL
    return {
        "character": data["character"],
        "history": json.loads(data["history"]),
        "msg_count": int(data.get("msg_count", 0)),
    }


async def append_ai_message(uid: int, role: str, content: str):
    key = f"mm:ai:session:{uid}"
    raw = await redis_pool.hget(key, "history")
    if not raw:
        return
    history = json.loads(raw)
    history.append({"role": role, "content": content})
    if len(history) > 20:
        history = history[-20:]
    pipe = redis_pool.pipeline()
    pipe.hset(key, "history", json.dumps(history))
    pipe.hincrby(key, "msg_count", 1)
    pipe.expire(key, 1800)
    await pipe.execute()


async def delete_ai_session(uid: int):
    await redis_pool.delete(f"mm:ai:session:{uid}")


async def has_ai_session(uid: int) -> bool:
    return await redis_pool.exists(f"mm:ai:session:{uid}") == 1


# ---- Mutual Likes ----

async def add_mutual_like(uid: int, partner_uid: int) -> bool:
    """Returns True if mutual (both liked each other)."""
    my_key = f"mm:mutual:likes:{uid}"
    their_key = f"mm:mutual:likes:{partner_uid}"
    result = await redis_pool.evalsha(
        _mutual_sha, 2,
        my_key, their_key,
        str(uid), str(partner_uid),
    )
    return result == 1


async def set_liked(uid: int, chat_key: str):
    """Mark chat as liked (prevent spam)."""
    key = f"mm:mutual:liked:{uid}:{chat_key}"
    await redis_pool.set(key, "1", ex=3600)


async def is_liked(uid: int, chat_key: str) -> bool:
    key = f"mm:mutual:liked:{uid}:{chat_key}"
    return await redis_pool.exists(key) == 1


# ---- Stats / Online Count ----

async def get_online_count() -> tuple[int, int]:
    """Returns (active_pairs, searching_count)."""
    # Count active chats
    active_count = 0
    cursor = 0
    while True:
        cursor, keys = await redis_pool.scan(
            cursor=cursor, match="mm:chat:active:*", count=500
        )
        active_count += len(keys)
        if not cursor:
            break
    pairs = active_count // 2

    # Count searching across all queues
    pipe = redis_pool.pipeline()
    for qk in ALL_QUEUE_KEYS:
        pipe.scard(qk)
    counts = await pipe.execute()
    # Users can be in multiple queues, but for stats we just sum
    searching = sum(counts)

    return pairs, searching


# ---- AI Character Memory (long-term) ----

_MEMORY_TTL = 30 * 24 * 3600  # 30 days


async def save_memory(uid: int, char_id: str, summary: str):
    """Save conversation summary for uid+character. TTL 30 days."""
    key = f"mm:ai:memory:{uid}:{char_id}"
    await redis_pool.set(key, summary, ex=_MEMORY_TTL)


async def get_memory(uid: int, char_id: str) -> str | None:
    """Get last conversation summary for uid+character."""
    key = f"mm:ai:memory:{uid}:{char_id}"
    return await redis_pool.get(key)


async def save_user_facts(uid: int, char_id: str, facts: list[str]):
    """Save key facts about user (max 10). TTL 30 days."""
    key = f"mm:ai:facts:{uid}:{char_id}"
    pipe = redis_pool.pipeline()
    pipe.delete(key)
    for fact in facts[:10]:
        pipe.sadd(key, fact)
    pipe.expire(key, _MEMORY_TTL)
    await pipe.execute()


async def get_user_facts(uid: int, char_id: str) -> list[str]:
    """Get stored facts about user for this character."""
    key = f"mm:ai:facts:{uid}:{char_id}"
    members = await redis_pool.smembers(key)
    return list(members) if members else []
