# Спецификация: Перенос админ-панели в channel_bot (Admin Bot)

**Приоритет:** P1 | **Автор:** Архитектор | **Дата:** 2026-04-03

---

## 1. Текущая архитектура

```
┌─────────────────────────────────────────────────┐
│              bot.py (основной бот)               │
│  BOT_TOKEN                                       │
│  ├── admin.py (Router) ←── moderation.py         │
│  │    ├── /admin панель                          │
│  │    ├── Жалобы + AI модерация                  │
│  │    ├── Управление юзерами                     │
│  │    ├── Аналитика, аудит, маркетинг            │
│  │    └── Background tasks (4 шт)                │
│  ├── ai_chat.py (Router)                         │
│  ├── energy_shop.py (Router)                     │
│  └── In-memory state:                            │
│       active_chats, ai_sessions, waiting_*,      │
│       chat_logs, last_msg_time, mutual_likes     │
└───────────────────┬─────────────────────────────┘
                    │ PostgreSQL (общая БД)
┌───────────────────┴─────────────────────────────┐
│           channel_bot.py (отдельный бот)         │
│  CHANNEL_BOT_TOKEN                               │
│  ├── Авто-постинг в @MATCHMEHUB                  │
│  ├── Claude API генерация контента               │
│  └── Читает bot_stats из общей БД                │
└─────────────────────────────────────────────────┘
```

**Проблема:** admin.py внутри основного бота — это 1585 строк, которые:
- Утяжеляют основной бот (больше хэндлеров, больше memory)
- Зависят от in-memory state (active_chats, ai_sessions) для real-time метрик
- Не масштабируются: рестарт основного бота = потеря админ-панели

---

## 2. Целевая архитектура

```
┌─────────────────────────────────────────────────┐
│              bot.py (основной бот)               │
│  BOT_TOKEN                                       │
│  ├── ai_chat.py, energy_shop.py                  │
│  ├── moderation.check_message() (real-time)      │
│  ├── inactivity_checker() (требует active_chats) │
│  └── In-memory state (active_chats, queues...)   │
│       │                                          │
│       └── Пишет в bot_stats каждые 60с           │
└───────────────────┬─────────────────────────────┘
                    │ PostgreSQL (общая БД)
                    │ bot_stats: online_pairs,
                    │   searching_count, ai_sessions_count,
                    │   queue_details
┌───────────────────┴─────────────────────────────┐
│     admin_bot.py (бывший channel_bot.py)         │
│  CHANNEL_BOT_TOKEN                               │
│  ├── channel/ (автопостинг — как есть)           │
│  ├── admin/  (панель, юзеры, аналитика)          │
│  ├── moderation/ (жалобы, AI-ревью, аудит)       │
│  └── Background tasks:                           │
│       ├── winback_task()                         │
│       ├── reminder_task()                        │
│       └── streak_and_ai_push_task()              │
└─────────────────────────────────────────────────┘
```

---

## 3. Классификация данных: DB vs In-Memory

### 3.1. Данные, доступные напрямую из БД (переносятся без проблем)

| Данные | Таблица | Используется в |
|--------|---------|---------------|
| Статистика юзеров (всего, premium, баны) | `users` | admin:stats |
| Retention D1/D7/D30 | `users` (created_at, last_seen) | admin:retention |
| Жалобы | `complaints_log` | admin:complaints |
| Аудит-лог | `complaints_log` (reviewed=true) | admin:audit |
| Поиск юзера по ID | `users` | admin:find |
| Управление юзерами (бан/разбан/warn) | `users` | uadm:* |
| Медиа персонажей | `ai_character_media` | admin:char_media |
| AI история | `ai_history` | streak_and_ai_push_task |
| Premium expiry | `users` (premium_until) | winback_task |

**Вердикт:** 90% админки работает с БД напрямую. Переносится без изменений.

### 3.2. Данные, требующие in-memory state (проблемные)

| Данные | Переменная в bot.py | Где используется |
|--------|---------------------|-----------------|
| Онлайн пары | `active_chats` (dict) | admin:stats, admin:online |
| Юзеры в поиске | `waiting_*` (7 sets) | admin:online |
| AI сессии | `ai_sessions` (dict) | admin:online |
| Кик юзера из чата | `active_chats.pop()` | uadm:kick |
| Автозавершение чатов | `active_chats`, `last_msg_time` | inactivity_checker |
| Отправка топиков в чат | `active_chats`, `chat_logs` | inactivity_checker |

---

## 4. Решение для real-time данных

### Подход: расширение таблицы `bot_stats` (рекомендуемый)

