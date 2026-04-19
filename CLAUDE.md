# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**MatchMeBot** — анонимный Telegram-дейтинг бот с AI-персонажами и монетизацией через Telegram Stars. Три языка (ru/en/es), три режима общения (simple/flirt/kink), 13 AI-персонажей трёх тиров. Основной доход: Premium-подписки, пачки энергии, подарки.

## Running the Project

```bash
# Install dependencies (Python 3.11+)
pip install -r requirements.txt

# Run the main bot
python bot.py

# Run the admin bot (separate process)
python admin_bot/main.py
```

**Required env vars:** `BOT_TOKEN`, `DATABASE_URL`, `ADMIN_ID`, `OPEN_ROUTER`  
**Optional:** `REDIS_URL` (без него — in-memory fallback), `CHANNEL_BOT_TOKEN`, `AI_HOURLY_LIMIT` (default 500)

No test suite exists. No linter config. Manual testing via Telegram.

## Architecture

### Module Map

```
bot.py                  — точка входа: DB/Redis init, DI всех роутеров, мониторинг
registration.py         — онбординг FSM: name→age→gender→mode→interests, /start, реферальная система
matching.py             — двухфазный поиск партнёра
chat.py                 — relay сообщений, end_chat, лайки, рейтинг, жалобы, подарки
profile.py              — /profile, /stats, /settings, уровни, стрики, квесты, достижения
payments.py             — /premium, Telegram Stars инвойсы, премиум/энергия/подарки
ai_chat.py              — AI-чат, система энергии, долгосрочная память, медиа-покупки
ai_utils.py             — обёртка OpenRouter API (chat, vision, voice, summarize, translate)
ai_characters.py        — 13 AI-персонажей: system prompts, tier, model, media
redis_state.py          — Redis pool + Lua scripts, ключи состояния
monitoring.py           — метрики, rate limiting, алерты в ADMIN_ID
keyboards.py            — все кнопки (reply + inline), мультиязычные через locales
locales.py              — ~510 ключей × 3 языка; использование: t(lang, "key", **kwargs)
constants.py            — цены, лимиты, стоп-слова, партнёрская реклама, возврат подарков
states.py               — FSM состояния: Reg, Chat, AIChat, EditProfile, Complaint, …
db.py                   — DB-хелперы (asyncpg pool)
admin_bot/              — отдельный процесс: панель, модерация, задачи, канал
funnel_bots/            — маркетинговые боты (отдельные процессы)
docs/                   — спеки фичей (Redis, мониторинг, модерированные посты, и т.д.)
```

### Dependency Injection Pattern

Все 6 роутеров **не импортируют друг друга**. `bot.py` инициализирует их через `init()` функции:

```python
# bot.py pattern
from matching import router as matching_router, init as init_matching
init_matching(db_pool, redis_pool, do_find_callback=chat.do_find)
dp.include_router(matching_router)
```

Единственное исключение: `matching.py` вызывает `do_find` из `chat.py` через callback, зарегистрированный при `init()`. Это разрывает циклический импорт.

### Two-Phase Matching Algorithm (`matching.py`)

Ключевая оптимизация для масштаба:
1. **Redis Phase**: `SRANDMEMBER` до 50 случайных кандидатов из очереди + batch `EXISTS` check
2. **DB Phase**: один `SELECT WHERE uid = ANY($1)` вместо N запросов
3. Фильтры: пол, возраст, язык, режим, shadow_ban, интересы, cross-mode consent
4. Сортировка: premium > общие интересы > рейтинг
5. Атомарное спаривание через Lua скрипт (race condition protection)
6. 30 сек таймаут → предложение AI-чата

### Redis State

```
mm:chat:active:{uid}          string   → partner_uid
mm:queue:{mode}:{premium}     set      → UIDs в поиске (7 очередей)
mm:chat:log:{uid1}:{uid2}     list     TTL 1h    → JSON логи для модерации
mm:ai:session:{uid}           hash     TTL 30m   → {character, history, msg_count, loaded_memory}
mm:mutual:likes:{uid}         set      TTL 10m   → UIDs, которые лайкнули этого юзера
mm:ai:memory:{uid}:{char}     string   TTL 30d   → резюме последних 2 разговоров
mm:ai:facts:{uid}:{char}      set      TTL 30d   → до 10 фактов о пользователе
mm:ratelimit:{uid}:{action}   zset               → sliding window (search, ai_msg, complaint)
```

Три Lua скрипта в `redis_state.py`: `PAIR_SCRIPT`, `UNPAIR_SCRIPT`, `MUTUAL_SCRIPT` — атомарные операции без гонок.

Если Redis недоступен: `_use_redis = False`, всё работает через Python dicts (fallback).

### AI System

**Тиры персонажей:**
- `basic` (gpt-4o-mini, 1⚡/msg): Luna, Мах, Мия, Кай
- `vip` (gemini-flash / hermes-70b, 2⚡): Аврора, Алекс, Диана, Леон
- `vip_plus` (hermes-405b, 3⚡): Лилит, Ева, Дамир, Арс, Мастер

