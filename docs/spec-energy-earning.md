# Спецификация: Новые способы заработка энергии

**Приоритет:** P2 | **Автор:** Архитектор | **Дата:** 2026-04-02

---

## 1. Выбранные механики (3 из N)

| Механика | Почему выбрана |
|----------|---------------|
| **A. Бонус за оценку чата** | Инфраструктура уже есть (`rate:{partner}:{stars}`, таблица `chat_ratings`). Минимум кода |
| **B. Ежедневные задания** | Повышает retention, создаёт привычку, направляет на нужное поведение |
| **C. Ачивки (одноразовые)** | Wow-эффект на первых сессиях, помогает онбордингу |

**Отброшены:** лидерборды (сложно, спорный ROI), "пригласи друга за энергию" (дублирует реферальную систему).

---

## 2. Механика A — Бонус за оценку чата

**Суть:** После завершения чата юзер видит звёзды (уже есть). Если оценил — получает +2 энергии.

**Баланс:**
- +2 энергии за оценку (любую, 1-5 звёзд)
- Лимит: макс 5 оценок/день = макс 10 энергии/день
- Cooldown: одна оценка на одного партнёра (уже есть — 60 сек защита)

**Защита от абьюза:**
- Нельзя оценить одного партнёра дважды за сессию (уже реализовано)
- Дневной лимит 5 оценок жёстко ограничивает фарм
- Мультиаккаунты: оценка возможна только после реального чата

**Изменения в БД:**
```sql
ALTER TABLE users ADD COLUMN rate_energy_today INTEGER DEFAULT 0;
```

**Интеграция:** В хэндлере `rate_chat` (bot.py:~2830-2857) — после вставки в `chat_ratings`:
```
if rate_energy_today < 5:
    ai_energy_used -= 2  (но не ниже 0)
    rate_energy_today += 1
    отправить "+2 за оценку!"
```

Сброс `rate_energy_today` вместе с `ai_energy_used` при ежедневном ресете (ai_chat.py:910-913).

---

## 3. Механика B — Ежедневные задания

**Суть:** 3 задания в день. Каждое = энергия. Все 3 = бонус сверху.

**Пул заданий (ротация — каждый день 3 из пула):**

| ID | Задание | Условие | Награда |
|----|---------|---------|---------|
| `chat_1` | Проведи 1 чат | total_chats +1 за день | +3 |
| `chat_3` | Проведи 3 чата | total_chats +3 за день | +5 |
| `rate_1` | Оцени чат | Любая оценка за день | +2 |
| `ai_msg` | Напиши AI-персонажу | 1 сообщение в AI чат | +2 |
| `like_1` | Поставь лайк | mutual_likes действие | +2 |

**Ежедневный набор:** 3 задания детерминистически на основе uid + дата:
```python
day_seed = (uid + date.today().toordinal()) % len(QUEST_POOL)
```

**Бонус за все 3:** +5 энергии сверху (итого до ~17/день от квестов).

**Новая таблица:**
```sql
CREATE TABLE daily_quests (
    uid        BIGINT  NOT NULL,
    quest_date DATE    NOT NULL DEFAULT CURRENT_DATE,
    quest_id   TEXT    NOT NULL,
    progress   INTEGER DEFAULT 0,
    goal       INTEGER NOT NULL DEFAULT 1,
    reward     INTEGER NOT NULL DEFAULT 2,
    claimed    BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (uid, quest_date, quest_id)
);
CREATE INDEX idx_daily_quests_uid_date ON daily_quests (uid, quest_date);
```

**Поле в users:**
```sql
ALTER TABLE users ADD COLUMN daily_bonus_claimed BOOLEAN DEFAULT FALSE;
```

**Интеграция:**
- `update_streak()` — генерирует 3 квеста в начале дня
- Хэндлеры чатов, оценок, AI — инкрементят progress
- Новая кнопка "Задания" в главном меню
- Claim автоматический при достижении goal
- Очистка старых записей в `streak_and_ai_push_task`: `DELETE FROM daily_quests WHERE quest_date < CURRENT_DATE - 7`

---

## 4. Механика C — Ачивки (одноразовые)

