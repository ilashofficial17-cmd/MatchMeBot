# MatchMe Bot — Project Bible

> Полная база знаний проекта: архитектура, дизайн-решения, копирайтинг-гайдлайны, структура файлов.
> Создано на основе дизайн/UX/копирайтинг аудита и рефакторинга апрель 2026.

---

## 1. Обзор проекта

**MatchMe** — Telegram-бот для анонимных знакомств и чатов.

| Параметр | Значение |
|----------|----------|
| Фреймворк | Aiogram 3.14 (Python) |
| БД | PostgreSQL (asyncpg) |
| FSM | MemoryStorage |
| AI | OpenRouter API (GPT-4o-mini, Hermes 3/4) |
| Локализация | 3 языка: RU, EN, ES |
| Монетизация | Telegram Stars (XTR) |
| Хостинг | Docker / VPS |

### Режимы чата
- **Chat** (simple) — общение по душам, 16+
- **Flirt** — флирт и лёгкие отношения, 16+
- **Kink/Roleplay** — 18+ контент, BDSM, фантазии

### AI-персонажи (13 штук)
| Блок | Персонажи | Тир |
|------|-----------|-----|
| Chat | Luna, Max Simple, Aurora, Alex | basic/vip |
| Flirt | Mia, Kai, Diana, Leon | basic/vip |
| Kink | Lilit, Eva, Damir, Ars, Master | vip_plus |

---

## 2. Архитектура файлов

```
MatchMeBot/
├── bot.py              (2954 строк) — Главный файл: хендлеры, FSM, поиск, чат
├── ai_chat.py          (1099 строк) — AI-чат: Router, ask_ai, хендлеры персонажей
├── ai_characters.py    (903 строки)  — Данные: AI_CHARACTERS dict, AI_LIMITS
├── ai_utils.py         (245 строк)  — OpenRouter API: get_ai_chat_response, translate
├── admin.py            (1585 строк) — Админка: Router, статистика, рассылки, задачи
├── moderation.py       (466 строк)  — Модерация: бан-слова, AI-судья, жалобы
├── db.py               (148 строк)  — DB хелперы: get_user, update_user, premium
├── constants.py        (223 строки) — Константы: цены, подарки, стоп-слова, реклама
├── keyboards.py        (278 строк)  — Все клавиатуры (Reply + Inline)
├── locales.py          (2289 строк) — Тексты RU/EN/ES (~456 ключей на язык)
├── states.py           (48 строк)   — FSM States: Reg, Chat, AIChat, Complaint...
├── energy_shop.py      (105 строк)  — Магазин энергии: Router, инвойсы
├── legal_texts.py      (375 строк)  — Юридические документы (ToS + Privacy) 3 языка
├── telegraph_pages.py  (175 строк)  — Публикация legal docs в Telegraph
├── channel_bot.py      (670 строк)  — Отдельный бот для канала
└── migrate_interests.py (88 строк)  — Миграция старых интересов
```

### Паттерн Dependency Injection
Модули не импортируют bot.py напрямую (избежание circular imports).
Вместо этого — паттерн `init()`:

```python
# В модуле (ai_chat.py, admin.py, moderation.py):
_bot = None
_get_user = None

def init(*, bot, get_user, ...):
    global _bot, _get_user
    _bot = bot
    _get_user = get_user

# В bot.py main():
ai_chat.init(bot=bot, get_user=get_user, ...)
dp.include_router(ai_chat.router)
```

### Порядок инициализации (main)
```
1. init_db()           — создание таблиц, миграции
2. db.init()           — передача db_pool в db.py
3. moderation.init()   — бот + db_pool + admin_id
4. create_legal_pages() — Telegraph страницы (кеш)
5. energy_shop.setup() — бот + db функции
6. ai_chat.init()      — все зависимости
7. admin_module.init()  — все зависимости
8. include_routers()   — подключение Router'ов
9. start_polling()
```

---

## 3. Глобальное состояние (bot.py)

```python
active_chats = {}          # uid -> partner_uid (активные чаты)
waiting_simple = set()     # очередь поиска: simple
waiting_flirt = set()      # очередь поиска: flirt
waiting_kink = set()       # очередь поиска: kink
waiting_*_premium = set()  # приоритетные очереди для Premium
pairing_lock = asyncio.Lock()  # защита от двойного матчинга
chat_logs = {}             # uid -> [messages] (для жалоб)
ai_sessions = {}           # uid -> {character_id, ...}
mutual_likes = {}          # uid -> set(partner_uids)
```

---

## 4. FSM States

```
Reg:          name → age → gender → mode → interests
Chat:         waiting, chatting
LangSelect:   choosing
Rules:        waiting
Complaint:    reason
EditProfile:  name, age, gender, mode, interests, search_gender
ResetProfile: confirm
AIChat:       choosing, chatting
AdminState:   waiting_user_id, waiting_char_gif
```

---

## 5. Монетизация

### Premium подписки
| План | Stars (RU) | Дни | Бейдж |
|------|-----------|-----|-------|
| 7d   | 129 ⭐    | 7   | — |
| 1m   | 349 ⭐    | 30  | 🔥 |
| 3m   | 749 ⭐    | 90  | 💎 (-28%) |

