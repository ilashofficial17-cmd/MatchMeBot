"""
Monitoring system for MatchMe Chat.
Collects metrics, checks thresholds, sends Telegram alerts.
All background tasks (monitoring_task, alert_checker, openrouter_health_probe)
are started from bot.py via init().
"""

import time
import resource
import logging
import asyncio
from collections import deque
from datetime import datetime
from typing import Any

import aiohttp
from aiogram import BaseMiddleware

logger = logging.getLogger("matchme.monitoring")

# ====================== INJECTED DEPENDENCIES ======================
_bot = None
_db_pool = None
_admin_id: int = 0
_redis_pool = None


def init(*, bot, db_pool, admin_id: int, redis_pool):
    global _bot, _db_pool, _admin_id, _redis_pool
    _bot = bot
    _db_pool = db_pool
    _admin_id = admin_id
    _redis_pool = redis_pool


# ====================== METRICS COLLECTOR ======================

class MetricsCollector:
    """Rolling-window metrics storage. Ticks every 30 sec, keeps 120 ticks (60 min)."""

    def __init__(self):
        self._response_times: deque[list[float]] = deque(maxlen=120)
        self._error_counts: deque[int] = deque(maxlen=120)
        self._redis_latency: deque[float] = deque(maxlen=120)
        self._pg_pool_used: deque[int] = deque(maxlen=120)
        self._memory_mb: deque[float] = deque(maxlen=120)
        self._ai_requests: deque[int] = deque(maxlen=120)

        self.total_requests: int = 0
        self.total_errors: int = 0
        self.total_ai_calls: int = 0
        self.boot_time: datetime = datetime.now()

        self._tick_times: list[float] = []
        self._tick_errors: int = 0
        self._tick_ai: int = 0

    def record_request(self, duration_ms: float):
        self._tick_times.append(duration_ms)
        self.total_requests += 1

    def record_error(self):
        self._tick_errors += 1
        self.total_errors += 1

    def record_ai_call(self):
        self._tick_ai += 1
        self.total_ai_calls += 1

    def flush_tick(self, redis_ms: float, pg_used: int, memory_mb: float):
        self._response_times.append(list(self._tick_times))
        self._error_counts.append(self._tick_errors)
        self._ai_requests.append(self._tick_ai)
        self._redis_latency.append(redis_ms)
        self._pg_pool_used.append(pg_used)
        self._memory_mb.append(memory_mb)
        self._tick_times = []
        self._tick_errors = 0
        self._tick_ai = 0

    def get_p95_response(self, window: int = 10) -> float:
        all_times: list[float] = []
        for times in list(self._response_times)[-window:]:
            all_times.extend(times)
        if not all_times:
            return 0.0
        all_times.sort()
        idx = int(len(all_times) * 0.95)
        return all_times[min(idx, len(all_times) - 1)]

    def get_error_rate(self, window: int = 10) -> float:
        recent = list(self._error_counts)[-window:]
        if not recent:
            return 0.0
        total = sum(recent)
        minutes = (window * 30) / 60
        return total / minutes if minutes > 0 else 0

    def get_snapshot(self) -> dict[str, Any]:
        uptime = (datetime.now() - self.boot_time).total_seconds()
        return {
            "uptime_sec": uptime,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "total_ai_calls": self.total_ai_calls,
            "p95_response_ms": round(self.get_p95_response(), 1),
            "error_rate_per_min": round(self.get_error_rate(), 2),
            "redis_latency_ms": round(self._redis_latency[-1], 1) if self._redis_latency else -1,
            "pg_pool_used": self._pg_pool_used[-1] if self._pg_pool_used else 0,
            "pg_pool_max": 20,
            "memory_mb": round(self._memory_mb[-1], 1) if self._memory_mb else 0,
            "ai_requests_per_min": sum(list(self._ai_requests)[-2:]),
        }


metrics = MetricsCollector()


# ====================== AIOGRAM MIDDLEWARE ======================

class MetricsMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        t0 = time.monotonic()
        try:
            result = await handler(event, data)
            duration = (time.monotonic() - t0) * 1000
            metrics.record_request(duration)
            return result
        except Exception:
            metrics.record_error()
            raise


# ====================== OPENROUTER HEALTH PROBE ======================

_last_openrouter_check: dict[str, Any] = {"ok": True, "latency_ms": 0, "checked_at": None}


def get_openrouter_status() -> dict:
    return dict(_last_openrouter_check)


