# Спецификация: Масштабирование

**Приоритет:** P1 | **Автор:** Архитектор | **Дата:** 2026-04-05

---

## 1. Текущие лимиты и целевые

| Компонент | Текущее значение | Предел | Целевое |
|-----------|-----------------|--------|---------|
| asyncpg pool | min=5, max=20 | ~200 concurrent queries | min=5, max=20 (OK до 50K MAU) |
| Redis pool | max_connections=20 | ~100K ops/sec | max_connections=30 |
| OpenRouter semaphore | 10 concurrent | зависит от плана | 20 |
| aiogram polling | 1 process | ~500 updates/sec | 1 process (до 100K MAU) |
| Railway RAM | 512 MB (default) | 8 GB (Pro) | 1 GB при 50K MAU |

---

## 2. asyncpg Pool

### Текущая конфигурация (bot.py:88)

```python
db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
```

### Анализ

При 1000 concurrent users:
- Средний handler делает 1-3 DB запроса
- Средний запрос: 2-10ms
- Throughput: 20 connections × 100 queries/sec/conn = **2000 queries/sec**
- При 100 req/sec от юзеров × 2 queries/req = 200 queries/sec → **загрузка 10%**

**Pool exhaustion** наступает при: 20 connections × 30ms (медленный запрос) = 667 queries/sec → ~300 concurrent handlers с медленными запросами.

### Рекомендация по порогам

| MAU | Concurrent | Pool size | Обоснование |
|-----|-----------|-----------|-------------|
| 10K | ~300 | min=5, max=20 | Достаточно — 10% загрузка |
| 50K | ~1500 | min=10, max=30 | PG на Railway выдерживает 50 connections |
| 100K | ~3000 | min=10, max=40 | Нужен PG Pro plan |

### Overflow handling

Сейчас: asyncpg ждёт освобождения connection (блокирует coroutine).
Добавить timeout:

```python
db_pool = await asyncpg.create_pool(
    DATABASE_URL,
    min_size=5,
    max_size=20,
    command_timeout=10,      # таймаут SQL запроса
    max_inactive_connection_lifetime=300,  # закрыть idle connections через 5 мин
)
```

---

## 3. Redis Connection Pool

### Текущая конфигурация (redis_state.py:142-146)

```python
redis_pool = aioredis.from_url(url, decode_responses=True, max_connections=20)
```

### Анализ

Redis single-thread: ~100K simple ops/sec.
При 1000 concurrent users, 100 messages/sec:
- Каждый message relay: 2-3 Redis ops (GET active_chats, SET last_msg_time, RPUSH chat_log)
- Pairing: 1 EVALSHA (Lua script) = 1 op
- Total: ~300-500 ops/sec → **0.5% Redis capacity**

### Рекомендация

```python
redis_pool = aioredis.from_url(
    url,
    decode_responses=True,
    max_connections=30,
    retry_on_timeout=True,
    socket_timeout=5,           # таймаут на операцию
    socket_connect_timeout=5,   # таймаут на connect
    health_check_interval=30,   # пинг каждые 30 сек
)
```

### Retry policy

```python
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

retry = Retry(ExponentialBackoff(cap=2, base=0.1), retries=3)

redis_pool = aioredis.from_url(
    url,
    decode_responses=True,
    max_connections=30,
    retry=retry,
    retry_on_error=[ConnectionError, TimeoutError],
)
```

---

## 4. Rate Limiting

### 4.1. Per-user message rate (уже есть частично)

Текущая защита (bot.py): `msg_count` — 5 сообщений за 5 секунд.

**Дополнительный лимит для масштабирования:**

```python
# Redis-based rate limiter (sliding window)
async def check_rate_limit(uid: int, action: str, limit: int, window_sec: int) -> bool:
    key = f"mm:ratelimit:{action}:{uid}"
    now = time.time()
    pipe = redis_pool.pipeline()
    pipe.zadd(key, {str(now): now})
    pipe.zremrangebyscore(key, 0, now - window_sec)
    pipe.zcard(key)
    pipe.expire(key, window_sec + 10)
    results = await pipe.execute()
    count = results[2]
    return count <= limit
```

