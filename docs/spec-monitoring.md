# Спецификация: Мониторинг

**Приоритет:** P1 | **Автор:** Архитектор | **Дата:** 2026-04-05

---

## 1. Архитектура мониторинга

```
┌──────────────────────────────────────────────────────┐
│                    bot.py (основной)                  │
│                                                      │
│  monitoring_task() ─── каждые 30 сек ────┐           │
│    ├── Redis PING                        │           │
│    ├── PG pool stats                     ├─► MetricsCollector (in-memory)
│    ├── OpenRouter latency probe          │           │
│    ├── Process memory (RSS)              │           │
│    └── Queue/chat counts                 ┘           │
│                                                      │
│  request_tracker ─── на каждый хэндлер ──┐           │
│    ├── response_time histogram           ├─► MetricsCollector
│    └── error counter                     ┘           │
│                                                      │
│  alert_checker() ─── каждые 60 сек ──────────────┐   │
│    └── threshold checks → bot.send_message(ADMIN) │   │
└──────────────────────────────────────────────────────┘
```

**НЕ используем:** Prometheus, Grafana, StatsD — overkill для одного процесса на Railway.
**Используем:** asyncio background task + in-memory MetricsCollector + Telegram-алерты.

---

## 2. MetricsCollector — ядро мониторинга

### Новый файл: monitoring.py

```python
import time, os, asyncio, resource
from collections import deque
from datetime import datetime

class MetricsCollector:
    def __init__(self):
        # Rolling windows (последние 60 минут, записи каждые 30 сек = 120 точек)
        self._response_times = deque(maxlen=120)   # list[float] per tick
        self._error_counts = deque(maxlen=120)      # int per tick
        self._redis_latency = deque(maxlen=120)     # float ms
        self._pg_pool_used = deque(maxlen=120)      # int
        self._memory_mb = deque(maxlen=120)         # float
        self._ai_requests = deque(maxlen=120)       # int per tick

        # Counters (since boot)
        self.total_requests = 0
        self.total_errors = 0
        self.total_ai_calls = 0
        self.boot_time = datetime.now()

        # Current-tick accumulators (reset every 30 sec)
        self._tick_times = []
        self._tick_errors = 0
        self._tick_ai = 0

    def record_request(self, duration_ms: float):
        self._tick_times.append(duration_ms)
        self.total_requests += 1

    def record_error(self):
        self._tick_errors += 1
        self.total_errors += 1

    def record_ai_call(self):
        self._tick_ai += 1
        self.total_ai_calls += 1

    def flush_tick(self, redis_ms, pg_used, memory_mb):
        """Вызывается каждые 30 сек из monitoring_task."""
        self._response_times.append(list(self._tick_times))
        self._error_counts.append(self._tick_errors)
        self._ai_requests.append(self._tick_ai)
        self._redis_latency.append(redis_ms)
        self._pg_pool_used.append(pg_used)
        self._memory_mb.append(memory_mb)
        # Reset accumulators
        self._tick_times = []
        self._tick_errors = 0
        self._tick_ai = 0

    def get_p95_response(self, window=10) -> float:
        """p95 response time за последние window тиков (5 мин при window=10)."""
        all_times = []
        for times in list(self._response_times)[-window:]:
            all_times.extend(times)
        if not all_times:
            return 0.0
        all_times.sort()
        idx = int(len(all_times) * 0.95)
        return all_times[min(idx, len(all_times) - 1)]

    def get_error_rate(self, window=10) -> float:
        """Ошибок в минуту за последние window тиков."""
        recent = list(self._error_counts)[-window:]
        if not recent:
            return 0.0
        total = sum(recent)
        minutes = (window * 30) / 60
        return total / minutes if minutes > 0 else 0

    def get_snapshot(self) -> dict:
        """Полный снапшот для дашборда."""
        return {
            "uptime_sec": (datetime.now() - self.boot_time).total_seconds(),
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "total_ai_calls": self.total_ai_calls,
            "p95_response_ms": self.get_p95_response(),
            "error_rate_per_min": self.get_error_rate(),
            "redis_latency_ms": self._redis_latency[-1] if self._redis_latency else -1,
            "pg_pool_used": self._pg_pool_used[-1] if self._pg_pool_used else 0,
            "memory_mb": self._memory_mb[-1] if self._memory_mb else 0,
            "ai_requests_per_min": sum(list(self._ai_requests)[-2:]),
        }

metrics = MetricsCollector()  # Singleton
```

---

## 3. monitoring_task() — фоновый сбор метрик

Каждые 30 секунд:

```python
async def monitoring_task():
    while True:
        await asyncio.sleep(30)
        try:
            # 1. Redis PING
            t0 = time.monotonic()
            await redis_pool.ping()
            redis_ms = (time.monotonic() - t0) * 1000

            # 2. PG pool stats
            pg_used = db_pool.get_size() - db_pool.get_idle_size()

            # 3. Process memory
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KB on Linux
            memory_mb = rss / 1024

            # 4. Flush
            metrics.flush_tick(redis_ms, pg_used, memory_mb)

        except Exception as e:
            logger.error(f"monitoring_task error: {e}")
```

### OpenRouter health probe (отдельно, каждые 5 мин)

Чтобы не тратить API-лимиты, проверяем OpenRouter раз в 5 минут:

```python
_last_openrouter_check = {"ok": True, "latency_ms": 0, "checked_at": None}

async def openrouter_health_probe():
    while True:
        await asyncio.sleep(300)
        try:
            t0 = time.monotonic()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    _last_openrouter_check["ok"] = resp.status == 200
                    _last_openrouter_check["latency_ms"] = (time.monotonic() - t0) * 1000
        except Exception:
            _last_openrouter_check["ok"] = False
        _last_openrouter_check["checked_at"] = datetime.now()
```