async def openrouter_health_probe():
    import os
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPEN_ROUTER_KEY", "")
    while True:
        await asyncio.sleep(300)
        try:
            t0 = time.monotonic()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    _last_openrouter_check["ok"] = resp.status == 200
                    _last_openrouter_check["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
        except Exception:
            _last_openrouter_check["ok"] = False
            _last_openrouter_check["latency_ms"] = -1
        _last_openrouter_check["checked_at"] = datetime.now()


# ====================== MONITORING TASK (every 30s) ======================

async def monitoring_task():
    await asyncio.sleep(10)  # let other systems start
    while True:
        try:
            # Redis PING
            redis_ms = -1.0
            if _redis_pool:
                t0 = time.monotonic()
                await _redis_pool.ping()
                redis_ms = (time.monotonic() - t0) * 1000

            # PG pool stats
            pg_used = 0
            if _db_pool:
                pg_used = _db_pool.get_size() - _db_pool.get_idle_size()

            # Process memory (RSS in KB on Linux)
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            memory_mb = rss_kb / 1024

            metrics.flush_tick(redis_ms, pg_used, memory_mb)
        except Exception as e:
            logger.error(f"monitoring_task error: {e}")

        await asyncio.sleep(30)


# ====================== ALERT CHECKER (every 60s) ======================

_last_alert: dict[str, datetime] = {}
ALERT_COOLDOWN = 300  # 5 min between alerts of same type


async def alert_checker():
    await asyncio.sleep(60)  # let metrics accumulate
    while True:
        try:
            snap = metrics.get_snapshot()
            alerts: list[str] = []

            # Redis (Railway network latency is typically 50-150ms)
            if snap["redis_latency_ms"] < 0:
                alerts.append("🔴 Redis DISCONNECTED")
            elif snap["redis_latency_ms"] > 500:
                alerts.append(f"🔴 Redis latency CRITICAL: {snap['redis_latency_ms']:.0f}ms")
            elif snap["redis_latency_ms"] > 200:
                alerts.append(f"🟡 Redis latency: {snap['redis_latency_ms']:.0f}ms")

            # PG pool
            if snap["pg_pool_used"] >= 20:
                alerts.append("🔴 PG pool EXHAUSTED (20/20)")
            elif snap["pg_pool_used"] > 15:
                alerts.append(f"🟡 PG pool high: {snap['pg_pool_used']}/20")

            # Memory
            if snap["memory_mb"] > 500:
                alerts.append(f"🔴 Memory CRITICAL: {snap['memory_mb']:.0f} MB")
            elif snap["memory_mb"] > 400:
                alerts.append(f"🟡 Memory high: {snap['memory_mb']:.0f} MB")

            # Error rate
            if snap["error_rate_per_min"] > 20:
                alerts.append(f"🔴 Error rate: {snap['error_rate_per_min']:.1f}/min")
            elif snap["error_rate_per_min"] > 5:
                alerts.append(f"🟡 Error rate: {snap['error_rate_per_min']:.1f}/min")

            # Response time
            if snap["p95_response_ms"] > 5000:
                alerts.append(f"🔴 p95 response: {snap['p95_response_ms']:.0f}ms")
            elif snap["p95_response_ms"] > 2000:
                alerts.append(f"🟡 p95 response: {snap['p95_response_ms']:.0f}ms")

            # OpenRouter
            if not _last_openrouter_check["ok"] and _last_openrouter_check["checked_at"]:
                alerts.append("🔴 OpenRouter DOWN")

            now = datetime.now()
            for alert in alerts:
                key = alert[:20]
                last = _last_alert.get(key)
                if last and (now - last).total_seconds() < ALERT_COOLDOWN:
                    continue
                _last_alert[key] = now
                try:
                    await _bot.send_message(_admin_id, f"⚠️ ALERT\n{alert}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"alert_checker error: {e}")

        await asyncio.sleep(60)


# ====================== RATE LIMITER ======================

async def check_rate_limit(uid: int, action: str, limit: int, window_sec: int) -> bool:
    """
    Redis sorted-set sliding window rate limiter.
    Returns True if within limit, False if exceeded.
    """
    if not _redis_pool:
        return True  # no Redis = no rate limiting

    key = f"mm:ratelimit:{action}:{uid}"
    now = time.time()
    try:
        pipe = _redis_pool.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.zremrangebyscore(key, 0, now - window_sec)
        pipe.zcard(key)
        pipe.expire(key, window_sec + 10)
        results = await pipe.execute()
        count = results[2]
        return count <= limit
    except Exception:
        return True  # fail open — don't block users on Redis errors


# ====================== FORMAT HELPERS ======================

def format_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    mins = int((seconds % 3600) // 60)
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours:
        parts.append(f"{hours}ч")
    parts.append(f"{mins}мин")
    return " ".join(parts)


def format_dashboard() -> str:
    snap = metrics.get_snapshot()
    or_status = get_openrouter_status()
    or_icon = "✅" if or_status["ok"] else "❌"
    or_ms = f"{or_status['latency_ms']:.0f}ms" if or_status["latency_ms"] >= 0 else "N/A"

    return (
        f"📊 Мониторинг MatchMe Bot\n\n"
        f"⏱ Uptime: {format_uptime(snap['uptime_sec'])}\n"
        f"📨 Requests: {snap['total_requests']:,} total\n"
        f"❌ Errors: {snap['total_errors']:,} total ({snap['error_rate_per_min']:.1f}/мин)\n\n"
        f"⚡ Response time (p95): {snap['p95_response_ms']:.0f}ms\n"
        f"🔗 Redis latency: {snap['redis_latency_ms']:.1f}ms\n"
        f"🗄 PG pool: {snap['pg_pool_used']}/{snap['pg_pool_max']} used\n"
        f"💾 Memory: {snap['memory_mb']:.0f} MB\n\n"
        f"🤖 AI calls: {snap['ai_requests_per_min']}/мин\n"
        f"🌐 OpenRouter: {or_icon} ({or_ms})"
    )
