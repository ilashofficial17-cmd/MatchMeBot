# Спецификация: Миграция с in-memory на Redis

**Приоритет:** P1 | **Автор:** Архитектор | **Дата:** 2026-04-03

---

## 1. Что переносить, что оставлять

### Переносится в Redis

| Переменная | Тип | Обоснование |
|-----------|-----|-------------|
| `active_chats` | dict[uid→partner] | Критично: теряется при рестарте, юзеры зависают |
| `waiting_*` (7 очередей) | set[uid] | Критично: очереди поиска теряются |
| `last_msg_time` | dict[uid→datetime] | Критично: inactivity_checker не работает без этого |
| `chat_logs` | dict[key→list[msg]] | Важно: жалобы без логов не работают |
| `mutual_likes` | dict[uid→set[uid]] | Важно: теряются лайки, юзеры не получают матчи |
| `liked_chats` | set[(uid, key)] | Важно: без этого юзер лайкает повторно |
| `_ai_sessions` | dict[uid→session] | Важно: AI чат прерывается при рестарте |
| FSM Storage | MemoryStorage | Критично: все FSM-стейты теряются |

### Остаётся в памяти

| Переменная | Тип | Обоснование |
|-----------|-----|-------------|
| `msg_count` | dict[uid→list[ts]] | Rolling window 5сек, 1-10 writes/sec/user. Redis round-trip убьёт latency. При рестарте пустой msg_count безвреден — юзер просто сможет отправить 5 сообщений без throttle |
| `_last_ai_msg` | dict[uid→datetime] | Аналогично last_msg_time, но для AI. Дублируется в БД (ai_messages_reset). При рестарте восстанавливается из БД |
| `pairing_lock` | asyncio.Lock | Заменяется Redis-транзакциями (WATCH/MULTI/EXEC) |
| `_complaint_cooldown` | dict[uid→datetime] | Маленький, не критичен при потере |

---

## 2. Зависимость: redis.asyncio

```
# requirements.txt — добавить:
redis[hiredis]>=5.0.0
```

`redis.asyncio` — встроенный async-клиент в пакете `redis>=4.2`. `hiredis` — C-парсер, ускоряет на 30-50%.

**Не использовать:** `aioredis` — deprecated, вмержен в `redis` пакет.

**Подключение:**
```python
import redis.asyncio as aioredis

redis_pool = None

async def init_redis():
    global redis_pool
    redis_pool = aioredis.from_url(
        os.environ["REDIS_URL"],
        decode_responses=True,      # str вместо bytes
        max_connections=20,         # по числу asyncpg pool
    )
    await redis_pool.ping()
```

---

## 3. Railway: подключение Redis

1. В Railway Dashboard → New Service → Redis
2. Получить `REDIS_URL` (формат: `redis://default:password@host:port`)
3. Добавить в Environment Variables основного сервиса
4. Никаких дополнительных конфигов — `redis.asyncio.from_url()` парсит URL автоматически

**Тариф:** Redis на Railway — $0.000231/hr за 1MB RAM. При 1000 юзеров ~5MB = ~$0.04/месяц.

---

## 4. Схема ключей Redis

### Naming convention: `mm:{domain}:{id}`

```
mm:chat:active:{uid}          → STRING (partner_uid)          TTL: нет
mm:queue:{mode}:{premium}     → SET (uid, uid, ...)           TTL: нет
mm:chat:lastmsg:{uid}         → STRING (ISO timestamp)        TTL: 600 (10 мин)
mm:chat:log:{chat_key}        → LIST [json_msg, ...]          TTL: 3600 (1 час)
mm:mutual:likes:{uid}         → SET (partner_uid, ...)        TTL: 600 (10 мин)
mm:mutual:liked:{uid}:{key}   → STRING "1"                    TTL: 3600 (1 час)
mm:ai:session:{uid}           → HASH {char, history, count}   TTL: 1800 (30 мин)
```

### Детализация по структурам

#### 4.1. active_chats → STRING

```
KEY:   mm:chat:active:{uid}
VALUE: "{partner_uid}"
TTL:   нет (удаляется явно при disconnect)
```

**Почему STRING, а не HASH:** Каждый lookup — по одному uid. HASH потребовал бы один ключ для всех пар, а atomic-операции (спаривание/разъединение) проще с отдельными ключами через WATCH.

#### 4.2. waiting_* → SET (7 ключей)