| Действие | Лимит | Окно | Обоснование |
|----------|-------|------|-------------|
| Сообщения в чате | 5 | 5 сек | Антиспам (уже есть) |
| Поиск партнёра | 3 | 60 сек | Антифлуд поиска |
| AI сообщения | 30 | 60 сек | Защита от API abuse |
| Жалобы | 3 | 300 сек | Антиспам жалоб |
| Лайки (mutual) | 10 | 60 сек | Антифлуд лайков |

### 4.2. Global OpenRouter budget

```python
# constants.py — добавить:
OPENROUTER_DAILY_BUDGET_USD = 10.0   # $10/день максимум
OPENROUTER_HOURLY_LIMIT = 500        # запросов в час

# В ai_utils.py:
_ai_hour_counter = 0
_ai_hour_reset = datetime.now()

async def check_ai_budget() -> bool:
    global _ai_hour_counter, _ai_hour_reset
    now = datetime.now()
    if (now - _ai_hour_reset).total_seconds() > 3600:
        _ai_hour_counter = 0
        _ai_hour_reset = now
    if _ai_hour_counter >= OPENROUTER_HOURLY_LIMIT:
        return False
    _ai_hour_counter += 1
    return True
```

При достижении лимита — показывать юзеру: "AI временно недоступен, попробуйте через 30 минут".

---

## 5. Queue optimization: 1000+ людей в очереди

### Текущая проблема

`do_find()` (bot.py) итерирует всех кандидатов из очереди:
```python
for pid in list(q):       # O(N) — получить всех
    pu = await get_user(pid)  # DB запрос на каждого!
```

При 1000 людей в очереди → 1000 DB запросов на один `do_find()`.

### Решение: двухфазный поиск

**Фаза 1: Redis-фильтрация (без DB)**
```python
# Получить до 50 случайных кандидатов
candidates_raw = await redis_pool.srandmember(queue_key, 50)

# Отфильтровать занятых (batch EXISTS)
pipe = redis_pool.pipeline()
for pid in candidates_raw:
    pipe.exists(f"mm:chat:active:{pid}")
results = await pipe.execute()
available = [pid for pid, exists in zip(candidates_raw, results) if not exists]
```

**Фаза 2: DB-обогащение (только для доступных)**
```python
# Загрузить профили пакетом (один запрос вместо N)
if available:
    rows = await db_pool.fetch(
        "SELECT * FROM users WHERE uid = ANY($1::bigint[])",
        available[:20]  # макс 20 кандидатов
    )
```

**Результат:** вместо 1000 DB запросов → 1 Redis pipeline + 1 batch DB запрос.

### Оценка времени

| Очередь | Текущее | Оптимизированное |
|---------|---------|-----------------|
| 100 чел | ~200ms (100 DB) | ~15ms (1 Redis + 1 DB) |
| 1000 чел | ~2000ms | ~20ms |
| 10000 чел | ~20000ms (!) | ~25ms |

---

## 6. Memory management

### Redis TTL стратегия (текущая + рекомендации)

| Ключ | Текущий TTL | Рекомендуемый | Обоснование |
|------|-------------|---------------|-------------|
| `mm:chat:active:{uid}` | нет | нет (explicit delete) | Нельзя автоудалять — юзер потеряет чат |
| `mm:queue:*` | нет | нет (explicit remove) | Нельзя автоудалять — юзер выпадет из поиска |
| `mm:chat:lastmsg:{uid}` | 600с | 600с ✓ | |
| `mm:chat:log:{key}` | 3600с | 3600с ✓ | |
| `mm:ai:session:{uid}` | 1800с | 1800с ✓ | |
| `mm:mutual:likes:{uid}` | 600с | 600с ✓ | |
| `mm:ratelimit:*` | window+10с | window+10с | Автоочистка |
| FSM states | нет (aiogram) | 86400с (24ч) | Добавить TTL — "забытые" FSM states накапливаются |

### Cleanup задача (дополнение к inactivity_checker)

Каждые 10 минут — проверять "мёртвые души":