**Лимиты энергии:** free=30⚡/день, premium=200⚡/день + bonus_energy (макс 500, начисляется за рейтинги/квесты/стрики).

**Долгосрочная память (`ai_chat.py`):**
- При старте сессии — грузит `mm:ai:memory` + `mm:ai:facts`, кеширует в `mm:ai:session:{uid}` → поле `loaded_memory` (экономит 2 Redis GET на каждое сообщение)
- При закрытии (≥4 сообщений) — суммаризирует через Gemini Flash, мержит с предыдущей памятью (хранятся последние 2 резюме), TTL 30 дней

**Budget mode в `ai_utils.py`:** при превышении `AI_HOURLY_LIMIT` фоллбэк на `google/gemini-flash-1.5`.

### Database Schema (ключевые таблицы)

`users`: ~50 колонок — uid (PK), name, age, gender, lang, mode, accept_simple/flirt/kink, accept_cross_mode, search_gender, search_age_min/max, premium_until, premium_tier, trial_used, ai_energy_used, bonus_energy, streak_days, level, shadow_ban, ab_group, referred_by

Дополнительные: `ai_history`, `ai_character_media`, `user_purchased_media`, `ai_notes`, `achievements`, `daily_quests`, `complaints_log`, `chat_ratings`, `ab_events`, `active_chats_db`, `bot_stats`

### Monetization Logic

- **A/B тестирование**: поле `ab_group` (A/B). Группа B получает скидку 15% на Premium.
- **Trial Premium**: одноразово, предлагается после 5-го чата.
- **Gifts**: роза/бриллиант/корона → получатель получает Premium на 1/3/7 дней.
- **Уровни**: 6 уровней на основе `total_chats`; разблокируют режимы.
- **Квесты**: ежедневно 3 случайных из 5 типов (chat×3, rate×2, ai×5, like×2, streak). Все выполнены → +5 бонусной энергии.

### Localization

```python
from locales import t, _all

text = t(lang, "key", name="Иван")  # возвращает строку для нужного языка
filters = F.text.in_(_all("btn_find"))  # все языковые варианты для фильтра
```

Не добавляй новые ключи только в один язык — `locales.py` требует запись во все три (ru/en/es).

### Monitoring & Alerts

`monitoring.py` запускает 3 фоновые задачи (через `bot.py`):
- `monitoring_task` (30s): Redis PING, PG pool stats, memory RSS
- `alert_checker` (60s): пороги → Telegram алерт ADMIN_ID
- `openrouter_health_probe` (5m): GET к OpenRouter API

Rate limiting: `check_rate_limit(uid, action, limit, window_sec)` через Redis sorted-set.

## Project History (Git)

| Коммит | Что было сделано |
|--------|-----------------|
| fd34691 | Долгосрочная AI-память (Redis TTL 30d) — интегрирован из PR #6 |
| 536ed4f | Merge: 6-модульный рефакторинг (итог) |
| a09649f | README обновлён под 6-модульную архитектуру |
| deac385 | Удалён мёртвый код из bot.py |
| 15d4614 | Багфиксы profile.py (fallback-режим) |
| 477e372 | **Рефакторинг:** монолит bot.py (3413 строк) → 6 модулей |
| 41ab3df | Аудит багфиксов: logger, queue count, corrupted text |
| 65d2ab3 | AI-чат: отслеживание медиа-покупок, антиповтор, контроль ролеплея |
| 533d722 | Повышены пороги алертов p95 (10s warn / 15s critical) |
| b1a8fff | Повышен порог латентности Redis (200ms/500ms) |
| 2b394ce | Мониторинг, двухфазный поиск, rate limits, AI budget cap |
| b48b1a3 | Система модерированных публикаций в канал |

## Important Patterns & Gotchas

- **Circular import guard**: `matching.py` → `chat.py` связь идёт только через callback, зарегистрированный в `bot.py`. Не добавляй прямых импортов между роутерами.
- **Redis fallback**: всегда оборачивай Redis-операции в `if _use_redis:` + `try/except Exception`.
- **Lua scripts**: не меняй `PAIR_SCRIPT`/`UNPAIR_SCRIPT` без понимания atomicity — race conditions в матчинге критичны.
- **Locales**: `locales.py` — 143KB. Дублирование ключей вызывало баги (исправлено в e451729). При добавлении ключей проверяй все 3 языка.
- **AI characters**: `ai_characters.py` — 112KB. Каждый персонаж имеет подробный system prompt + конфиг медиа.
- **Energy accounting**: `ai_energy_used` сбрасывается ежедневно в `ai_messages_reset`. `bonus_energy` не сбрасывается (до капа 500).
- **admin_bot**: отдельный процесс, общается с main bot через таблицу `bot_stats` в PostgreSQL.
