# Спецификация: Персистентная бонусная энергия (bonus_energy)

**Приоритет:** P1 | **Автор:** Архитектор | **Дата:** 2026-04-03

---

## 1. Проблема

Вся энергия хранится в одном поле `ai_energy_used`. При ежедневном ресете:
```python
await _update_user(uid, ai_energy_used=0, ai_messages_reset=datetime.now())
```
Все бонусы от ачивок, квестов и покупок за Stars **сгорают**.

**Текущая формула:**
```
energy_left = max_energy - ai_energy_used
где max_energy = DAILY_ENERGY[tier] + ai_bonus
```

**Проблема в деталях:** Покупка за Stars уменьшает `ai_energy_used` (bot.py:1741):
```python
new_used = max(0, energy_used - pack["amount"])
```
Если юзер купил 50 энергии вечером и использовал 10 — при ресете `ai_energy_used=0`, оставшиеся 40 пропадают. Юзер заплатил реальные деньги за энергию, которая сгорела.

---

## 2. Решение

Новое поле `bonus_energy` (INTEGER DEFAULT 0) — персистентный баланс, не сбрасывается при ежедневном ресете.

**Новая формула:**
```
effective_max = max_energy + bonus_energy
energy_left = effective_max - ai_energy_used
```

**Порядок расхода:**
1. Сначала тратится дневная энергия (max_energy)
2. Когда дневная исчерпана — тратится бонусная (bonus_energy)
3. При ресете: `ai_energy_used = 0`, `bonus_energy` остаётся

**Реализация порядка расхода через ресет:**
```python
# При ежедневном ресете:
if energy_used > max_energy:
    # Юзер потратил часть бонусной — уменьшаем bonus_energy
    bonus_spent = energy_used - max_energy
    new_bonus = max(0, bonus_energy - bonus_spent)
    await _update_user(uid, ai_energy_used=0, bonus_energy=new_bonus, ai_messages_reset=now)
else:
    # Юзер потратил только дневную — bonus_energy не трогаем
    await _update_user(uid, ai_energy_used=0, ai_messages_reset=now)
```

Это ключевая логика. Дневная энергия сбрасывается, бонусная "разъедается" только если юзер реально превысил дневной лимит.

---

## 3. SQL миграция

```sql
ALTER TABLE users ADD COLUMN bonus_energy INTEGER DEFAULT 0;
```

**Одноразовая миграция данных:** Для юзеров с `ai_energy_used < 0` (результат текущих покупок):
```sql
UPDATE users
SET bonus_energy = ABS(ai_energy_used),
    ai_energy_used = 0
WHERE ai_energy_used < 0;
```

---

## 4. Точки начисления bonus_energy

### 4.1. Покупка за Stars (bot.py:1740-1742)

**БЫЛО:**
```python
energy_used = u.get("ai_energy_used", 0) if u else 0
new_used = max(0, energy_used - pack["amount"])
await update_user(uid, ai_energy_used=new_used)
```

**СТАЛО:**
```python
bonus = u.get("bonus_energy", 0) if u else 0
new_bonus = bonus + pack["amount"]
await update_user(uid, bonus_energy=new_bonus)
```
Покупки теперь всегда идут в bonus_energy. Не тратятся при ресете.

### 4.2. Ачивки (при реализации spec-energy-earning)

**БЫЛО (план):** `ai_energy_used -= reward`
**СТАЛО:** `bonus_energy += reward`

### 4.3. Квесты (при реализации spec-energy-earning)

**БЫЛО (план):** `ai_energy_used -= reward`
**СТАЛО:** `bonus_energy += reward`

### 4.4. Бонус за оценку чата (при реализации spec-energy-earning)

**БЫЛО (план):** `ai_energy_used -= 2`
**СТАЛО:** `bonus_energy += 2`

### 4.5. Return Gifts (при реализации spec-return-gifts)

**БЫЛО (план):** `ai_energy_used -= gift_amount`
**СТАЛО:** `bonus_energy += gift_amount`

### 4.6. Стрик-бонусы — БЕЗ ИЗМЕНЕНИЙ

`ai_bonus` — это другой механизм (увеличивает max_energy на постоянной основе). Не трогаем.

---

## 5. Точки расхода (проверка доступной энергии)

### 5.1. AI сообщение (ai_chat.py:912-918)

**БЫЛО:**
```python
cost, max_energy = get_energy_info(char_tier, user_tier, ai_bonus)
if energy_used + cost > max_energy:
    # энергия кончилась
```

**СТАЛО:**
```python
cost, max_energy = get_energy_info(char_tier, user_tier, ai_bonus)
bonus = u.get("bonus_energy", 0) if u else 0
effective_max = max_energy + bonus
if energy_used + cost > effective_max:
    # энергия кончилась
```

### 5.2. Ежедневный ресет (ai_chat.py:915-917)

**БЫЛО:**
```python
if reset_time and (datetime.now() - reset_time).total_seconds() > 86400:
    await _update_user(uid, ai_energy_used=0, ai_messages_reset=datetime.now())
    energy_used = 0
```

**СТАЛО:**
```python
if reset_time and (datetime.now() - reset_time).total_seconds() > 86400:
    bonus = u.get("bonus_energy", 0) if u else 0
    if energy_used > max_energy:
        bonus_spent = energy_used - max_energy
        new_bonus = max(0, bonus - bonus_spent)
    else:
        new_bonus = bonus
    await _update_user(uid, ai_energy_used=0, bonus_energy=new_bonus, ai_messages_reset=datetime.now())
    energy_used = 0
    bonus = new_bonus  # обновить локальную переменную
```

