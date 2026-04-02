# Артефакт сессии — 2 апреля 2026 (сессия 3)

> Контекст всего, что обсуждалось и делалось в чате с Claude.
> Тема сессии: система энергии ИИ, магазин энергии, фикс дублирующихся эмодзи.

---

## Исходный контекст на старте сессии

Система энергии была уже реализована на `main` другой сессией Claude (коммит `eb2e0e2`):
- `ENERGY_COST = {"basic": 1, "vip": 2, "vip_plus": 3}`
- 30⚡/день (free), 200⚡/день (premium)
- Поле `ai_energy_used` в БД
- Ключ `ai_energy_status` в локали

Проблема: предыдущий локальный коммит был утерян после `git reset --hard origin/main`.
Новая кодовая база имеет другую структуру (извлечённые файлы `ai_characters.py`, `constants.py`, `db.py`).

---

## Фаза 1: Переприменение системы энергии на новую кодовую базу

**Коммит:** `9863182`

### Изменения keyboards.py
- **Убран lock блока 3** (VIP+ персонажи): удалена проверка `is_premium`, все 13 персонажей доступны всем без подписки

### Изменения ai_chat.py
| Что | Было | Стало |
|-----|------|-------|
| Тип иконки тира | `"🔥"` для VIP/VIP+ | `{"basic":"✅","vip":"⭐","vip_plus":"💎"}` |
| Проверка на входе | Блокировала вход если `energy_used + cost > max` | Убрана — проверка только в обработчике сообщений |
| Поле энергии | `ai_energy_used` (накопленное) | без изменений |
| Отображение при входе | `ai_energy_status` → `⚡ left/max` | `ai_energy_cost` → `⚡ Стоимость: N энергии за сообщение` |
| После каждого ответа | Только предупреждение при ≤5 | Добавлена визуализация бара `⚡ 27/30 ▓▓▓▓▓▓▓▓▓░` |
| При пустой энергии | `ai_limit_basic/plus` (без таймера) | `ai_energy_empty` с обратным отсчётом `{hours}ч {mins}м` |

Добавлена функция `_energy_bar(used, max_e)` — 8-блочная визуализация `▓░`.

### Изменения locales.py (ru/en/es)
- Добавлены: `ai_energy_cost`, `ai_energy_low`, `ai_energy_empty`
- Удалены: `ai_limit_plus`, `ai_limit_basic`, `ai_remaining`, `ai_energy_status`
- Обновлены: `ai_chatting_with`, `ai_quick_start` — `{limit_text}` → `{energy_text}`

---

## Фаза 2: Магазин энергии + комплексный рефакторинг

**Коммит:** `f3f9948`

После показа скриншотов пользователь выявил ряд проблем:
1. Бар энергии в чате — нужно убрать
2. Нет магазина энергии (нового файла)
3. Старые лимиты ("20 сообщений/день") остались в `ai_menu` и `premium_info`
4. Дубликаты эмодзи в кнопках и тексте
5. Иконки `tier_icon` + эмодзи из имени персонажа давали двойные символы

### Создан energy_shop.py (новый файл)
```
Структура:
- setup(bot, get_user, update_user, get_lang) — инъекция зависимостей
- energy_shop_show (callback: energy_shop) — показывает магазин с текущим балансом
- energy_buy (callback: energy_buy:{key}) — инвойс на покупку пакета
```

### constants.py — добавлены ENERGY_PACKS
```python
ENERGY_PACKS = {
    "e30":  {"stars": 49,  "amount": 30,  "label_key": "energy_pack_30",  "emoji": "⚡"},
    "e100": {"stars": 129, "amount": 100, "label_key": "energy_pack_100", "emoji": "⚡⚡"},
    "e300": {"stars": 299, "amount": 300, "label_key": "energy_pack_300", "emoji": "⚡⚡⚡"},
}
```
Цены умножаются на `PRICE_MULTIPLIERS` по языку (ru×1.0, es×1.3, en×2.0).

### keyboards.py — добавлена kb_energy_shop()
```python
def kb_energy_shop(lang="ru"):
    # Для каждого пакета: цена * мультипликатор языка
    # callback_data = "energy_buy:{key}"
```

### bot.py
- Добавлен импорт `energy_shop_module` и `ENERGY_PACKS`
- В `successful_payment`: обработчик `payload.startswith("energy_")` — вычитает `pack["amount"]` из `ai_energy_used` (даёт мгновенную энергию)
- Добавлен `energy_shop_module.setup(...)` и `dp.include_router(energy_shop_module.router)`

### ai_chat.py
- **Убран бар из сообщений**: `⚡ 27/30 ▓░` после каждого ответа убран
- **Убран tier_icon**: в `choose_ai_character` и `ai_quick_start` имя берётся напрямую из локали (она уже содержит эмодзи)
- **Info callback**: убран `cdata['emoji']` prefix (дублировал эмодзи из локали)
- **Кнопка на пустой энергии**: добавлен `btn_buy_energy` → `energy_shop`
- **_show_ai_menu**: вычисляет и передаёт `energy_left`, `energy_max` в шаблон `ai_menu`