```
KEY:   mm:queue:simple:free
KEY:   mm:queue:simple:premium
KEY:   mm:queue:flirt:free
KEY:   mm:queue:flirt:premium
KEY:   mm:queue:kink:free
KEY:   mm:queue:kink:premium
KEY:   mm:queue:anon:free
VALUE: SET of uid strings
TTL:   нет
```

**Маппинг:**
```python
def queue_key(mode: str, premium: bool) -> str:
    tier = "premium" if premium else "free"
    return f"mm:queue:{mode}:{tier}"

ALL_QUEUE_KEYS = [
    "mm:queue:anon:free",
    "mm:queue:simple:free", "mm:queue:flirt:free", "mm:queue:kink:free",
    "mm:queue:simple:premium", "mm:queue:flirt:premium", "mm:queue:kink:premium",
]
```

#### 4.3. last_msg_time → STRING с TTL

```
KEY:   mm:chat:lastmsg:{uid}
VALUE: ISO timestamp string
TTL:   600 (auto-cleanup через 10 мин — заменяет ручной cleanup в inactivity_checker)
```

#### 4.4. chat_logs → LIST (capped)

```
KEY:   mm:chat:log:{min_uid}:{max_uid}
VALUE: LIST of JSON strings: [{"sender":uid,"text":"...","time":"HH:MM:SS"}, ...]
TTL:   3600 (auto-cleanup через 1 час после последнего сообщения)
MAX:   10 записей (LTRIM после каждого RPUSH)
```

#### 4.5. mutual_likes → SET с TTL

```
KEY:   mm:mutual:likes:{uid}
VALUE: SET of partner_uid strings
TTL:   600 (10 мин — текущий таймаут mutual_likes)
```

#### 4.6. liked_chats → STRING (флаг)

```
KEY:   mm:mutual:liked:{uid}:{chat_key}
VALUE: "1"
TTL:   3600 (очистка автоматическая)
```

**Заменяет set:** Вместо `(uid, chat_key) in liked_chats` → `EXISTS mm:mutual:liked:{uid}:{chat_key}`.

#### 4.7. ai_sessions → HASH

```
KEY:   mm:ai:session:{uid}
FIELDS:
  character  → "luna"
  history    → JSON string: [{"role":"user","content":"..."},...]
  msg_count  → "5"
TTL:   1800 (30 мин inactivity — заменяет ручной cleanup)
```

---

## 5. FSM Storage → RedisStorage

```python
from aiogram.fsm.storage.redis import RedisStorage

storage = RedisStorage.from_url(os.environ["REDIS_URL"])
dp = Dispatcher(storage=storage)
```

**Ключи aiogram RedisStorage** (автоматические):
```
fsm:{bot_id}:{chat_id}:{user_id}:state    → STRING ("Chat:chatting")
fsm:{bot_id}:{chat_id}:{user_id}:data     → JSON (state data)
```

Не требует ручной миграции — aiogram сам управляет.

---

## 6. Код-примеры критических операций

### 6.1. Спаривание (atomic: убрать из очереди + добавить в active_chats)

**Текущий код (bot.py, pairing_lock):**
```python
async with pairing_lock:
    if uid in active_chats:
        return True
    for cand_pid, _, _, _, cand_q in candidates:
        if cand_pid not in active_chats and cand_pid in cand_q:
            partner = cand_pid
            cand_q.discard(partner)
            break
    if partner:
        active_chats[uid] = partner
        active_chats[partner] = uid
```

**Redis-версия (Lua script для атомарности):**
```python
PAIR_SCRIPT = """
local uid = KEYS[1]
local partner = KEYS[2]
local queue_key = KEYS[3]

-- Проверка: оба не в чате
if redis.call('EXISTS', 'mm:chat:active:' .. uid) == 1 then
    return -1   -- uid уже в чате
end
if redis.call('EXISTS', 'mm:chat:active:' .. partner) == 1 then
    return -2   -- partner уже в чате
end
-- Проверка: partner в очереди
if redis.call('SISMEMBER', queue_key, partner) == 0 then
    return -3   -- partner уже не в очереди
end

-- Атомарное спаривание
redis.call('SREM', queue_key, partner)
redis.call('SET', 'mm:chat:active:' .. uid, partner)
redis.call('SET', 'mm:chat:active:' .. partner, uid)

-- Убираем uid из всех очередей
local all_queues = redis.call('KEYS', 'mm:queue:*')
for _, qk in ipairs(all_queues) do
    redis.call('SREM', qk, uid)
end

local now = ARGV[1]
redis.call('SET', 'mm:chat:lastmsg:' .. uid, now, 'EX', 600)
redis.call('SET', 'mm:chat:lastmsg:' .. partner, now, 'EX', 600)

return 1  -- success
"""

# Регистрация скрипта при старте
pair_sha = await redis_pool.script_load(PAIR_SCRIPT)

# Вызов
async def try_pair(uid: int, partner: int, queue_key: str) -> bool:
    now = datetime.now().isoformat()
    result = await redis_pool.evalsha(
        pair_sha, 3,
        str(uid), str(partner), queue_key,
        now
    )
    return result == 1
```

