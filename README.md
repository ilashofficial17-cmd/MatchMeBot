# MatchMe Bot

Анонимный чат-бот для Telegram с ИИ-персонажами, системой матчинга, Redis-состоянием, мониторингом и монетизацией через Telegram Stars.

---

## Содержание

- [Архитектура](#архитектура)
- [Файлы проекта](#файлы-проекта)
- [Переменные окружения](#переменные-окружения)
- [Redis](#redis)
- [База данных](#база-данных)
- [Мониторинг](#мониторинг)
- [ИИ-персонажи](#ии-персонажи)
- [Система энергии](#система-энергии)
- [Монетизация](#монетизация)
- [Поиск собеседника](#поиск-собеседника)
- [Локализация](#локализация)
- [FSM-состояния](#fsm-состояния)
- [Admin Bot](#admin-bot)
- [Запуск](#запуск)

---

## Архитектура

Основной бот разбит на 6 Router-модулей (aiogram 3), связанных через dependency injection (`init()`):

```
Telegram API
    │
    ▼
bot.py  ←─────────────────── точка входа: Dispatcher, DB/Redis pool, cleanup, main()
    │   │
    │   ├── registration.py       /start, onboarding, согласие, Reg FSM-поток
    │   ├── matching.py           do_find, /find, отмена поиска, двухфазный поиск
    │   ├── chat.py               relay сообщений, end_chat, mutual match, жалобы, гифты, rate
    │   ├── profile.py            /profile, /stats, /settings, /edit, /help, quests, energy, referral
    │   └── payments.py           /premium, trial, buy, pre_checkout, successful_payment
    │
    ├── ai_chat.py                  ИИ чат: персонажи, энергия, memory, vision, voice
    ├── ai_utils.py                 OpenRouter API: chat, vision, voice, budget cap
    ├── ai_characters.py            13 ИИ-персонажей (промпты, тиры, модели)
    ├── energy_shop.py              магазин энергии (Telegram Stars)
    │
    ├── redis_state.py              Redis: очереди, чаты, AI-сессии, Lua scripts
    ├── monitoring.py               метрики, алерты, rate limiting, дашборд
    │
    ├── keyboards.py                все клавиатуры (Reply + Inline)
    ├── locales.py                  тексты на ru / en / es (~500 ключей × 3 языка)
    ├── states.py                   FSM-состояния (aiogram 3)
    ├── constants.py                цены, лимиты, rate limits, стоп-слова
    ├── db.py                       вспомогательные DB-операции
    ├── moderation.py               автомодерация сообщений
    │
    ├── admin.py                    админ-панель основного бота
    ├── legal_texts.py              юридические тексты (ToS, Privacy)
    └── telegraph_pages.py          публикация в Telegraph
    
admin_bot/                          ── отдельный бот для канала и админки ──
    ├── config.py                   конфигурация (токены, расписание)
    ├── db.py                       DB-операции админ-бота
    ├── keyboards.py                клавиатуры админ-бота
    ├── admin/                      управление юзерами, рассылки, маркетинг
    ├── channel/                    автопостинг, модерируемые посты, изображения
    ├── moderation/                 AI-ревью жалоб
    ├── support/                    обработка обращений
    └── tasks/                      фоновые задачи (ремайндеры, стрики, winback)

funnel_bots/                        ── рекламные воронки ──
    ├── ai_demo_bot.py              демо AI-чата с Мией
    └── anon_chat_bot.py            промо анонимного чата
```

---

## Файлы проекта

### Основной бот (6 Router-модулей)

| Файл | Строк | Назначение |
|------|-------|-----------|
| `bot.py` | 1157 | Точка входа: `init_db()`, DB/Redis pool, DB-хелперы (`get_user`, `update_user`, `is_premium`), cleanup background tasks, error_handler, `main()` wiring всех роутеров через `init()` |
| `registration.py` | 704 | `/start`, onboarding, согласие с правилами, `needs_onboarding()`, Reg FSM-флоу (name → age → gender → mode → interests) |
| `matching.py` | 647 | `do_find()` — двухфазный поиск (Redis + DB batch), `anon_search`, `/find`, `cancel_search`, `notify_no_partner`, `_MODE_CHARS` |
| `chat.py` | 979 | Relay сообщений между партнёрами, `end_chat`, mutual match, жалобы, рейтинг, гифты, stop-words модерация |
| `profile.py` | 728 | `/profile`, `/stats`, `/settings`, `/edit`, `/help`, квесты, энергия, рефералы, `/reset`, выбор языка, правила |
| `payments.py` | 367 | Triаl Premium, `/premium`, `buy_premium`, `pre_checkout`, `successful_payment`, gift-платежи, energy-пакеты |

**Итого:** 4582 строк (было ~3413 в монолитном `bot.py`)

### Dependency Injection

Все модули следуют единому паттерну:

```python
# в модуле:
router = Router()
_bot = None
_db_pool = None
# ... другие глобальные зависимости

def init(*, bot, db_pool, use_redis, ...):
    global _bot, _db_pool, ...
    _bot = bot
    _db_pool = db_pool
    # ...

# в bot.py main():
import chat, matching, registration, profile, payments
chat.init(bot=bot, db_pool=db_pool, ...)
matching.init(bot=bot, db_pool=db_pool, ...)
# ...
dp.include_router(registration.router)
dp.include_router(matching.router)
dp.include_router(chat.router)
dp.include_router(profile.router)
dp.include_router(payments.router)
```

**Циркулярные зависимости** (chat↔matching, registration→matching) разрешаются пост-инициализацией через `set_do_find(fn)`.

### Вспомогательные модули

| Файл | Назначение |
|------|-----------|
| `ai_chat.py` | ИИ чат: выбор персонажа, обмен сообщениями, энергия, memory, vision (~1300 строк) |
| `ai_characters.py` | 13 персонажей: системные промпты, тиры, модели, max_tokens |
| `ai_utils.py` | OpenRouter API: `get_ai_chat_response()`, `describe_image()`, `transcribe_voice()`, `summarize_conversation()`, budget cap |
| `redis_state.py` | Redis: 22 функции, 3 Lua-скрипта (pairing, unpairing, mutual), AI memory, retry policy |
| `monitoring.py` | `MetricsCollector`, `MetricsMiddleware`, `monitoring_task`, `alert_checker`, `openrouter_health_probe`, `check_rate_limit`, `format_dashboard` |
| `energy_shop.py` | Router магазина энергии: показ, инвойс, обработка платежа |
| `keyboards.py` | Все клавиатуры: `kb_main`, `kb_ai_characters`, `kb_premium`, `kb_energy_shop` и др. |
| `locales.py` | Все тексты: 3 языка (ru/en/es), ~500 ключей на язык |
| `constants.py` | `PREMIUM_PLANS`, `ENERGY_PACKS`, `GIFTS`, `RATE_LIMITS`, `PRICE_MULTIPLIERS`, уровни |
| `states.py` | FSM-группы: Reg, Chat, AIChat, LangSelect, Rules, Complaint и др. |
| `db.py` | `get_user()`, `update_user()`, `increment_user()` и вспомогательные DB-функции |
| `admin.py` | Админ-панель: статистика, баны, рассылки, когортная аналитика |
| `moderation.py` | Проверка на стоп-слова, автобан |
| `legal_texts.py` | Юридические тексты (ToS, Privacy Policy) |
| `telegraph_pages.py` | Публикация юридических страниц в Telegraph |
| `migrate_interests.py` | Одноразовая миграция интересов |

---

## Переменные окружения

| Переменная | Обязательная | Описание |
|------------|-------------|---------|
| `BOT_TOKEN` | ✅ | Telegram Bot Token от @BotFather |
| `DATABASE_URL` | ✅ | PostgreSQL DSN (`postgresql://user:pass@host/db`) |
| `ADMIN_ID` | ✅ | Telegram user ID администратора |
| `OPEN_ROUTER` | ✅ | API ключ OpenRouter (AI чат, модерация, канал) |
| `REDIS_URL` | Рекомендуется | Redis URL (`redis://...`). Без неё — fallback на in-memory |
| `CHANNEL_BOT_TOKEN` | Для канала | Токен бота канала @MATCHMEHUB |
| `ANTHROPIC_API_KEY` | Опционально | Ключ Anthropic (резерв) |
| `VENICE_API_KEY` | Опционально | Ключ Venice AI (резерв) |
| `CHANNEL_IMAGE_ENABLED` | Опционально | `"1"` / `"0"` — генерация изображений для канала (по умолчанию вкл) |
| `AI_HOURLY_LIMIT` | Опционально | Лимит AI-запросов в час (по умолчанию 500) |

---

## Redis

**Библиотека:** `redis.asyncio` с retry policy (ExponentialBackoff, 3 retries)

### Конфигурация пула

```python
max_connections=30, retry_on_timeout=True,
socket_timeout=5, socket_connect_timeout=5, health_check_interval=30
```

### Схема ключей

| Ключ | Тип | TTL | Назначение |
|------|-----|-----|-----------|
| `mm:chat:active:{uid}` | string (partner_uid) | — | Активные чат-пары |
| `mm:queue:{mode}:{premium}` | set | — | Очереди поиска (7 ключей) |
| `mm:chat:lastmsg:{uid}` | string (timestamp) | 600с | Время последнего сообщения |
| `mm:chat:log:{key}` | list | 3600с | Логи чата для модерации |
| `mm:ai:session:{uid}` | hash | 1800с | AI-сессия (character, history, msg_count) |
| `mm:mutual:likes:{uid}` | string | 600с | Взаимные лайки |
| `mm:memory:{uid}:{char}` | string | 30д | Долгосрочная память AI-персонажа |
| `mm:facts:{uid}:{char}` | string (JSON list) | 30д | Факты о пользователе для AI |
| `mm:ratelimit:{action}:{uid}` | sorted set | window+10с | Rate limiting |

### Lua-скрипты (атомарные операции)

- **PAIR_SCRIPT** — спаривание: убрать из очереди + добавить в active_chats
- **UNPAIR_SCRIPT** — отключение: удалить обоих из active_chats
- **MUTUAL_SCRIPT** — взаимные лайки: атомарная проверка + удаление

### Fallback

Если `REDIS_URL` не задан — бот работает с `MemoryStorage` и Python dict'ами. Все Redis-операции обёрнуты в `if _use_redis:` проверки.

---

## База данных

**СУБД:** PostgreSQL (asyncpg, pool min=5, max=20, command_timeout=10s)

### Ключевые таблицы

| Таблица | Назначение |
|---------|-----------|
| `users` | Профили пользователей (~50 полей) |
| `chat_ratings` | Оценки собеседников (stars 1-5) |
| `ai_character_media` | Медиа-файлы персонажей (gif, photo, blurred, hot) |
| `ai_chat_history` | Персистентная история AI-чатов |
| `ai_notes` | Заметки AI-персонажей о пользователях |
| `achievements` | Ачивки пользователей |
| `daily_quests` | Ежедневные задания |
| `complaints` | Жалобы |
| `bot_stats` | Статистика бота (key-value) |

### Ключевые поля `users`

| Поле | Тип | Описание |
|------|-----|---------|
| `uid` | bigint PK | Telegram user ID |
| `name`, `age`, `gender` | text/int | Профиль |
| `lang` | text | Язык: `ru` / `en` / `es` |
| `mode` | text | Режим: `simple` / `flirt` / `kink` |
| `premium_tier` / `premium_until` | text | Подписка |
| `ai_energy_used` / `bonus_energy` | int | Система энергии |
| `level` / `total_chats` / `streak_days` | int | Прогресс |
| `search_gender` / `search_age_min` / `search_age_max` | text/int | Фильтры поиска |
| `shadow_ban` | bool | Теневой бан |
| `ab_group` | text | A/B группа (`A` / `B`) |

---

## Мониторинг

### MetricsCollector (in-memory)

Rolling window метрик за последние 60 минут (120 тиков по 30 сек):
- Response time (p95)
- Error rate (per min)
- Redis latency
- PG pool usage
- Memory RSS
- AI requests count

### Фоновые задачи

| Задача | Интервал | Описание |
|--------|----------|---------|
| `monitoring_task()` | 30 сек | Redis PING, PG pool stats, memory RSS, flush tick |
| `alert_checker()` | 60 сек | Проверка порогов → Telegram алерт админу |
| `openrouter_health_probe()` | 5 мин | GET /api/v1/models → ok/latency |

### Пороги алертов

| Метрика | Warning | Critical |
|---------|---------|----------|
| Redis latency | > 200ms | > 500ms / disconnect |
| PG pool | > 15/20 | 20/20 (exhausted) |
| Memory RSS | > 400 MB | > 500 MB |
| Error rate | > 5/мин | > 20/мин |
| p95 response | > 2000ms | > 5000ms |
| OpenRouter | — | DOWN |

### Rate Limiting

Redis sorted set sliding window (`check_rate_limit()`):

| Действие | Лимит | Окно |
|----------|-------|------|
| Поиск | 3 | 60 сек |
| AI сообщения | 10 | 60 сек |
| Жалобы | 3 | 300 сек |

### MetricsMiddleware

aiogram middleware для автоматического замера времени каждого хендлера и подсчёта ошибок.

---

## ИИ-персонажи

### 13 персонажей с тремя тирами

| Тир | Модель | Персонажи |
|-----|--------|-----------|
| `basic` | gpt-4o-mini | Луна, Макс, Мия, Кай |
| `vip` | gemini-flash / hermes-70b | Аврора, Алекс, Диана, Леон |
| `vip_plus` | hermes-405b | Лилит, Ева, Дамир, Арс, Мастер |

### AI Memory (долгосрочная)

- При завершении сессии (≥4 сообщений) → `summarize_conversation()` через Gemini Flash
- Summary + facts сохраняются в Redis (TTL 30 дней)
- При следующей сессии — memory подгружается в system prompt
- Кэширование в session hash (`_load_memory_cached()`) — экономит 2 Redis GET на сообщение
- Кнопка "Стереть память" — очищает и DB notes, и Redis memory

### Budget Control

- Hourly cap: 500 запросов/час (настраивается через `AI_HOURLY_LIMIT`)
- `budget_mode` параметр: при превышении бюджета → fallback на `google/gemini-flash-1.5`
- Token usage логируется из ответа OpenRouter

---

## Система энергии

Каждое сообщение в ИИ чате тратит энергию. Энергия сбрасывается каждые 24 часа.

### Стоимость по тиру

| Тир | Стоимость | Персонажи |
|-----|-----------|-----------|
| `basic` | 1 ⚡ | Луна, Макс, Мия, Кай |
| `vip` | 2 ⚡ | Аврора, Алекс, Диана, Леон |
| `vip_plus` | 3 ⚡ | Лилит, Ева, Дамир, Арс, Мастер |

### Дневные лимиты

| Подписка | Лимит |
|----------|-------|
| Free | 30 ⚡/день |
| Premium | 200 ⚡/день |

### Способы получения энергии

1. **Покупка** — Telegram Stars (магазин энергии)
2. **Оценка собеседника** — +2 bonus energy за каждую оценку
3. **Ежедневные квесты** — 3 задания в день с наградами
4. **Ачивки** — одноразовые награды за достижения
5. **Return gifts** — бонус энергии для вернувшихся пользователей

---

## Монетизация

Все платежи — Telegram Stars (`currency="XTR"`).

### Premium подписка

| Ключ | Дней | Цена (ru) | Цена (en) | Цена (es) |
|------|------|-----------|-----------|-----------|
| `7d` | 7 | 129 ⭐ | 258 ⭐ | 168 ⭐ |
| `1m` | 30 | 349 ⭐ | 698 ⭐ | 454 ⭐ |
| `3m` | 90 | 749 ⭐ | 1498 ⭐ | 974 ⭐ |

### Пакеты энергии

| Ключ | Энергия | Цена (ru) |
|------|---------|-----------|
| `e10` | 10 ⚡ | 29 ⭐ |
| `e50` | 50 ⚡ | 99 ⭐ |
| `e150` | 150 ⚡ | 249 ⭐ |

### Региональные мультипликаторы

```python
PRICE_MULTIPLIERS = {"ru": 1.0, "es": 1.3, "en": 2.0}
```

---

## Поиск собеседника

### Двухфазный поиск (оптимизация для масштабирования)

**Фаза 1 — Redis-фильтрация (без DB):**
- `SRANDMEMBER` — до 50 случайных кандидатов из очереди
- `pipeline EXISTS` — batch проверка кто уже в чате

**Фаза 2 — Batch DB-обогащение:**
- `SELECT * FROM users WHERE uid = ANY($1::bigint[])` — один запрос вместо N
- Фильтрация: пол, возраст, язык, режим, shadow ban, интересы

**Результат:** 1000 чел в очереди → ~20ms (вместо ~2000ms при O(N) подходе)

### Фильтры

- Пол (search_gender)
- Возрастной диапазон (search_age_min/max)
- Языковой регион (search_range: local/global)
- Режим (simple/flirt/kink + cross-mode для flirt↔kink)
- Shadow ban изоляция
- Premium приоритет в сортировке

---

## Локализация

Все тексты в `locales.py`. Три языка: `ru`, `en`, `es`.

```python
TEXTS = {
    "ru": { "key": "текст {param}", ... },  # ~510 ключей
    "en": { "key": "text {param}", ... },    # ~510 ключей
    "es": { "key": "texto {param}", ... },   # ~508 ключей
}

def t(lang: str, key: str, **kwargs) -> str
```

### Мультиязычный матчинг кнопок

```python
def _all(key):
    """Все языковые варианты для ключа — защита от смены языка."""
    return {TEXTS[lang][key] for lang in TEXTS if key in TEXTS[lang]}
```

Используется в `ai_chat.py` для проверки нажатий кнопок: `if txt in _all("btn_end_ai_chat")` вместо `if txt == t(lang, "btn_end_ai_chat")`.

---

## FSM-состояния

Определены в `states.py`:

| Группа | Состояния | Назначение |
|--------|-----------|-----------|
| `Reg` | name → age → gender → mode → interests | Регистрация профиля |
| `Chat` | chatting | Живой анонимный чат |
| `AIChat` | choosing → chatting | ИИ чат |
| `LangSelect` | selecting | Выбор языка |
| `Rules` | accept | Принятие правил |
| `Complaint` | reason | Жалоба на пользователя |
| `EditProfile` | name / age / gender и др. | Редактирование профиля |
| `ResetProfile` | confirm | Сброс профиля |
| `AdminState` | broadcast / edit_stopwords и др. | Админ-панель |

---

## Admin Bot

Отдельный процесс (`admin_bot/`) для канала @MATCHMEHUB и административных задач.

### Модули

| Модуль | Назначение |
|--------|-----------|
| `admin/router.py` | Управление юзерами, статистика, баны |
| `admin/broadcast.py` | Рассылки |
| `admin/marketing.py` | Маркетинговые инструменты |
| `admin/media.py` | Управление медиа AI-персонажей |
| `channel/content.py` | Генераторы контента (советы, шутки, истории, опросы) |
| `channel/scheduler.py` | Расписание автопостинга + модерируемые посты |
| `channel/router.py` | Хендлеры модерации постов (approve/regen/edit/dismiss) |
| `moderation/ai_review.py` | AI-ревью жалоб |
| `tasks/reminders.py` | Напоминания неактивным |
| `tasks/streaks.py` | Стрики и ежедневные награды |
| `tasks/winback.py` | Return gifts для вернувшихся |

### Модерируемые посты

Два режима публикации на канал (per-rubric):
- **auto** — пост публикуется сразу
- **moderated** — превью в админку → approve / regen / edit / dismiss

### Генерация изображений

FLUX.2 Pro через OpenRouter для рубрик: chat_story, hot_take, night_vibe.

---

## Запуск

### Зависимости

```bash
pip install aiogram asyncpg aiohttp redis
```

### Переменные окружения

```bash
export BOT_TOKEN="..."
export DATABASE_URL="postgresql://..."
export ADMIN_ID="..."
export OPEN_ROUTER="..."
export REDIS_URL="redis://..."  # опционально, но рекомендуется
```

### Запуск

```bash
python bot.py
```

Бот автоматически:
1. Создаёт таблицы PostgreSQL (если не существуют)
2. Подключается к Redis (если `REDIS_URL` задан) или использует in-memory fallback
3. Запускает мониторинг (monitoring_task, alert_checker, openrouter_health_probe)
4. Регистрирует middleware (MetricsMiddleware)
5. Начинает polling

---

## Спецификации (docs/)

| Файл | Описание |
|------|---------|
| `spec-redis-migration.md` | Схема миграции in-memory → Redis |
| `spec-monitoring.md` | Архитектура мониторинга и алертов |
| `spec-scaling.md` | Анализ bottleneck'ов 10K-100K MAU |
| `spec-moderated-posts.md` | Авто vs модерируемые посты |
| `spec-bonus-energy.md` | Постоянная бонусная энергия |
| `spec-energy-earning.md` | Рейтинг, квесты, ачивки |
| `spec-return-gifts.md` | Return gifts (winback) |
| `spec-admin-bot.md` | Архитектура админ-бота |
| `financial-model.md` | Unit economics, LTV, cost projection |