### locales.py (ru/en/es)
- `ai_menu`: убраны "Basic: 20/день" и т.п., добавлено `⚡ Энергия: {energy_left}/{energy_max}` + описание стоимости тиров
- `premium_info`: строка "Больше AI — 100 сообщений/день..." заменена на "⚡ Больше энергии — 200 ⚡/день"
- Добавлены: `energy_shop_title`, `energy_pack_30/100/300`, `energy_invoice_title`, `energy_invoice_desc`, `energy_purchased`, `energy_pack_not_found`, `btn_buy_energy`

---

## Фаза 3: Фикс дублирующихся эмодзи в рекомендациях + энергия везде

**Коммит:** `6b369c0`

После новых скриншотов выявлены оставшиеся проблемы.

### Источник дублей: `_get_ai_recommendations`
Функция строила строку `f"{char['emoji']} {t(lang, char['name_key'])}"`.
Locale key уже содержит эмодзи: `"char_luna" = "🌙 Луна"` → итог `"🌙 🌙 Луна"`.

**Фикс:**
```python
# Было:
fav_parts.append(f"{char['emoji']} {t(lang, char['name_key'])}")
text += t(lang, "ai_recommended", emoji=char["emoji"], name=...)

# Стало:
fav_parts.append(t(lang, char['name_key']))
text += t(lang, "ai_recommended", name=...)
```

Аналогично исправлены шаблоны `ai_recommended` в локалях (убран параметр `{emoji}`).

### Кнопка магазина энергии — добавлена в 3 места

| Место | Реализация |
|-------|------------|
| Список персонажей (`kb_ai_characters`) | `InlineKeyboardButton("⚡ Купить энергию", "energy_shop")` |
| Боковое меню (`kb_main`) | Новая строка `[KeyboardButton(btn_energy_shop)]` |
| Помощь (`help_text`) | Добавлена строка "⚡ Магазин энергии — купи энергию для ИИ чата" |

### Хендлер в bot.py
```python
@dp.message(F.text.in_(_all("btn_energy_shop")), StateFilter("*"))
async def cmd_energy_shop(message, state):
    # Вычисляет текущий баланс → показывает kb_energy_shop
```

---

## Итоговая схема системы энергии

### Поля в БД (таблица users)
| Поле | Тип | Назначение |
|------|-----|------------|
| `ai_energy_used` | int | Накопленное потребление за текущий день |
| `ai_messages_reset` | timestamp | Момент последнего сброса |
| `ai_bonus` | int | Постоянный бонус к дневному лимиту |

### Тиры персонажей и стоимость
| Тир | Стоимость | Персонажи |
|-----|-----------|-----------|
| `basic` | 1⚡ | Луна, Макс, Мия, Кай |
| `vip` | 2⚡ | Аврора, Алекс, Диана, Леон |
| `vip_plus` | 3⚡ | Лилит, Ева, Дамир, Арс, Мастер |

### Дневные лимиты
| Подписка | Лимит |
|----------|-------|
| Free | 30⚡/день |
| Premium | 200⚡/день |

### Пакеты энергии
| Пакет | Кол-во | Цена (ru) | Цена (en) |
|-------|--------|-----------|-----------|
| e30 | 30⚡ | 49⭐ | 98⭐ |
| e100 | 100⚡ | 129⭐ | 258⭐ |
| e300 | 300⚡ | 299⭐ | 598⭐ |

Покупка пакета: `ai_energy_used -= pack["amount"]` (мгновенная энергия).

---

## Все коммиты сессии

| Хэш | Описание |
|-----|----------|
| `9863182` | feat: energy system — bar visualization, all chars unlocked, cost on entry |
| `f3f9948` | feat: energy shop, fix duplicates, clean AI menu |
| `6b369c0` | fix: duplicate emoji in recommendations, add energy shop everywhere |

---

## Важные архитектурные решения

1. **Все 13 персонажей открыты без подписки** — доступ регулируется только энергией, не подпиской
2. **Бар энергии убран из чата** — пользователь хотел видеть энергию только при выборе персонажа
3. **Магазин в отдельном файле** (`energy_shop.py`) — аналог паттерна premium в bot.py, с инъекцией зависимостей
4. **Имена персонажей в локали уже содержат эмодзи** — не добавлять `char['emoji']` при отображении имени
5. **Покупка энергии не меняет дневной лимит** — уменьшает `ai_energy_used`, что эквивалентно добавлению энергии

---

## Правило для следующих сессий

> Всегда пушить в `main` сразу после каждого коммита, не ждать команды.