**Почему Lua:** `WATCH/MULTI/EXEC` ненадёжен при конкурентных матчах — retry-loops сложнее. Lua-скрипт атомарен на уровне Redis, без race conditions.

### 6.2. Отключение (atomic: удалить из active_chats обоих)

```python
UNPAIR_SCRIPT = """
local uid = KEYS[1]
local partner = redis.call('GET', 'mm:chat:active:' .. uid)
if not partner then
    return 0  -- не был в чате
end

-- Удаляем обе стороны
redis.call('DEL', 'mm:chat:active:' .. uid)
redis.call('DEL', 'mm:chat:active:' .. partner)

-- Убираем из всех очередей (на всякий случай)
local all_queues = redis.call('KEYS', 'mm:queue:*')
for _, qk in ipairs(all_queues) do
    redis.call('SREM', qk, uid)
end

-- Очистка last_msg_time
redis.call('DEL', 'mm:chat:lastmsg:' .. uid)
redis.call('DEL', 'mm:chat:lastmsg:' .. partner)

return partner
"""

unpair_sha = await redis_pool.script_load(UNPAIR_SCRIPT)

async def disconnect(uid: int) -> int | None:
    """Returns partner_uid or None."""
    result = await redis_pool.evalsha(unpair_sha, 1, str(uid))
    return int(result) if result and result != 0 else None
```

### 6.3. Поиск партнёра (FIFO из очереди)

```python
async def get_candidates(queue_key: str, exclude_uid: int) -> list[int]:
    """Получить всех из очереди, кроме себя и занятых."""
    members = await redis_pool.smembers(queue_key)
    candidates = []
    for m in members:
        pid = int(m)
        if pid == exclude_uid:
            continue
        # Проверяем что не в чате (дешёвая проверка)
        if await redis_pool.exists(f"mm:chat:active:{pid}"):
            continue
        candidates.append(pid)
    return candidates
```

**Оптимизация:** Для больших очередей — использовать `SRANDMEMBER` вместо `SMEMBERS`:
```python
# Получить до 50 случайных кандидатов (O(N) → O(50))
members = await redis_pool.srandmember(queue_key, 50)
```

### 6.4. Chat logs — append + capped list

```python
async def log_message(uid1: int, uid2: int, sender: int, text: str):
    key = f"mm:chat:log:{min(uid1,uid2)}:{max(uid1,uid2)}"
    msg = json.dumps({"sender": sender, "text": text[:200],
                       "time": datetime.now().strftime("%H:%M:%S")})
    pipe = redis_pool.pipeline()
    pipe.rpush(key, msg)
    pipe.ltrim(key, -10, -1)    # Keep last 10
    pipe.expire(key, 3600)      # TTL 1 hour
    await pipe.execute()

async def get_chat_log(uid1: int, uid2: int) -> list[dict]:
    key = f"mm:chat:log:{min(uid1,uid2)}:{max(uid1,uid2)}"
    raw = await redis_pool.lrange(key, 0, -1)
    return [json.loads(r) for r in raw]
```

### 6.5. AI session — HASH operations

```python
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
    await redis_pool.expire(key, 1800)  # refresh TTL on access
    return {
        "character": data["character"],
        "history": json.loads(data["history"]),
        "msg_count": int(data["msg_count"]),
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
```

### 6.6. Mutual likes — SET с TTL

