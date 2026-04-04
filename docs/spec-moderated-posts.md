# Спецификация: Модерируемые публикации в канал

**Приоритет:** P2 | **Автор:** Архитектор | **Дата:** 2026-04-04

---

## 1. Текущий flow

```
scheduler.channel_poster() (каждые 10 мин)
  → проверяет CHANNEL_SCHEDULE[hour]
  → content.generate_*() → текст
  → admin_bot.send_message(CHANNEL_ID, text)  ← сразу в канал
```

Ручной постинг уже имеет preview:
```
Админ → "📝 Создать пост" → выбирает рубрику
  → generate → preview в чат админа → кнопки ✅/🔄/❌
  → channel_preview_cache[msg_id] → публикация
```

**Задача:** Дать scheduler'у тот же flow с preview, что и у ручного постинга.

---

## 2. Два режима

| Режим | Flow | Когда использовать |
|-------|------|-------------------|
| **AUTO** | scheduler → generate → сразу в канал | Стабильные рубрики: daily_stats, peak_hour |
| **MODERATED** | scheduler → generate → preview админу → ✅/✏️/❌ | AI-генерируемые: dating_tip, joke, hot_take |

### Настройка: per-rubric (не глобальная)

Глобальное переключение — слишком грубо. Статистика не требует ревью, а шутки и советы — требуют.

**Конфигурация по умолчанию:**

```python
# admin_bot/config.py — добавить:
RUBRIC_MODE = {
    "daily_stats":  "auto",
    "peak_hour":    "auto",
    "dating_tip":   "moderated",
    "joke":         "moderated",
    "poll":         "auto",
    "weekly_recap": "moderated",
    "milestone":    "auto",
}
```

**Персистентность:** Хранить в `bot_stats` таблице:
```
key: "rubric_mode:{rubric}"
value: "auto" | "moderated"
```
При старте — если нет записи в bot_stats, берётся дефолт из RUBRIC_MODE.

---

## 3. Flow модерации

```
scheduler.channel_poster()
  │
  ├─ rubric mode == "auto"
  │   └─ generate → send_message(CHANNEL_ID) → done
  │
  └─ rubric mode == "moderated"
      └─ generate → create pending_post → send preview to ADMIN_ID
          │
          ├─ ✅ Опубликовать → send_message(CHANNEL_ID) → delete pending
          ├─ 🔄 Перегенерировать → generate заново → обновить preview
          ├─ ✍️ Редактировать → FSM: ожидание текста от админа
          ├─ ❌ Отклонить → delete pending → notify "отклонено"
          └─ (2 часа без ответа) → auto-dismiss → log
```

### Preview сообщение админу

```
📋 Пост на модерации

Рубрика: 💡 Совет дня
Время: 12:05

───────────────
{текст поста}
───────────────

[✅ Опубликовать] [🔄 Другой вариант]
[✍️ Редактировать] [❌ Отклонить]
```

---

## 4. Хранение pending posts

### In-memory dict (как channel_preview_cache)

```python
# admin_bot/channel/scheduler.py — добавить:
pending_posts = {}
# Структура:
# pending_posts[post_id] = {
#     "rubric": str,
#     "text": str,
#     "poll_data": tuple | None,   # (question, options) для poll
#     "preview_msg_id": int,       # ID сообщения с preview в чате админа
#     "created_at": datetime,
#     "attempts": int,             # сколько раз перегенерировали
# }
```

`post_id` — автоинкрементный int, начинается с 1 при каждом рестарте. Не нужен в БД — pending posts живут только в процессе.

**Почему не БД:** Pending posts — короткоживущие (< 2 часов). При рестарте бота они всё равно невалидны (preview message пропал). In-memory достаточно.

---

## 5. Timeout: 2 часа без ответа

**Решение: auto-dismiss (не publish).**

Обоснование: если админ не ответил — контент возможно неактуален (peak_hour stats, daily_stats устарели). Безопаснее не публиковать.

**Реализация:** В `channel_poster()` main loop — перед генерацией новых постов, проверяем expired:

```python
# В начале каждой итерации channel_poster():
now = datetime.now()
for post_id, post in list(pending_posts.items()):
    if (now - post["created_at"]).total_seconds() > 7200:  # 2 часа
        # Auto-dismiss
        try:
            await admin_bot.edit_message_text(
                chat_id=ADMIN_ID,
                message_id=post["preview_msg_id"],
                text=f"⏰ Пост [{post['rubric']}] отклонён по таймауту (2ч)"
            )
        except Exception:
            pass
        del pending_posts[post_id]
```

---

## 6. Callback data scheme

```
chmod:approve:{post_id}       — опубликовать
chmod:regen:{post_id}         — перегенерировать
chmod:edit:{post_id}          — начать редактирование
chmod:dismiss:{post_id}       — отклонить
chmod:mode:{rubric}           — переключить режим рубрики
```

**Длина callback_data:** Telegram limit = 64 bytes. `chmod:approve:999` = 18 bytes — ок.

---

## 7. FSM для редактирования

Новый state нужен только для режима "✍️ Редактировать":

```python
# admin_bot/channel/router.py — добавить:
from aiogram.fsm.state import State, StatesGroup

class ChannelPostEdit(StatesGroup):
    waiting_text = State()    # Ожидание нового текста от админа
```