```python
async def redis_cleanup():
    """Удаляет orphaned ключи — юзеры в active_chats, которых нет в Telegram."""
    while True:
        await asyncio.sleep(600)
        # Проверяем: есть ли active_chats без last_msg_time
        # Если last_msg_time expired (TTL 600с) но active_chat жив — orphan
        cursor = 0
        while True:
            cursor, keys = await redis_pool.scan(cursor, match="mm:chat:active:*", count=200)
            for key in keys:
                uid = key.split(":")[-1]
                has_msg = await redis_pool.exists(f"mm:chat:lastmsg:{uid}")
                if not has_msg:
                    # Orphan — нет сообщений 10+ минут, но чат "жив"
                    # Отключить через UNPAIR_SCRIPT
                    await disconnect(int(uid))
            if cursor == 0:
                break
```

### Оценка Redis memory

| MAU | Concurrent | active_chats | queues | chat_logs | ai_sessions | FSM | **Total** |
|-----|-----------|-------------|--------|-----------|------------|-----|-----------|
| 10K | 500 | 12 KB | 5 KB | 250 KB | 750 KB | 250 KB | **~1.3 MB** |
| 50K | 2500 | 60 KB | 25 KB | 1.2 MB | 3.7 MB | 1.2 MB | **~6.2 MB** |
| 100K | 5000 | 120 KB | 50 KB | 2.5 MB | 7.5 MB | 2.5 MB | **~12.7 MB** |

Railway Redis Free: 25 MB. Хватает до **~200K MAU**.

---

## 7. Bottleneck analysis

### Где сломается первым

```
Нагрузка ──────────────────────────────────────────────►

10K MAU          50K MAU          100K MAU
│                │                │
▼                ▼                ▼

[1] OpenRouter   [3] PG pool     [5] Single process
    semaphore        exhaustion       CPU bound
    (10 concurrent)  (20 conn)        (1 core)

[2] Queue scan   [4] Memory       [6] Telegram
    O(N) per         RSS > 512MB      API rate limits
    do_find()                         (30 req/sec/bot)
```

| # | Bottleneck | При каком MAU | Симптом | Решение |
|---|-----------|---------------|---------|---------|
| 1 | OpenRouter semaphore=10 | 10K | AI response > 5с | Увеличить до 20-30 |
| 2 | Queue scan O(N) | 10K | do_find() > 2с | Двухфазный поиск (секция 5) |
| 3 | PG pool=20 | 50K | Handlers зависают | Увеличить до 30-40, добавить timeout |
| 4 | Memory 512MB | 50K | OOM kill | Railway 1GB plan |
| 5 | Single process CPU | 100K | p95 > 3с, event loop lag | Horizontal scaling (секция 8) |
| 6 | Telegram API limits | 100K | 429 Too Many Requests | Batch notifications, queue sends |

### Telegram API rate limits (важно!)

- `sendMessage`: 30 req/sec к одному чату, ~30 req/sec глобально для бота
- При 100K MAU background tasks (reminders, winback, streaks) могут отправлять тысячи сообщений
- **Решение:** Очередь отправки с throttle 25 msg/sec:

```python
_send_queue = asyncio.Queue()

async def throttled_sender():
    while True:
        uid, text, kwargs = await _send_queue.get()
        try:
            await bot.send_message(uid, text, **kwargs)
        except Exception:
            pass
        await asyncio.sleep(0.04)  # 25 msg/sec
```

---

## 8. Horizontal scaling (2+ процесса)

### Когда нужно

При CPU > 80% на одном процессе (~100K MAU). Один Python process = один event loop = один CPU core.

### Что нужно поменять

| Компонент | Текущее | Для 2+ процессов |
|-----------|---------|-------------------|
| Redis state | ✅ Уже готово | Ничего менять не нужно — Redis общий |
| FSM storage | ✅ RedisStorage | Ничего менять не нужно |
| Background tasks | ❌ Все запускаются | Нужен leader election |
| pairing_lock | ✅ Lua scripts | Ничего менять не нужно |
| Telegram polling | ❌ 1 процесс | Нужен webhook вместо polling |

### Leader election для background tasks

Только один процесс должен запускать: inactivity_checker, reminder_task, winback_task, monitoring_task.