```python
async def add_mutual_like(uid: int, partner_uid: int) -> bool:
    """Returns True if mutual (both liked each other)."""
    my_key = f"mm:mutual:likes:{uid}"
    their_key = f"mm:mutual:likes:{partner_uid}"

    # Проверяем взаимность (Lua для атомарности)
    MUTUAL_SCRIPT = """
    local my_key = KEYS[1]
    local their_key = KEYS[2]
    local uid = ARGV[1]
    local partner = ARGV[2]

    -- Добавляем свой лайк
    redis.call('SADD', my_key, partner)
    redis.call('EXPIRE', my_key, 600)

    -- Проверяем взаимность
    if redis.call('SISMEMBER', their_key, uid) == 1 then
        -- Взаимный! Очищаем
        redis.call('SREM', my_key, partner)
        redis.call('SREM', their_key, uid)
        return 1
    end
    return 0
    """
    result = await redis_pool.eval(MUTUAL_SCRIPT, 2, my_key, their_key, str(uid), str(partner_uid))
    return result == 1
```

---

## 7. Замена pairing_lock

Текущий `pairing_lock` (asyncio.Lock) заменяется **Lua-скриптами**. Все операции, которые сейчас внутри `async with pairing_lock`, становятся атомарными Lua-скриптами на стороне Redis.

| Текущий блок | Redis замена |
|-------------|-------------|
| `cleanup()` lock | `UNPAIR_SCRIPT` |
| `do_find()` lock | `PAIR_SCRIPT` (цикл по кандидатам — в Python, сам match — в Lua) |
| `end_chat()` lock | `UNPAIR_SCRIPT` |
| `mutual_like()` lock | `MUTUAL_SCRIPT` + `PAIR_SCRIPT` |
| `anon_search()` lock | `PAIR_SCRIPT` |
| `cancel_search()` lock | `SREM` по всем очередям (pipeline) |

**Важно:** `pairing_lock` больше не нужен вообще. Lua-скрипт Redis — это atomic operation уровня сервера.

---

## 8. Миграция без даунтайма (graceful)

### Фаза 1: Dual-Write (1-2 дня)

Добавить Redis параллельно, не убирая in-memory:

```python
# Обёртка: пишет в оба места
async def set_active_chat(uid, partner):
    active_chats[uid] = partner              # in-memory (старое)
    await redis_pool.set(f"mm:chat:active:{uid}", str(partner))  # Redis (новое)

async def get_active_partner(uid):
    return active_chats.get(uid)             # читаем из in-memory (быстрее)
```

Это позволяет:
- Убедиться что Redis работает стабильно
- Сравнить состояние in-memory vs Redis (мониторинг)
- Откатиться мгновенно (просто убрать Redis-вызовы)

### Фаза 2: Read from Redis (1-2 дня)

Переключить чтение на Redis, запись в оба:
```python
async def get_active_partner(uid):
    result = await redis_pool.get(f"mm:chat:active:{uid}")
    return int(result) if result else None   # читаем из Redis
```

### Фаза 3: Remove in-memory (финал)

Удалить все dict'ы, переключить FSM на RedisStorage:
```python
# БЫЛО:
dp = Dispatcher(storage=MemoryStorage())

# СТАЛО:
from aiogram.fsm.storage.redis import RedisStorage
storage = RedisStorage.from_url(os.environ["REDIS_URL"])
dp = Dispatcher(storage=storage)
```

Удалить `pairing_lock`, заменить на Lua-скрипты.

### Фаза 4: Восстановление при старте

Добавить в `main()`:
```python
async def restore_from_db():
    """Восстановить active_chats из PostgreSQL (backup)."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT uid1, uid2 FROM active_chats_db")
        pipe = redis_pool.pipeline()
        for r in rows:
            pipe.set(f"mm:chat:active:{r['uid1']}", str(r['uid2']))
            pipe.set(f"mm:chat:active:{r['uid2']}", str(r['uid1']))
        await pipe.execute()
```

---

## 9. Новый модуль: redis_state.py

Весь Redis-доступ — в одном файле. Не разбрасывать по bot.py.

```
redis_state.py (новый файл):
  - init_redis(url)
  - Lua scripts (PAIR_SCRIPT, UNPAIR_SCRIPT, MUTUAL_SCRIPT)
  - set_active_chat(uid, partner)
  - get_active_partner(uid) -> int | None
  - disconnect(uid) -> int | None
  - add_to_queue(uid, mode, premium)
  - remove_from_queues(uid)
  - get_candidates(mode, premium, exclude_uid) -> list[int]
  - log_message(uid1, uid2, sender, text)
  - get_chat_log(uid1, uid2) -> list[dict]
  - set_last_msg_time(uid)
  - get_last_msg_time(uid) -> datetime | None
  - create_ai_session(uid, char_id, history)
  - get_ai_session(uid) -> dict | None
  - append_ai_message(uid, role, content)
  - delete_ai_session(uid)
  - add_mutual_like(uid, partner) -> bool
  - set_liked(uid, chat_key)
  - is_liked(uid, chat_key) -> bool
  - get_online_count() -> (pairs, searching)
```