---

## 4. Request tracking — middleware

aiogram middleware для замера времени каждого хэндлера:

```python
from aiogram import BaseMiddleware

class MetricsMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        t0 = time.monotonic()
        try:
            result = await handler(event, data)
            duration = (time.monotonic() - t0) * 1000
            metrics.record_request(duration)
            return result
        except Exception as e:
            metrics.record_error()
            raise
```

Регистрация:
```python
dp.message.middleware(MetricsMiddleware())
dp.callback_query.middleware(MetricsMiddleware())
```

---

## 5. Алерты

### Пороги

| Метрика | Warning | Critical | Действие |
|---------|---------|----------|---------|
| Redis ping | > 50ms | fail/timeout | Telegram алерт |
| PG pool used | > 15 (75%) | = 20 (100%) | Telegram алерт |
| Memory RSS | > 400 MB | > 500 MB | Telegram алерт |
| Error rate | > 5/мин | > 20/мин | Telegram алерт |
| p95 response | > 2000ms | > 5000ms | Telegram алерт |
| OpenRouter | — | 5xx / timeout | Telegram алерт |
| AI requests | > 50/мин | > 100/мин | Log warning (cost) |

### alert_checker() — каждые 60 секунд

```python
_last_alert = {}  # metric_name -> datetime (cooldown)
ALERT_COOLDOWN = 300  # 5 мин между алертами одного типа

async def alert_checker():
    while True:
        await asyncio.sleep(60)
        snap = metrics.get_snapshot()
        alerts = []

        if snap["redis_latency_ms"] < 0:
            alerts.append("🔴 Redis DISCONNECTED")
        elif snap["redis_latency_ms"] > 50:
            alerts.append(f"🟡 Redis latency: {snap['redis_latency_ms']:.0f}ms")

        if snap["pg_pool_used"] >= 20:
            alerts.append("🔴 PG pool EXHAUSTED (20/20)")
        elif snap["pg_pool_used"] > 15:
            alerts.append(f"🟡 PG pool high: {snap['pg_pool_used']}/20")

        if snap["memory_mb"] > 500:
            alerts.append(f"🔴 Memory CRITICAL: {snap['memory_mb']:.0f} MB")
        elif snap["memory_mb"] > 400:
            alerts.append(f"🟡 Memory high: {snap['memory_mb']:.0f} MB")

        if snap["error_rate_per_min"] > 20:
            alerts.append(f"🔴 Error rate: {snap['error_rate_per_min']:.1f}/min")
        elif snap["error_rate_per_min"] > 5:
            alerts.append(f"🟡 Error rate: {snap['error_rate_per_min']:.1f}/min")

        if snap["p95_response_ms"] > 5000:
            alerts.append(f"🔴 p95 response: {snap['p95_response_ms']:.0f}ms")
        elif snap["p95_response_ms"] > 2000:
            alerts.append(f"🟡 p95 response: {snap['p95_response_ms']:.0f}ms")

        if not _last_openrouter_check["ok"]:
            alerts.append("🔴 OpenRouter DOWN")

        for alert in alerts:
            key = alert[:20]  # dedup by prefix
            last = _last_alert.get(key)
            if last and (datetime.now() - last).total_seconds() < ALERT_COOLDOWN:
                continue
            _last_alert[key] = datetime.now()
            try:
                await bot.send_message(ADMIN_ID, f"⚠️ ALERT\n{alert}")
            except Exception:
                pass
```

---

## 6. Uptime tracking

При старте:
```python
await update_stat("bot_start_time", datetime.now().isoformat())
```

В `monitoring_task()` каждые 30 сек:
```python
await update_stat("bot_uptime_sec", str(int((datetime.now() - boot_time).total_seconds())))
await update_stat("bot_last_heartbeat", datetime.now().isoformat())
```

Отображение в админке:
```
Uptime: 3д 14ч 22мин
Last heartbeat: 2 сек назад
```

---

## 7. Админ-дашборд

Новая кнопка "📊 Мониторинг" в admin_bot → раздел "Аналитика":

```
📊 Мониторинг MatchMe Bot

⏱ Uptime: 3д 14ч 22мин
📨 Requests: 142,857 total
❌ Errors: 23 total (0.2/мин)

⚡ Response time (p95): 145ms
🔗 Redis latency: 1.2ms
🗄 PG pool: 3/20 used
💾 Memory: 186 MB

🤖 AI calls: 12/мин
🌐 OpenRouter: ✅ OK (234ms)

👥 Online: 142 пар
🔍 В поиске: 37
🤖 AI сессий: 89
```

Callback: `admin:monitoring` → вызывает `metrics.get_snapshot()` + форматирует.

---

## 8. Файлы для изменения

| Файл | Изменения |
|------|-----------|
| **monitoring.py** | НОВЫЙ: MetricsCollector, monitoring_task, alert_checker, openrouter_health_probe |
| **bot.py** | Запуск monitoring_task + alert_checker + openrouter_health_probe в main(). Регистрация MetricsMiddleware |
| **ai_utils.py** | Добавить `metrics.record_ai_call()` в каждый API вызов |
| **admin_bot/admin/router.py** | Новый хэндлер `admin:monitoring` |
| **admin_bot/keyboards.py** | Кнопка "📊 Мониторинг" |

---

## 9. SQL миграции

Не требуются. Uptime хранится в существующей `bot_stats` (key-value).