Сейчас `inactivity_checker()` уже пишет в `bot_stats` каждые 60 секунд:
```python
# admin.py:1084-1096 (внутри inactivity_checker)
INSERT INTO bot_stats (key, value) VALUES ('online_pairs', ...)
INSERT INTO bot_stats (key, value) VALUES ('searching_count', ...)
```

**Расширяем** набор метрик, которые bot.py пушит в `bot_stats`:

```sql
-- Новые ключи в bot_stats:
'online_pairs'      -- уже есть (active_chats // 2)
'searching_count'   -- уже есть (сумма всех очередей)
'ai_sessions_count' -- НОВЫЙ: len(ai_sessions)
'queue_details'     -- НОВЫЙ: JSON с разбивкой по очередям
'active_uids'       -- НОВЫЙ: JSON список uid в active_chats (для кика)
```

**Admin Bot читает эти метрики из БД** — задержка максимум 60 секунд. Для админки это приемлемо.

### Кик юзера (uadm:kick) — особый случай

Кик требует **модификации** in-memory state основного бота. Варианты:

**Вариант A (рекомендуемый): Таблица команд**
```sql
CREATE TABLE admin_commands (
    id         SERIAL PRIMARY KEY,
    command    TEXT NOT NULL,        -- 'kick', 'force_disconnect'
    target_uid BIGINT NOT NULL,
    params     JSONB DEFAULT '{}',
    status     TEXT DEFAULT 'pending',  -- pending / executed / failed
    created_at TIMESTAMP DEFAULT NOW(),
    executed_at TIMESTAMP
);
```

1. Admin Bot записывает команду: `INSERT INTO admin_commands (command, target_uid) VALUES ('kick', 12345)`
2. bot.py в `inactivity_checker()` (каждые 60с) проверяет pending команды и исполняет
3. Обновляет `status = 'executed'`
4. Admin Bot опционально проверяет статус

**Задержка:** до 60 секунд. Для кика — приемлемо.

**Вариант B (отброшен): HTTP API в bot.py** — оверинжиниринг, требует aiohttp server, порт, auth.
**Вариант C (отброшен): Redis pub/sub** — новая зависимость, оверкилл для 1-2 команд.

---

## 5. Background tasks — куда переносить

| Задача | Требует in-memory? | Куда |
|--------|-------------------|------|
| `inactivity_checker()` | **ДА** (active_chats, last_msg_time, chat_logs) | **Остаётся в bot.py** |
| `reminder_task()` | Нет (только DB reads + bot.send_message) | **Переносится в Admin Bot** |
| `winback_task()` | Нет (только DB reads + bot.send_message) | **Переносится в Admin Bot** |
| `streak_and_ai_push_task()` | Нет (только DB reads + bot.send_message) | **Переносится в Admin Bot** |

**Важно:** `reminder_task`, `winback_task`, `streak_and_ai_push_task` отправляют сообщения юзерам **через основной бот** (BOT_TOKEN). После переноса они будут отправлять через **Admin Bot** (CHANNEL_BOT_TOKEN).

**Проблема:** Юзеры привыкли получать сообщения от основного бота. Сообщения от другого бота могут путать.

**Решение:** Использовать **основной BOT_TOKEN для отправки**. Admin Bot создаёт второй экземпляр бота:
```python
main_bot = Bot(token=os.environ["BOT_TOKEN"])      # для отправки юзерам
admin_bot = Bot(token=os.environ["CHANNEL_BOT_TOKEN"])  # для админ-интерфейса
```
Background tasks используют `main_bot.send_message()`.

---

## 6. Модерация — что переносить

### check_message() — ОСТАЁТСЯ в bot.py

Вызывается **в реальном времени** при каждом сообщении в чате (bot.py:2181). Задержка недопустима.

```
Юзер шлёт сообщение → bot.py:Chat.chatting handler → moderation.check_message()
```

Эта функция — часть hot path основного бота.

### ai_review_complaint() + жалобы UI — ПЕРЕНОСИТСЯ в Admin Bot

Жалобы — это асинхронный процесс: юзер жалуется → AI анализирует → админ решает. Задержка не критична.

**Поток после миграции:**
1. Юзер нажимает "Пожаловаться" в основном боте
2. bot.py записывает жалобу в `complaints_log` (как сейчас)
3. Admin Bot подхватывает pending жалобы (через polling или при открытии admin:complaints)
4. AI ревью + админ-интерфейс — в Admin Bot

### Разделение moderation.py

