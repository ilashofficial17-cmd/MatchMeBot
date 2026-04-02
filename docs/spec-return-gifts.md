# Спецификация: Подарки возвращения (Return Gifts)

**Приоритет:** P2 | **Автор:** Архитектор | **Дата:** 2026-04-02

---

## 1. Текущее состояние winback

`winback_task()` (admin.py:1276-1375) — 4 стадии push-уведомлений:

| Stage | Триггер | Сообщение | Бонус |
|-------|---------|-----------|-------|
| 1 | Premium истекает через 24ч | "Заканчивается завтра" | нет |
| 2 | Только истёк | "Закончился" | нет |
| 3 | 3+ дня после истечения | "Скучаем" | нет |
| 4 | 7+ дней | "Последний шанс" | нет |

**Проблема:** Уведомления без ценности — юзер не возвращается. Работает только для бывших Premium.

---

## 2. Дизайн Return Gifts

**Ключевое отличие:** Работает для ВСЕХ юзеров по `last_seen`, не только бывших Premium.

| Тир | Дни неактивности | Бонус энергии | Бонус Premium | Условие |
|-----|-----------------|---------------|---------------|---------|
| 1 | 3 дня | +10 | - | total_chats >= 1 |
| 2 | 7 дней | +25 | - | total_chats >= 3 |
| 3 | 14 дней | +50 | 1 день trial | total_chats >= 5 |
| 4 | 30 дней | +100 | 3 дня trial | total_chats >= 10 |

**Условие `total_chats`** — защита: новые юзеры, зарегистрировавшиеся и бросившие, не получают подарки.

---

## 3. Защита от абьюза

**Проблема:** Юзер уходит на 3 дня -> получает 10 энергии -> уходит -> повторяет.

**Решения:**
1. **Cooldown:** Минимум 30 дней между получениями Return Gift одного тира
2. **Лимит:** Максимум 4 подарка за всё время (по одному на тир). После тира 4 — больше не даём
3. **Сгорание:** Подарок сгорает через 48 часов если юзер не вернулся
4. **Не суммируются:** Пропустил тир 1 (3 дня) и вернулся на 8-й день — получает только тир 2, не оба

---

## 4. SQL миграция

```sql
ALTER TABLE users ADD COLUMN return_gift_stage  INTEGER   DEFAULT 0;
ALTER TABLE users ADD COLUMN return_gift_given  TIMESTAMP DEFAULT NULL;
ALTER TABLE users ADD COLUMN return_gifts_total INTEGER   DEFAULT 0;
```

- `return_gift_stage` — последний выданный тир (0-4)
- `return_gift_given` — когда выдан последний подарок (для cooldown 30д)
- `return_gifts_total` — общее число подарков (макс 4)

---

## 5. Интеграция с winback_task

НЕ заменяем текущий winback — он для бывших Premium. Новая система — дополнительная.

Добавить в `winback_task()` (admin.py) новый блок после строки ~1375:

```python
# Return Gifts — для всех неактивных юзеров
rows = await conn.fetch("""
    SELECT uid, last_seen, total_chats, return_gift_stage, 
           return_gift_given, return_gifts_total
    FROM users
    WHERE last_seen < NOW() - INTERVAL '3 days'
      AND return_gifts_total < 4
      AND (return_gift_given IS NULL 
           OR return_gift_given < NOW() - INTERVAL '30 days')
      AND ban_until IS NULL
      AND total_chats >= 1
""")
```

Для каждого юзера — определить тир по `days_since_last_seen`, выдать бонус:

```python
RETURN_GIFT_TIERS = {
    1: {"days": 3,  "energy": 10,  "premium_days": 0, "min_chats": 1},
    2: {"days": 7,  "energy": 25,  "premium_days": 0, "min_chats": 3},
    3: {"days": 14, "energy": 50,  "premium_days": 1, "min_chats": 5},
    4: {"days": 30, "energy": 100, "premium_days": 3, "min_chats": 10},
}
```

**Начисление энергии:**
```python
new_val = max(0, ai_energy_used - gift_amount)
await update_user(uid, ai_energy_used=new_val,
                  return_gift_stage=tier,
                  return_gift_given=datetime.now(),
                  return_gifts_total=total + 1)
```

**Trial Premium (тиры 3-4):**
```python
await update_user(uid, premium_until=(datetime.now() + timedelta(days=days)).isoformat())
```

---

## 6. Сообщения (добавить в locales.py)

| Ключ | RU | EN | ES |
|------|----|----|----|
| `return_gift_1` | "Мы скучали! +10 энергии — попробуй AI-чат!" | "We missed you! +10 energy — try AI chat!" | "Te extranamos! +10 energia — prueba el chat IA!" |
| `return_gift_2` | "Рады видеть! +25 энергии на счету" | "Good to see you! +25 energy added" | "Que bueno verte! +25 energia" |
| `return_gift_3` | "Подарок: +50 энергии и 1 день Premium!" | "Gift: +50 energy and 1 day Premium!" | "Regalo: +50 energia y 1 dia Premium!" |
| `return_gift_4` | "Макс подарок: +100 энергии и 3 дня Premium!" | "Max gift: +100 energy and 3 days Premium!" | "Regalo max: +100 energia y 3 dias Premium!" |

---

## 7. Файлы для изменения

| Файл | Что менять |
|------|-----------|
| `bot.py` | init_db — новые поля в users |
| `admin.py` | winback_task — новый блок Return Gifts после строки ~1375 |
| `constants.py` | RETURN_GIFT_TIERS dict |
| `locales.py` | 4 текста x 3 языка |

---

## 8. Риски

| Риск | Митигация |
|------|-----------|
| Фарм через уход/возврат | Cooldown 30д + лимит 4 подарка навсегда |
| Мультиаккаунты | Условие total_chats >= N делает фарм невыгодным |
| Спам уведомлениями | Один подарок = одно сообщение, не повторяется |
| Конфликт с winback Premium | Системы независимы, не пересекаются |

---

## 9. Реализация

**Оценка:** 2-3 часа
**Порядок:**
1. SQL миграция (3 поля)
2. RETURN_GIFT_TIERS в constants.py
3. Блок в winback_task (admin.py)
4. Тексты в locales.py
5. Тест: создать юзера с last_seen = NOW() - 4 days, запустить winback_task