---

## 10. Оценка нагрузки

### Redis операций/секунду при 1000 concurrent users

| Операция | Частота | Redis команд |
|----------|---------|-------------|
| relay message (active_chats GET) | 50-100/сек | 50-100 GET |
| relay message (last_msg_time SET) | 50-100/сек | 50-100 SET+EXPIRE |
| relay message (chat_log RPUSH) | 50-100/сек | 50-100 RPUSH+LTRIM |
| queue add/remove | 5-20/сек | 5-20 SADD/SREM |
| pairing (Lua script) | 2-10/сек | 2-10 EVALSHA |
| inactivity scan | 1/60сек | ~500 GET (scan all) |
| AI session read/write | 10-30/сек | 10-30 HGETALL/HSET |
| **Итого** | | **~200-400 ops/sec** |

**Redis single-thread throughput:** ~100,000 ops/sec (простые команды).

**Запас:** 250-500x. Бот может масштабироваться до **250,000 concurrent users** без деградации Redis.

### Latency

| Операция | In-memory | Redis (localhost) | Redis (Railway, same region) |
|----------|-----------|-------------------|------------------------------|
| GET | <1μs | ~0.1ms | ~1-2ms |
| SET | <1μs | ~0.1ms | ~1-2ms |
| EVALSHA (Lua) | N/A | ~0.2ms | ~2-3ms |
| Pipeline (3 cmd) | N/A | ~0.15ms | ~1.5-2.5ms |

**Влияние на UX:** Relay message добавит ~2-4ms latency (GET active_chats + SET last_msg_time). Незаметно для юзера.

### Memory

| Данные | При 1000 юзеров | При 10,000 юзеров |
|--------|-----------------|-------------------|
| active_chats (500 пар) | ~25 KB | ~250 KB |
| queues (200 юзеров) | ~10 KB | ~100 KB |
| chat_logs (500 чатов × 10 msg) | ~500 KB | ~5 MB |
| ai_sessions (300 × 20 msg) | ~1.5 MB | ~15 MB |
| last_msg_time | ~10 KB | ~100 KB |
| FSM states | ~50 KB | ~500 KB |
| **Итого** | **~2 MB** | **~21 MB** |

Railway Redis Free: 25 MB. При 10,000 юзеров — впритык. Pro ($5/мес) дает 256 MB.

---

## 11. Список файлов для изменения

| Файл | Изменения |
|------|-----------|
| **redis_state.py** | НОВЫЙ: весь Redis-доступ, Lua-скрипты |
| **bot.py** | Убрать dict'ы (active_chats, waiting_*, chat_logs, last_msg_time, mutual_likes, liked_chats). Заменить на вызовы redis_state. Убрать pairing_lock. FSM: MemoryStorage → RedisStorage |
| **ai_chat.py** | Убрать _ai_sessions, _last_ai_msg. Заменить на redis_state |
| **admin.py / admin_bot/** | Читать active_chats count из Redis вместо injected dict |
| **requirements.txt** | Добавить `redis[hiredis]>=5.0.0` |

---

## 12. Риски

| Риск | Уровень | Митигация |
|------|---------|-----------|
| Redis недоступен | Высокий | Healthcheck при старте. Circuit breaker: fallback на in-memory если Redis упал (Фаза 1 dual-write) |
| Latency сетевая | Низкий | Railway Redis в том же регионе: <2ms. Pipeline для batch |
| Lua-скрипты сложны для debug | Средний | Логирование результатов. Unit-тесты с fakeredis |
| KEYS команда в Lua (O(N)) | Средний | Заменить на hardcoded список 7 queue keys вместо `KEYS mm:queue:*` |
| Потеря данных при Redis restart | Средний | PostgreSQL backup (active_chats_db). Restore при старте |
| Memory overflow | Низкий | TTL на все ключи кроме active_chats и queues. Мониторинг `INFO memory` |
