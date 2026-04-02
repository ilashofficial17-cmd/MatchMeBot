# MatchMe Bot

Анонимный чат-бот для Telegram с ИИ-персонажами, системой матчинга и монетизацией через Telegram Stars.

---

## Содержание

- [Архитектура](#архитектура)
- [Файлы проекта](#файлы-проекта)
- [Переменные окружения](#переменные-окружения)
- [База данных](#база-данных)
- [Система энергии](#система-энергии)
- [Монетизация](#монетизация)
- [Локализация](#локализация)
- [FSM-состояния](#fsm-состояния)
- [Запуск](#запуск)
- [Правило для Claude](#правило-для-claude)

---

## Архитектура

```
Telegram API
    │
    ▼
bot.py  ←──────────────────────── точка входа, dp (Dispatcher)
    │                               все основные хендлеры
    ├── ai_chat.py                  ИИ чат, система энергии, персонажи
    ├── energy_shop.py              магазин энергии (покупка пакетов)
    ├── admin.py                    админ-панель, аналитика, рассылки
    ├── channel_bot.py              канальный бот (партнёрская реклама)
    ├── moderation.py               автомодерация сообщений
    │
    ├── keyboards.py                все клавиатуры (Reply + Inline)
    ├── locales.py                  тексты на ru / en / es
    ├── states.py                   FSM-состояния (aiogram)
    ├── constants.py                цены, планы, пакеты, стоп-слова
    ├── db.py                       вспомогательные DB-операции
    │
    ├── ai_characters.py            конфиги всех 13 ИИ-персонажей
    ├── ai_utils.py                 OpenRouter API (chat, vision, voice)
    │
    ├── legal_texts.py              юридические тексты (ToS, Privacy)
    └── telegraph_pages.py          публикация юридических страниц в Telegraph
```

---

## Файлы проекта

| Файл | Назначение | Изменять когда |
|------|-----------|----------------|
| `bot.py` | Точка входа, хендлеры сообщений/колбэков, платежи, поиск собеседника | Новые команды, хендлеры, изменения платёжного флоу |
| `ai_chat.py` | ИИ чат: выбор персонажа, обмен сообщениями, система энергии, vision, voice | Изменения поведения ИИ, системы энергии, тиров |
| `ai_characters.py` | Словарь `AI_CHARACTERS` — системные промпты, тиры, модели, max_tokens всех 13 персонажей | Добавление/изменение персонажей |
| `ai_utils.py` | `get_ai_chat_response()`, `describe_image()`, `transcribe_voice()` — обёртки над OpenRouter | Смена моделей, параметры запросов |
| `energy_shop.py` | Router для покупки энергии: показ магазина, инвойс, обработка платежа | Добавление пакетов, изменение флоу покупки |
| `keyboards.py` | Все клавиатуры: `kb_main`, `kb_ai_characters`, `kb_premium`, `kb_energy_shop`, и др. | Новые кнопки, изменение меню |
| `locales.py` | Все тексты бота: 3 языка (ru/en/es), ~2000 строк | Любые изменения текстов, новые ключи |
| `constants.py` | `PREMIUM_PLANS`, `ENERGY_PACKS`, `GIFTS`, `PRICE_MULTIPLIERS`, `STOP_WORDS`, уровни | Изменения цен, пакетов, планов |
| `states.py` | FSM-группы: Reg, Chat, LangSelect, Rules, AIChat, AdminState и др. | Новые состояния в диалоговых флоу |
| `db.py` | `get_user()`, `update_user()`, `increment_user()` и др. вспомогательные DB-функции | Новые поля в таблице users, новые запросы |
| `admin.py` | Админ-панель: статистика, баны, рассылки, аналитика когорт, управление медиа персонажей | Новые админ-команды, аналитика |
| `moderation.py` | Проверка сообщений на стоп-слова, автобан | Изменения правил модерации |
| `legal_texts.py` | Тексты ToS и Privacy Policy | Изменения юридических текстов |
| `telegraph_pages.py` | Публикация ToS/Privacy в Telegraph | Изменения процесса публикации |

---

## Переменные окружения

| Переменная | Обязательная | Описание |
|------------|-------------|---------|
| `BOT_TOKEN` | ✅ | Telegram Bot Token от @BotFather |
| `DATABASE_URL` | ✅ | PostgreSQL DSN (`postgresql://user:pass@host/db`) |
| `ADMIN_ID` | ✅ | Telegram user ID администратора |
| `OPENROUTER_API_KEY` | ✅ | API ключ OpenRouter (используется в ai_utils.py) |

---

## База данных

**СУБД:** PostgreSQL (asyncpg, pool 5–20 соединений)

### Ключевые поля таблицы `users`

| Поле | Тип | Описание |
|------|-----|---------|
| `uid` | bigint | Telegram user ID |
| `name` | text | Имя пользователя |
| `lang` | text | Язык: `ru` / `en` / `es` |
| `mode` | text | Режим поиска: `simple` / `flirt` / `kink` |
| `premium_tier` | text | `null` / `premium` |
| `premium_until` | text | ISO datetime или `"permanent"` |
| `ai_energy_used` | int | Накопленное потребление энергии за день |
| `ai_messages_reset` | timestamp | Момент последнего сброса счётчика энергии |
| `ai_bonus` | int | Постоянный бонус к дневному лимиту энергии |
| `ab_group` | text | A/B группа для ценовых тестов (`A` / `B`) |

---

## Система энергии

Каждое сообщение в ИИ чате тратит энергию. Энергия сбрасывается каждые 24 часа.

### Стоимость по тиру персонажа

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

### Логика (ai_chat.py)

```python
ENERGY_COST  = {"basic": 1, "vip": 2, "vip_plus": 3}
DAILY_ENERGY = {"free": 30, "premium": 200}

cost, max_energy = get_energy_info(char_tier, user_tier, ai_bonus)
# Проверка: energy_used + cost > max_energy → показать ai_energy_empty с таймером
# После ответа: UPDATE users SET ai_energy_used = energy_used + cost
# Сброс: если (now - ai_messages_reset) > 86400s → ai_energy_used = 0
```

---

## Монетизация

Все платежи — Telegram Stars (`currency="XTR"`). `pre_checkout_query` всегда `ok=True`.

### Premium

Определено в `constants.py → PREMIUM_PLANS`:

| Ключ | Дней | Цена (ru) | Цена (en) |
|------|------|-----------|-----------|
| `7d` | 7 | 129 ⭐ | 258 ⭐ |
| `1m` | 30 | 349 ⭐ | 698 ⭐ |
| `3m` | 90 | 749 ⭐ | 1498 ⭐ |

### Пакеты энергии

Определено в `constants.py → ENERGY_PACKS`. Покупка вычитает `amount` из `ai_energy_used`:

| Ключ | Энергия | Цена (ru) | Цена (en) |
|------|---------|-----------|-----------|
| `e30` | 30 ⚡ | 49 ⭐ | 98 ⭐ |
| `e100` | 100 ⚡ | 129 ⭐ | 258 ⭐ |
| `e300` | 300 ⚡ | 299 ⭐ | 598 ⭐ |

### Региональные мультипликаторы

```python
PRICE_MULTIPLIERS = {"ru": 1.0, "es": 1.3, "en": 2.0}
```

### Платёжный флоу

```
callback "buy:{plan}"         → bot.send_invoice(payload="premium_{plan}")
callback "energy_buy:{pack}"  → bot.send_invoice(payload="energy_{pack}")
pre_checkout_query             → answer(ok=True)
successful_payment             → обработка по payload prefix:
                                  "gift_"    → _handle_gift_payment()
                                  "energy_"  → ai_energy_used -= amount
                                  "premium_" → update premium_until
```

---

## Локализация

Все тексты в `locales.py`. Структура:

```python
TEXTS = {
    "ru": { "key": "текст {param}", ... },
    "en": { "key": "text {param}", ... },
    "es": { "key": "texto {param}", ... },
}

def t(lang: str, key: str, **kwargs) -> str:
    # Возвращает текст с подставленными параметрами
```

**Правило:** при добавлении любого нового текста — добавить ключ во все 3 языка (`ru`, `en`, `es`).

---

## FSM-состояния

Определены в `states.py`:

| Группа | Назначение |
|--------|-----------|
| `Reg` | Регистрация профиля (name → age → gender → mode → interests) |
| `Chat` | Живой анонимный чат |
| `AIChat` | ИИ чат (choosing → chatting) |
| `LangSelect` | Выбор языка |
| `Rules` | Принятие правил |
| `Complaint` | Жалоба на пользователя |
| `EditProfile` | Редактирование профиля |
| `ResetProfile` | Сброс профиля |
| `AdminState` | Состояния в админ-панели |

---

## Запуск

```bash
pip install aiogram asyncpg aiohttp

export BOT_TOKEN="..."
export DATABASE_URL="postgresql://..."
export ADMIN_ID="..."
export OPENROUTER_API_KEY="..."

python bot.py
```

---

## Правило для Claude

> **При любом изменении кода обновлять этот README в том же коммите.**

| Что изменилось | Что обновить в README |
|---------------|----------------------|
| Добавлен / удалён `.py` файл | Таблица [Файлы проекта](#файлы-проекта) |
| Изменены лимиты или стоимость энергии | Раздел [Система энергии](#система-энергии) |
| Изменены цены, добавлены планы/пакеты | Раздел [Монетизация](#монетизация) |
| Новая переменная окружения | Таблица [Переменные окружения](#переменные-окружения) |
| Новые FSM-состояния | Таблица [FSM-состояния](#fsm-состояния) |
| Новые поля в БД | Таблица [База данных](#база-данных) |
| Изменена архитектура / зависимости между файлами | Схема [Архитектура](#архитектура) |

README в `main` должен всегда отражать реальное состояние кода.