### Energy пакеты
| Пакет | Stars (RU) | Энергия | Описание |
|-------|-----------|---------|----------|
| e10   | 29 ⭐     | +10     | продолжить диалог |
| e50   | 99 ⭐     | +50     | на целый вечер 🔥 |
| e150  | 249 ⭐    | +150    | хватит надолго 💎 |

### Подарки
| Подарок | Stars | Дни Premium |
|---------|-------|-------------|
| 🌹 Rose    | 19 ⭐  | +1 день |
| 💎 Diamond | 49 ⭐  | +3 дня  |
| 👑 Crown   | 99 ⭐  | +7 дней |

### Региональные множители
```python
PRICE_MULTIPLIERS = {"ru": 1.0, "es": 1.3, "en": 2.0}
```
Базовые цены × множитель = финальная цена в Stars.

### A/B тестирование
- Группа A: стандартная цена
- Группа B: скидка 15% (`AB_PRICE_DISCOUNT_B = 0.85`)

---

## 6. Дизайн-система и UX-решения

### Клавиатура чата (kb_chat)
```
Ряд 1: [❤️ Лайк]  [💬 Тема]
Ряд 2: [⏭ Далее]  [🛑 Стоп]
Ряд 3: [⚠️ Жалоба] [🏠 Домой]
```
> Лайк и Жалоба разнесены (были рядом — случайные нажатия).

### AI-персонажи (kb_ai_characters)
- Кнопки персонажей по 2 в ряд
- Kink-персонажи для non-VIP: одна кнопка "🔒 Открыть 5 VIP+ персонажей"
- В конце: кнопка "⚡ Пополнить энергию"

### After-chat flow
- **2 сообщения** вместо 3 (было: chat_ended + rate + partner_left, стало: chat_ended_rate + after_chat)
- Рейтинг встроен в сообщение о конце чата

### Energy Shop UI
```
⚡ Твоя энергия

▰▰▰▱▱▱▱▱▱▱  45 / 100
🔄 Сброс через 18ч 23м

Выбирай пакет — и продолжай общение 👇

[⚡ +10 — продолжить диалог — 29 ⭐]
[⚡ +50 — на целый вечер — 99 ⭐ 🔥]
[⚡ +150 — хватит надолго — 249 ⭐ 💎]
[💎 Premium — 200 ⚡/день уже включено]
[← Назад]
```

---

## 7. Копирайтинг-гайдлайны

### Тон и голос
- **Обращение**: "ты" (не "вы"), дружеский тон
- **Стиль**: короткие фразы, живой язык, как пишет друг в чате
- **Эмодзи**: 1-2 на сообщение, тематические (не случайные)
- **Без канцеляризма**: "готово" вместо "зачислено", "возьми" вместо "оформи"

### Принципы текстов
| Принцип | Плохо | Хорошо |
|---------|-------|--------|
| Выгода > фича | "200 ⚡/день без покупок" | "200 ⚡/день уже включено" |
| Действие > описание | "Каждое сообщение тратит энергию" | "Выбирай пакет — и продолжай 👇" |
| Не пугать | "бессрочный бан", "невозможен" | Убрать из саммари, оставить в полном документе |
| Не обесценивать | "+10 — ещё пару фраз" | "+10 — продолжить диалог" |
| Мотивировать | "Общение продолжается" | "Возвращайся в чат 💬" |

### Privacy экран — структура
```
📋 Короткий заголовок

Вступление (1 строка)

🔞 Возраст
🔒 Данные
💬 Переписка
🤖 AI
💳 Покупки

📄 Полная версия: ссылка
💬 Поддержка: контакт

CTA принятия
```
> Эмодзи-иконки вместо буллетов (•) — визуальное разделение секций.

### Шаблон для новых текстов
1. Заголовок с эмодзи (1 строка)
2. Пустая строка
3. Основной текст (2-4 строки, короткие)
4. Пустая строка
5. CTA или кнопки

---

## 8. Система энергии (AI)

### Лимиты
```python
DAILY_ENERGY = {"free": 30, "premium": 200}
AI_LIMITS = {
    "basic":    {"free": 20,  "premium": 100},
    "vip":      {"free": 10,  "premium": 50},
    "vip_plus": {"free": 0,   "premium": 50},
}
```

### Стоимость по тирам
- **basic** персонажи: 1 энергия/сообщение
- **vip** персонажи: 2 энергии/сообщение
- **vip_plus** персонажи: 3 энергии/сообщение

### Сброс
- Каждые 24 часа (от `ai_messages_reset` timestamp)
- `ai_bonus` добавляется к лимиту (стрик-бонусы)

### Streak бонусы
```python
STREAK_BONUSES = {3: +5, 7: +10, 14: +15, 30: +20}
```
Бонус добавляется к `ai_bonus` (макс 50).

---

## 9. Уровни пользователей

```python
LEVEL_THRESHOLDS = [0, 10, 30, 75, 150, 300]  # total_chats
```