| ID | Название | Условие | Награда |
|----|----------|---------|---------|
| `first_chat` | Первый чат | total_chats >= 1 | +10 |
| `chats_10` | 10 чатов | total_chats >= 10 | +15 |
| `chats_50` | 50 чатов | total_chats >= 50 | +25 |
| `first_rate` | Первая оценка | Запись в chat_ratings | +5 |
| `first_ai` | Первый AI чат | Сообщение AI-персонажу | +5 |
| `streak_7` | Неделя подряд | streak_days >= 7 | +15 |
| `streak_30` | Месяц подряд | streak_days >= 30 | +30 |
| `first_like` | Первый лайк | mutual request отправлен | +5 |
| `mutual_match` | Взаимный матч | Успешный mutual match | +10 |

**Таблица:**
```sql
CREATE TABLE achievements (
    uid            BIGINT    NOT NULL,
    achievement_id TEXT      NOT NULL,
    unlocked_at    TIMESTAMP DEFAULT NOW(),
    energy_claimed BOOLEAN   DEFAULT FALSE,
    PRIMARY KEY (uid, achievement_id)
);
CREATE INDEX idx_achievements_uid ON achievements (uid);
```

**Проверка:** Функция `check_achievements(uid)` вызывается после стрика, оценки, чата, AI-сообщения.

---

## 5. Полная SQL миграция

```sql
-- Механика A: Бонус за оценку
ALTER TABLE users ADD COLUMN rate_energy_today INTEGER DEFAULT 0;

-- Механика B: Ежедневные задания
ALTER TABLE users ADD COLUMN daily_bonus_claimed BOOLEAN DEFAULT FALSE;

CREATE TABLE daily_quests (
    uid        BIGINT  NOT NULL,
    quest_date DATE    NOT NULL DEFAULT CURRENT_DATE,
    quest_id   TEXT    NOT NULL,
    progress   INTEGER DEFAULT 0,
    goal       INTEGER NOT NULL DEFAULT 1,
    reward     INTEGER NOT NULL DEFAULT 2,
    claimed    BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (uid, quest_date, quest_id)
);
CREATE INDEX idx_daily_quests_uid_date ON daily_quests (uid, quest_date);

-- Механика C: Ачивки
CREATE TABLE achievements (
    uid            BIGINT    NOT NULL,
    achievement_id TEXT      NOT NULL,
    unlocked_at    TIMESTAMP DEFAULT NOW(),
    energy_claimed BOOLEAN   DEFAULT FALSE,
    PRIMARY KEY (uid, achievement_id)
);
CREATE INDEX idx_achievements_uid ON achievements (uid);
```

---

## 6. Баланс экономики

| Источник | Free/день | Premium/день |
|----------|-----------|-------------|
| Базовый лимит | 30 | 200 |
| Стрик (макс) | +20 | +20 |
| Оценки (5x2) | +10 | +10 |
| Квесты (3+бонус) | ~+17 | ~+17 |
| **Итого/день** | **~77** | **~247** |
| Ачивки (разово) | ~120 всего | ~120 всего |

**Соотношение Free/Premium: 77/247 = 31%.** Premium дает 3.2x больше — мотивация к покупке сохраняется.

---

## 7. Порядок реализации

1. **Механика A** (оценка за энергию) — 1-2 часа, 1 поле, изменения только в rate_chat
2. **Ачивки** — 3-4 часа, новая таблица, хуки в 5 хэндлерах
3. **Квесты** — 4-6 часов, новая таблица, UI, генерация, хуки

---

## 8. Файлы для изменения

| Файл | Что менять |
|------|-----------|
| `bot.py` | init_db (новые таблицы), rate_chat хэндлер, update_streak, новая кнопка "Задания" |
| `ai_chat.py` | Ежедневный ресет — добавить rate_energy_today, daily_bonus_claimed |
| `db.py` | Новые функции: get_quests, increment_quest, check_achievements |
| `constants.py` | QUEST_POOL, ACHIEVEMENTS, RATE_ENERGY_REWARD, RATE_ENERGY_LIMIT |
| `keyboards.py` | Кнопка "Задания", клавиатура квестов |
| `locales.py` | Тексты квестов, ачивок, бонусов за оценку (ru/en/es) |