---

## 6. UI — отображение энергии

### 6.1. Энерго-бар (ai_chat.py:154-158 и energy_shop.py:27-32)

**Подход: одна шкала, два источника.**

```
⚡ 45/30 [▓▓▓▓▓▓▓▓▓▓] (+15 бонус)
```

Юзер видит: у меня 45 энергии (30 дневная + 15 бонусная). Не запутывает.

**БЫЛО:**
```python
def _energy_bar(used: int, max_e: int) -> str:
    current = max(max_e - used, 0)
    filled = round((current / max_e) * 8) if max_e > 0 else 0
    bar = "▓" * filled + "░" * (8 - filled)
    return f"⚡ {current}/{max_e}  {bar}"
```

**СТАЛО:**
```python
def _energy_bar(used: int, max_e: int, bonus: int = 0) -> str:
    effective_max = max_e + bonus
    current = max(effective_max - used, 0)
    filled = round((current / effective_max) * 8) if effective_max > 0 else 0
    bar = "▓" * filled + "░" * (8 - filled)
    bonus_hint = f"  (+{bonus} bonus)" if bonus > 0 else ""
    return f"⚡ {current}/{effective_max}  {bar}{bonus_hint}"
```

### 6.2. Энерго-шоп (energy_shop.py:50-57)

Добавить `bonus_energy` в расчёт:
```python
bonus = u.get("bonus_energy", 0) if u else 0
effective_max = max_energy + bonus
energy_left = max(effective_max - energy_used, 0)
bar = _energy_bar(energy_left, effective_max)
```

### 6.3. Профиль энергии (bot.py:2776-2795)

Аналогично — добавить bonus в расчёт `energy_left` и передать в `_energy_bar`.

---

## 7. Полный список файлов для изменения

| Файл | Строки | Что менять |
|------|--------|-----------|
| **bot.py** | ~134 | init_db: добавить поле `bonus_energy INTEGER DEFAULT 0` |
| **bot.py** | ~1740-1742 | Покупка Stars: начислять в bonus_energy вместо уменьшения ai_energy_used |
| **bot.py** | ~2776-2795 | Профиль: учитывать bonus_energy в отображении |
| **ai_chat.py** | ~146-151 | get_energy_info: добавить параметр bonus (или менять в вызывающем коде) |
| **ai_chat.py** | ~154-158 | _energy_bar: добавить параметр bonus |
| **ai_chat.py** | ~912-918 | Проверка энергии: effective_max = max_energy + bonus |
| **ai_chat.py** | ~915-917 | Ресет: сохранять bonus_energy при сбросе ai_energy_used |
| **ai_chat.py** | ~956-958 | После отправки: учитывать bonus в energy_left |
| **energy_shop.py** | ~27-32 | _energy_bar: добавить параметр bonus |
| **energy_shop.py** | ~50-57 | Показ шопа: учитывать bonus_energy |
| **locales.py** | — | Добавить ключ для бонусной метки (опционально) |

---

## 8. Формула — итоговая сводка

```
ЕЖЕДНЕВНЫЙ ЦИКЛ:
  max_energy     = DAILY_ENERGY[tier] + ai_bonus         (30/200 + стрик)
  bonus_energy   = персистентный баланс                   (покупки, ачивки, квесты)
  effective_max  = max_energy + bonus_energy
  energy_left    = effective_max - ai_energy_used

РАСХОД (каждое AI сообщение):
  ai_energy_used += cost
  Блокировка если: ai_energy_used > effective_max

РЕСЕТ (каждые 24ч):
  if ai_energy_used > max_energy:
      bonus_energy -= (ai_energy_used - max_energy)   # бонус частично потрачен
  ai_energy_used = 0

НАЧИСЛЕНИЕ БОНУСОВ:
  Покупка Stars   → bonus_energy += amount
  Ачивка          → bonus_energy += reward
  Квест           → bonus_energy += reward
  Оценка чата     → bonus_energy += 2
  Return Gift     → bonus_energy += gift
  Стрик           → ai_bonus += milestone    (другой механизм, не bonus_energy)
```

---

## 9. Риски

| Риск | Митигация |
|------|-----------|
| bonus_energy растёт бесконечно | Лимит: MAX_BONUS_ENERGY = 500 (добавить в constants.py) |
| Юзер копит бонус и не покупает Premium | 500 энергии = ~166 сообщений basic. Premium дает 200/день — всё равно выгоднее |
| Обратная совместимость | bonus_energy DEFAULT 0 — старые юзеры не затронуты |
| Миграция юзеров с отрицательным ai_energy_used | Одноразовый SQL: перенести отрицательный баланс в bonus_energy |
| Гонка при параллельном начислении бонусов | Использовать `INCREMENT` через db.py:increment_user вместо read-modify-write |

---

## 10. Рекомендации для Разработчика

**Порядок:**
1. SQL миграция (1 поле + одноразовый UPDATE)
2. ai_chat.py — ресет и проверка энергии (ядро логики)
3. bot.py — покупка Stars (самое критичное — деньги юзеров)
4. energy_shop.py + bot.py — UI отображение
5. Будущие системы (ачивки, квесты, return gifts) — сразу начисляют в bonus_energy

**Тестирование:**
- Юзер с 0 бонусов → ресет не трогает bonus_energy
- Юзер купил 50 → потратил 40 дневных + 20 бонусных → ресет → bonus_energy = 30
- Юзер купил 50 → потратил 20 дневных → ресет → bonus_energy = 50 (не тронут)
- Отображение: 30 дневных + 15 бонусных = "45/45" в шкале