```
moderation.py (остаётся в bot.py):
  - check_message()          # real-time проверка
  - HARD_BAN_WORDS           # списки стоп-слов
  - SUSPECT_WORDS
  - init(bot, pool, admin_id)

moderation_admin.py (новый файл в Admin Bot):
  - ai_review_complaint()    # AI анализ жалоб
  - _apply_decision()        # применение решений
  - _escalate_to_admin()     # эскалация
  - get_audit_log()          # аудит-лог
  - format_audit_entry()     # форматирование
```

---

## 7. Структура файлов Admin Bot

```
admin_bot/
├── main.py                    # Точка входа, dispatcher, startup
├── config.py                  # Env vars, constants
├── db.py                      # Общий DB pool + helpers
│
├── channel/
│   ├── __init__.py
│   ├── router.py              # Хэндлеры канала (из channel_bot.py)
│   ├── content.py             # Генераторы контента (Claude API)
│   └── scheduler.py           # Расписание постинга
│
├── admin/
│   ├── __init__.py
│   ├── router.py              # /admin, stats, retention, find, online
│   ├── users.py               # uadm:* хэндлеры (бан, разбан, kick, premium)
│   ├── media.py               # Медиа персонажей (charmedia:*, cmview:*, cmdel:*)
│   └── marketing.py           # Маркетинг, рассылки
│
├── moderation/
│   ├── __init__.py
│   ├── router.py              # cadm:* хэндлеры (действия по жалобам)
│   ├── ai_review.py           # ai_review_complaint, _apply_decision
│   └── audit.py               # audit:* хэндлеры, get_audit_log
│
├── tasks/
│   ├── __init__.py
│   ├── winback.py             # winback_task()
│   ├── reminders.py           # reminder_task()
│   └── streaks.py             # streak_and_ai_push_task()
│
└── utils/
    ├── __init__.py
    └── bot_commands.py         # Polling admin_commands таблицы (для кика)
```

**Итого:** ~15 файлов вместо 1 монолита в 1585 строк.

---

## 8. Система ролей

Сейчас один `ADMIN_ID`. Рекомендую расширить до 3 ролей:

| Роль | Доступ | Кто |
|------|--------|-----|
| **owner** | Всё + удаление юзеров + маркетинг рассылки | Основатель (ADMIN_ID) |
| **admin** | Статистика + жалобы + бан/разбан + медиа | Доверенные люди |
| **moderator** | Только жалобы + предупреждения (без бана > 24ч) | Модераторы сообщества |

**Таблица:**
```sql
CREATE TABLE admin_roles (
    uid   BIGINT PRIMARY KEY,
    role  TEXT NOT NULL DEFAULT 'moderator',  -- owner / admin / moderator
    added_by BIGINT,
    added_at TIMESTAMP DEFAULT NOW()
);

-- Начальное значение:
INSERT INTO admin_roles (uid, role) VALUES (<ADMIN_ID>, 'owner');
```

**Проверка в хэндлерах:**
```python
async def require_role(uid, min_role):
    # owner > admin > moderator
    ROLE_LEVEL = {"moderator": 1, "admin": 2, "owner": 3}
    user_role = await get_admin_role(uid)
    if not user_role or ROLE_LEVEL[user_role] < ROLE_LEVEL[min_role]:
        return False
    return True
```

**Ограничения по ролям:**

| Действие | moderator | admin | owner |
|----------|-----------|-------|-------|
| Просмотр статистики | + | + | + |
| Просмотр жалоб | + | + | + |
| Предупреждение | + | + | + |
| Бан 3ч | + | + | + |
| Бан 24ч | - | + | + |
| Перманент бан | - | + | + |
| Shadow ban | - | + | + |
| Кик из чата | - | + | + |
| Premium выдать/убрать | - | + | + |
| Удаление юзера | - | - | + |
| Маркетинг рассылки | - | - | + |
| Управление ролями | - | - | + |
| Управление каналом | - | + | + |

---

## 9. Схема взаимодействия двух ботов

```
                    ЮЗЕР
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
   ┌──────────────┐      ┌───────────────┐
   │   bot.py     │      │  admin_bot/   │
   │  (основной)  │      │  main.py      │
   │              │      │               │
   │ Чаты, AI,    │      │ /admin панель │
   │ регистрация, │      │ Жалобы+AI     │
   │ платежи      │      │ Аналитика     │
   │              │      │ Канал постинг │
   │ check_msg()  │      │ Background    │
   │ inactivity() │      │ tasks (3 шт)  │
   └──────┬───────┘      └──────┬────────┘
          │                      │
          │   bot_stats (60s)    │ читает
          │──────────────────────│
          │   admin_commands     │ пишет
          │◄─────────────────────│
          │                      │
          └──────────┬───────────┘
                     │
              ┌──────┴──────┐
              │  PostgreSQL  │
              │  (общая БД)  │
              └─────────────┘
```