### Flow редактирования:

1. Админ нажимает "✍️ Редактировать"
2. Handler сохраняет post_id в FSM data: `await state.update_data(editing_post_id=post_id)`
3. Устанавливает state: `await state.set_state(ChannelPostEdit.waiting_text)`
4. Отправляет: "Отправь новый текст поста (или /cancel для отмены)"
5. Следующее текстовое сообщение — новый текст поста
6. Обновляет preview, показывает кнопки заново
7. `await state.clear()`

### Отмена:

```python
@router.message(Command("cancel"), StateFilter(ChannelPostEdit.waiting_text))
async def cancel_edit(message, state):
    await state.clear()
    await message.answer("Редактирование отменено")
```

---

## 8. Изменения в scheduler.py

### Текущий код (lines 65-75):

```python
rubric = rubrics[0]
gen = CHANNEL_GENERATORS.get(rubric)
if gen:
    text = await gen()
    if text:
        if rubric == "poll":
            # ... send_poll
        else:
            await admin_bot.send_message(CHANNEL_ID, text)
        last_channel_post[rubric] = now
```

### Новый код:

```python
rubric = rubrics[0]
mode = await get_rubric_mode(rubric)   # "auto" или "moderated"
gen = CHANNEL_GENERATORS.get(rubric)

if gen:
    text = await gen()
    if not text:
        continue

    if mode == "auto":
        # Как раньше — сразу в канал
        if rubric == "poll":
            question, options = text
            await admin_bot.send_poll(CHANNEL_ID, question, options, is_anonymous=True)
        else:
            await admin_bot.send_message(CHANNEL_ID, text)
        last_channel_post[rubric] = now

    elif mode == "moderated":
        # Отправить на модерацию
        poll_data = text if rubric == "poll" else None
        post_text = text if rubric != "poll" else f"📊 Опрос: {text[0]}"
        await create_pending_post(rubric, post_text, poll_data)
        # НЕ обновляем last_channel_post — обновится после публикации
```

---

## 9. UI: управление режимами

### Новая кнопка в разделе "Канал"

```
📢 Канал
├── 📝 Создать пост
├── ⚡ Авто-постинг [ВКЛ]
├── 📅 Расписание
├── 🔔 Режимы рубрик         ← НОВАЯ
├── 📋 Очередь на модерацию  ← НОВАЯ
├── 📊 Канал стат
└── 🔌 Статус API
```

### "🔔 Режимы рубрик" — inline-клавиатура:

```
Режимы публикации:

[📊 daily_stats    — 🤖 АВТО]
[📈 peak_hour      — 🤖 АВТО]
[💡 dating_tip     — 👁 МОДЕР]
[😂 joke           — 👁 МОДЕР]
[📊 poll           — 🤖 АВТО]
[📰 weekly_recap   — 👁 МОДЕР]
[🎯 milestone      — 🤖 АВТО]
```

Каждая строка — кнопка `chmod:mode:{rubric}`. Нажатие переключает режим (toggle).

### "📋 Очередь на модерацию"

Если pending_posts пуст:
```
Очередь пуста — все посты опубликованы ✅
```

Если есть pending:
```
📋 На модерации: 2 поста

1. 💡 dating_tip — 12:05 (1ч 23мин назад)
2. 😂 joke — 15:02 (18мин назад)

[Открыть #1] [Открыть #2]
```

Кнопка "Открыть" — пересылает preview-сообщение с кнопками модерации.

---

## 10. Список файлов для изменения

| Файл | Что менять |
|------|-----------|
| **admin_bot/config.py** | Добавить `RUBRIC_MODE` dict с дефолтами |
| **admin_bot/channel/scheduler.py** | Логика auto/moderated, pending_posts dict, timeout cleanup, create_pending_post() |
| **admin_bot/channel/router.py** | Новые хэндлеры: chmod:approve/regen/edit/dismiss/mode, ChannelPostEdit FSM, кнопки "Режимы рубрик" и "Очередь" |
| **admin_bot/keyboards.py** | Кнопки модерации (approve/regen/edit/dismiss), кнопка "Режимы рубрик", кнопка "Очередь" |
| **admin_bot/db.py** | get_rubric_mode(rubric), set_rubric_mode(rubric, mode) — через bot_stats |

---

## 11. SQL миграции

Не требуются. Используем существующую `bot_stats` (key-value):
```
key: "rubric_mode:dating_tip"   value: "moderated"
key: "rubric_mode:joke"         value: "moderated"
```

Если ключа нет — берётся дефолт из `RUBRIC_MODE` в config.py.

---

## 12. Риски

| Риск | Митигация |
|------|-----------|
| Админ забыл одобрить → пост пропущен | Timeout 2ч + логирование. Можно добавить повторное напоминание через 1ч |
| Перегенерация тратит AI API | Лимит: max 3 перегенерации на пост (`attempts` в pending_posts) |
| Рестарт бота = потеря pending posts | Приемлемо: pending живут < 2ч, после рестарта scheduler сгенерирует новые |
| Конфликт: scheduler генерирует новый пост пока старый в очереди | Проверка: `if rubric in [p["rubric"] for p in pending_posts.values()]: skip` |
| Много постов в очереди = спам админу | Показывать одно уведомление с кнопкой "📋 Очередь" вместо отдельных preview |