| Уровень | Чатов | Название |
|---------|-------|----------|
| 0 | 0+   | Новичок |
| 1 | 10+  | Общительный |
| 2 | 30+  | Душа компании |
| 3 | 75+  | Мастер общения |
| 4 | 150+ | Легенда |
| 5 | 300+ | Бог чатов |

---

## 10. Рекламная система

### Структура слота
```python
{
    "text_key": "ad_dzen_1",      # ключ текста в locales.py
    "url": "https://t.me/...",    # URL рекламодателя
    "btn_key": "btn_ad_connect",  # ключ кнопки
    "langs": ["ru"],              # None = все языки
    "modes": None,                # None = все режимы, ["kink"] = только kink
}
```

### Текущие рекламодатели
| Рекламодатель | Языки | Режимы |
|---------------|-------|--------|
| Dzen VPN | RU | все |
| BuyVPN Global | EN, ES | все |
| Playbox | EN, ES | kink |
| SMS PRO | RU | все |
| BoundLess3D | все | kink, flirt |
| Song Stop | EN, ES | все |
| Совместимость | RU, EN | simple, flirt |
| Звёздный бот | RU | все |
| Luna AI | все | kink |

---

## 11. Модерация

### Лестница наказаний
1. Предупреждение (warn_count += 1)
2. Бан 3 часа (warn_count >= 2)
3. Бан 24 часа (warn_count >= 3)
4. Перманентный бан (тяжёлые нарушения)

### AI-модератор
- Анализирует chat_log по жалобе
- Выдаёт reasoning + confidence
- Автобан при confidence > 0.85

### Стоп-слова
Автоматически логируются при обнаружении:
- Реклама услуг, спам, крипта
- Контент с несовершеннолетними
- Эскорт/проституция

---

## 12. Юридическая система

### Документы
- **Terms of Service + Privacy Policy** — единый документ
- 3 языка: RU, EN, ES
- Хранение: Telegraph pages (кешируются в `.telegraph_cache.json`)
- Применимое право: US law, AAA arbitration

### Ключевые пункты
- Минимальный возраст: 16 (18+ для kink)
- Все покупки окончательны (EU Directive 2011/83/EU Art. 16(m))
- AI-персонажи вымышлены
- Данные: Telegram ID, имя, возраст, пол (не хранит: телефон, email, IP)
- Удаление данных: команда /reset

---

## 13. Рефакторинг — что было сделано

### Tier 1 (выполнено)
| Из файла | Новый файл | Строк | Что извлечено |
|----------|-----------|-------|---------------|
| bot.py | db.py | 148 | 12 DB-функций (get_user, update_user, get_premium_tier...) |
| bot.py | constants.py | 223 | PREMIUM_PLANS, GIFTS, STOP_WORDS, PARTNER_ADS, LEVEL_*, STREAK_* |
| ai_chat.py | ai_characters.py | 903 | AI_CHARACTERS dict (13 персонажей), AI_LIMITS |

### Результат
- `bot.py`: 3160 → 2954 строк
- `ai_chat.py`: 1991 → 1099 строк
- Все модули связаны через imports, поведение не изменено

### Tier 2 (не реализовано, план)
- `premium.py` — хендлеры покупок/инвойсов из bot.py как Router
- `registration.py` — FSM регистрации из bot.py как Router
- `profile.py` — профиль/настройки/help из bot.py как Router

---

## 14. Копирайтинг — что было переписано

### Полный список переписанных ключей (RU/EN/ES)
```
welcome, welcome_intro, welcome_tour, welcome_back,
channel_bonus, help_text, premium_title, premium_info,
benefit_premium, upsell, profile_text, profile_upgrade,
searching_anon, connected, partner_found, chat_ended,
partner_left, no_partner_wait, after_chat_propose,
ad_message, stats_text, mutual_match, mutual_request_sent,
mutual_request_received, streak_reminder, streak_lost,
ai_miss_you, inactivity_end, settings_title, reg_rules_profile,
chat_ended_rate, ai_unlock_vip_plus, privacy,
energy_shop_title, energy_pack_10/50/150,
energy_shop_premium_cta, energy_purchased,
ai_energy_low, ai_energy_empty
```

### Переименованные кнопки
| Было | Стало |
|------|-------|
| ⚡ Поиск | 🎲 Случайный чат |
| 🔍 По анкете | 🔍 Подбор по анкете |

---

## 15. Чеклист для новых фич

При добавлении новой функции:

- [ ] Текст добавлен во все 3 языка в `locales.py`
- [ ] Тон соответствует гайдлайнам (ты, короткие фразы, выгода > фича)
- [ ] Клавиатура добавлена в `keyboards.py`
- [ ] Кнопки не конфликтуют с существующими (проверить `_all()` коллизии)
- [ ] Если новый Router — подключен в `main()` через `dp.include_router()`
- [ ] Если нужны DB-функции — использовать `db.py` или паттерн init()
- [ ] Цены учитывают `PRICE_MULTIPLIERS` (RU/EN/ES)
- [ ] Premium-фичи проверяют `get_premium_tier()` / `is_premium()`
- [ ] Эмодзи в кнопках: один тематический, не перегружать