**Потоки данных:**
1. **bot.py → БД → admin_bot:** Статистика (bot_stats), жалобы (complaints_log), юзеры (users)
2. **admin_bot → БД → bot.py:** Команды кика (admin_commands), баны (users.ban_until)
3. **admin_bot → юзеры:** Background tasks через `main_bot` (BOT_TOKEN)

---

## 10. SQL миграции

```sql
-- Таблица команд от админ-бота к основному боту
CREATE TABLE admin_commands (
    id          SERIAL PRIMARY KEY,
    command     TEXT NOT NULL,
    target_uid  BIGINT NOT NULL,
    params      JSONB DEFAULT '{}',
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMP DEFAULT NOW(),
    executed_at TIMESTAMP
);
CREATE INDEX idx_admin_commands_status ON admin_commands (status) WHERE status = 'pending';

-- Таблица ролей
CREATE TABLE admin_roles (
    uid       BIGINT PRIMARY KEY,
    role      TEXT NOT NULL DEFAULT 'moderator',
    added_by  BIGINT,
    added_at  TIMESTAMP DEFAULT NOW()
);

-- Расширение bot_stats (новые ключи)
-- Не требует DDL — таблица key-value, просто добавляем новые ключи:
-- 'ai_sessions_count', 'queue_details', 'active_uids'
```

---

## 11. План миграции (порядок)

### Фаза 1: Подготовка инфраструктуры
1. Создать структуру `admin_bot/` с `main.py`, `config.py`, `db.py`
2. SQL миграция: `admin_commands`, `admin_roles`
3. Расширить `bot_stats` в `inactivity_checker()` — добавить ai_sessions_count, queue_details
4. Добавить в bot.py polling `admin_commands` (в inactivity_checker — уже бегает каждые 60с)

### Фаза 2: Перенос канала
5. Перенести channel_bot.py → `admin_bot/channel/` (рефакторинг в модули)
6. Проверить что автопостинг работает как раньше

### Фаза 3: Перенос админки (самое большое)
7. Перенести admin:stats, admin:retention, admin:find, admin:online → `admin_bot/admin/router.py`
8. Перенести uadm:* → `admin_bot/admin/users.py` (кик через admin_commands)
9. Перенести charmedia:* → `admin_bot/admin/media.py`
10. Перенести маркетинг → `admin_bot/admin/marketing.py`

### Фаза 4: Перенос модерации
11. Разделить moderation.py → оставить check_message() в bot.py
12. Перенести ai_review_complaint + UI жалоб → `admin_bot/moderation/`
13. Перенести аудит-лог → `admin_bot/moderation/audit.py`

### Фаза 5: Перенос background tasks
14. Перенести reminder_task → `admin_bot/tasks/reminders.py`
15. Перенести winback_task → `admin_bot/tasks/winback.py`
16. Перенести streak_and_ai_push_task → `admin_bot/tasks/streaks.py`
17. Настроить main_bot (BOT_TOKEN) для отправки сообщений юзерам

### Фаза 6: Очистка
18. Удалить admin.py из основного бота
19. Удалить admin_module Router из bot.py
20. Удалить channel_bot.py (заменён admin_bot/)
21. Добавить систему ролей

**Между фазами — тестирование.** Откат возможен на любом этапе.

---

## 12. Риски

| Риск | Уровень | Митигация |
|------|---------|-----------|
| Задержка кика до 60с | Низкий | Приемлемо для админ-операций. Можно уменьшить интервал polling до 10с |
| Background tasks отправляют от другого бота | Средний | Использовать main_bot (BOT_TOKEN) для юзер-уведомлений |
| Два бота — два деплоя | Низкий | Docker compose, одна команда запуска |
| bot_stats не обновился (бот упал) | Низкий | Добавить `updated_at` в bot_stats, показывать "данные устарели" если > 5 мин |
| Жалоба подана, но AI ревью в другом боте | Низкий | complaints_log в общей БД, admin_bot проверяет при открытии |
| Большой рефакторинг | Высокий | Поэтапная миграция (6 фаз), каждая фаза независимо тестируется |

---

## 13. Что НЕ переносится (остаётся в bot.py)

| Компонент | Причина |
|-----------|---------|
| `moderation.check_message()` | Real-time hot path, задержка недопустима |
| `inactivity_checker()` | Требует active_chats, last_msg_time, chat_logs |
| Запись жалоб в complaints_log | Инициируется юзером в основном боте |
| bot_stats writer | Часть inactivity_checker |
| admin_commands executor | Часть inactivity_checker (добавляется) |