```python
async def try_become_leader(ttl=60) -> bool:
    """Попытка стать лидером. Лидер обновляет каждые ttl/2 сек."""
    return await redis_pool.set(
        "mm:leader",
        os.environ.get("RAILWAY_REPLICA_ID", "default"),
        nx=True,    # только если ключа нет
        ex=ttl      # TTL — если лидер умер, другой подхватит
    )

async def leader_loop():
    is_leader = False
    while True:
        is_leader = await try_become_leader()
        if is_leader and not tasks_running:
            start_background_tasks()
        elif not is_leader and tasks_running:
            stop_background_tasks()
        await asyncio.sleep(30)  # renew / check every 30s
```

### Webhook вместо polling

```python
# Для 2+ процессов:
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# Telegram будет слать updates на https://your-app.railway.app/webhook
# Railway load balancer распределяет между репликами
```

### План миграции на 2+ процесса

1. Webhook endpoint + WEBHOOK_URL env var
2. Leader election в Redis
3. Background tasks только на лидере
4. Railway: увеличить replicas до 2
5. Тест: рестарт одного процесса → лидер переключается

**Когда:** При CPU consistently > 70% на одном процессе.

---

## 9. Cost projection

### Railway

| Компонент | 10K MAU | 50K MAU | 100K MAU |
|-----------|---------|---------|----------|
| Bot process (512MB) | $5 | $10 (1GB) | $20 (2GB, 2 replicas) |
| PostgreSQL (1GB) | $5 | $10 (5GB) | $20 (10GB) |
| Redis (25MB) | $3 | $5 (100MB) | $5 (100MB) |
| **Subtotal** | **$13** | **$25** | **$45** |

### OpenRouter API

Из финансовой модели:
- Average AI cost: $0.133 per active user per month
- DAU = 30% MAU

| MAU | DAU | AI cost/мес |
|-----|-----|-------------|
| 10K | 3K | **$400** |
| 50K | 15K | **$2,000** |
| 100K | 30K | **$4,000** |

### Total cost

| MAU | Infra | AI API | **Total** |
|-----|-------|--------|-----------|
| 10K | $13 | $400 | **$413** |
| 50K | $25 | $2,000 | **$2,025** |
| 100K | $45 | $4,000 | **$4,045** |

### Revenue (при 3% конверсии, RU-weighted)

| MAU | Paying (3%) | Revenue (чистый) | **Profit** |
|-----|-----------|------------------|------------|
| 10K | 300 | $1,908 | **+$1,495** |
| 50K | 1,500 | $9,540 | **+$7,515** |
| 100K | 3,000 | $19,080 | **+$15,035** |

---

## 10. Приоритетный план действий

| # | Действие | Когда | Усилие |
|---|----------|-------|--------|
| 1 | Двухфазный поиск (queue optimization) | **Сейчас** — O(N) уже тормозит при 100+ в очереди | 2-3 часа |
| 2 | Rate limiting (Redis-based) | До запуска рекламы | 3-4 часа |
| 3 | OpenRouter budget cap | До запуска рекламы | 1 час |
| 4 | asyncpg command_timeout + max_inactive | При 10K MAU | 30 мин |
| 5 | Redis retry policy + health_check | При 10K MAU | 30 мин |
| 6 | Throttled sender (Telegram rate limit) | При 10K MAU | 2 часа |
| 7 | Увеличить pool sizes | При 50K MAU | Конфиг |
| 8 | Railway RAM upgrade | При 50K MAU | Конфиг |
| 9 | Webhook + leader election | При 100K MAU | 1 день |

---

## 11. Файлы для изменения

| Файл | Что менять |
|------|-----------|
| **bot.py** | do_find() — двухфазный поиск. Pool timeout config. Throttled sender |
| **redis_state.py** | Retry policy, health_check_interval, socket_timeout |
| **ai_utils.py** | Budget cap, увеличить semaphore |
| **constants.py** | RATE_LIMITS dict, OPENROUTER_HOURLY_LIMIT, OPENROUTER_DAILY_BUDGET |
| **monitoring.py** | Rate limiter helper (check_rate_limit) |

## 12. SQL миграции

Не требуются.
