"""
AI-модерация для MatchMe бота.
Анализирует жалобы и сообщения через Claude API.
Ведёт аудит-лог всех решений.
"""

import os
import json
import logging
import aiohttp
from datetime import datetime, timedelta

logger = logging.getLogger("matchme.moderation")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Зависимости — инициализируются из bot.py
_bot = None
_db_pool = None
_admin_id = None

# Жёсткий бан — ЦП и несовершеннолетние (keyword-based, без AI)
HARD_BAN_WORDS = [
    "мне 12", "мне 13", "мне 14", "мне 15",
    "школьница ищу", "школьник ищу", "порно за деньги",
    "детское порно", "цп продаю", "малолетка",
]

# Подозрительные слова — триггер для AI-проверки (НЕ авто-бан)
SUSPECT_WORDS = [
    "предлагаю услуги", "оказываю услуги", "интим услуги",
    "escort", "эскорт", "проститутка",
    "вирт за деньги", "вирт платно", "за донат",
    "подпишись на канал", "перейди по ссылке", "мой канал",
    "казино", "ставки на спорт", "заработок в телеграм",
    "крипта х10", "пассивный доход", "продаю фото", "продаю видео",
    "продаю интим", "купи подписку", "пиши в лс за", "скидка на услуги",
]

MODERATION_SYSTEM_PROMPT = (
    "Ты модератор анонимного чат-бота для знакомств MatchMe. "
    "Анализируй переписку и принимай решение по жалобе.\n\n"
    "ПРАВИЛА:\n"
    "- Несовершеннолетние (упоминание возраста <18, поиск школьников) → ban_perm\n"
    "- Продажа интим-услуг, эскорт, платные услуги → shadow_ban\n"
    "- Спам, реклама каналов, крипто-схемы, финансовые пирамиды → shadow_ban\n"
    "- Угрозы физической расправой, преследование → ban_perm\n"
    "- Тяжёлые оскорбления, буллинг → ban_24h\n"
    "- Пошлый контент без согласия собеседника → warn или ban_3h\n"
    "- Ложная жалоба (ничего не нарушено) → dismiss\n"
    "- Неясная ситуация, недостаточно контекста → escalate\n\n"
    "УЧИТЫВАЙ:\n"
    "- Историю пользователя (предупреждения, прошлые жалобы)\n"
    "- Контекст переписки (шутка, взаимное согласие, провокация)\n"
    "- Тяжесть нарушения и повторность\n"
    "- Если у пользователя уже были предупреждения — ужесточай наказание\n\n"
    "SHADOW BAN:\n"
    "- Теневая блокировка — пользователь НЕ ЗНАЕТ что забанен\n"
    "- Используй для спамеров, рекламщиков, продавцов\n\n"
    "ОТВЕТ строго в JSON формате:\n"
    '{"decision": "warn|ban_3h|ban_24h|ban_perm|shadow_ban|escalate|dismiss", '
    '"confidence": 0.0-1.0, '
    '"reason_short": "краткая причина для уведомления пользователя (1 предложение)", '
    '"reason_detailed": "подробный анализ для аудит-лога (2-3 предложения)", '
    '"notify_user": true/false}\n\n'
    "notify_user=false ТОЛЬКО для shadow_ban и dismiss. Для остальных всегда true."
)

MESSAGE_CHECK_PROMPT = (
    "Ты модератор чата знакомств. Проверь сообщение на нарушения.\n"
    "Нарушения: продажа услуг, реклама, спам, мошенничество.\n"
    "Если нарушение есть — ответь JSON: {\"violation\": true, \"type\": \"shadow_ban\", \"reason\": \"причина\"}\n"
    "Если нет — ответь: {\"violation\": false}\n"
    "Отвечай ТОЛЬКО JSON, без пояснений."
)


def init(bot_instance, pool, admin_id):
    """Инициализация модуля — вызывается из bot.py"""
    global _bot, _db_pool, _admin_id
    _bot = bot_instance
    _db_pool = pool
    _admin_id = admin_id


async def migrate_db():
    """Добавляет новые колонки в complaints_log для AI-модерации"""
    if not _db_pool:
        return
    async with _db_pool.acquire() as conn:
        for col, definition in [
            ("decided_by", "TEXT DEFAULT 'pending'"),
            ("ai_reasoning", "TEXT DEFAULT NULL"),
            ("ai_confidence", "REAL DEFAULT NULL"),
            ("decision_details", "TEXT DEFAULT NULL"),
        ]:
            try:
                await conn.execute(
                    f"ALTER TABLE complaints_log ADD COLUMN IF NOT EXISTS {col} {definition}"
                )
            except Exception:
                pass


# ====================== CLAUDE API ======================

async def _ask_claude(system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-6", max_tokens: int = 400) -> str | None:
    """Универсальный вызов Claude API"""
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY не задан")
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("content", [])
                    if content and isinstance(content, list) and len(content) > 0:
                        return content[0].get("text")
                    logger.warning("Claude API: empty content in response")
                    return None
                else:
                    body = await resp.text()
                    logger.error(f"Claude API error: {resp.status} — {body[:200]}")
                    return None
    except Exception as e:
        logger.error(f"Claude API exception: {e}")
        return None


def _parse_json_response(text: str) -> dict | None:
    """Парсит JSON из ответа Claude (убирает markdown обёртку если есть)"""
    if not text:
        return None
    text = text.strip()
    # Убираем ```json ... ``` обёртку
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Попробуем найти JSON внутри текста
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        logger.error(f"Failed to parse AI response: {text[:200]}")
        return None


# ====================== AI-МОДЕРАЦИЯ ЖАЛОБ ======================

async def ai_review_complaint(complaint_id: int) -> dict | None:
    """
    AI анализирует жалобу и принимает решение.
    Возвращает dict с решением или None при ошибке (fallback на ручную модерацию).
    """
    if not _db_pool or not _bot:
        return None

    # Загружаем жалобу
    async with _db_pool.acquire() as conn:
        complaint = await conn.fetchrow(
            "SELECT * FROM complaints_log WHERE id=$1", complaint_id
        )
    if not complaint:
        return None

    accused_uid = complaint["to_uid"]
    reporter_uid = complaint["from_uid"]
    chat_log = complaint.get("chat_log", "")
    reason = complaint.get("reason", "")

    # История обвиняемого
    async with _db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", accused_uid)
        prev_complaints = await conn.fetch(
            "SELECT reason, admin_action, decided_by, ai_reasoning FROM complaints_log "
            "WHERE to_uid=$1 AND reviewed=TRUE ORDER BY created_at DESC LIMIT 5",
            accused_uid,
        )

    warn_count = user.get("warn_count", 0) if user else 0
    total_complaints = user.get("complaints", 0) if user else 0
    is_shadow = user.get("shadow_ban", False) if user else False

    history_text = f"Предупреждений: {warn_count}, Жалоб всего: {total_complaints}"
    if is_shadow:
        history_text += ", УЖЕ в shadow ban"
    if prev_complaints:
        history_text += "\nПоследние решения: " + "; ".join(
            f"{r.get('admin_action', r.get('ai_reasoning', '?'))}" for r in prev_complaints
        )

    user_prompt = (
        f"ЖАЛОБА #{complaint_id}\n"
        f"Причина: {reason}\n\n"
        f"ИСТОРИЯ ОБВИНЯЕМОГО:\n{history_text}\n\n"
        f"ПЕРЕПИСКА:\n{chat_log[:2000]}"
    )

    # Вызов AI
    raw = await _ask_claude(MODERATION_SYSTEM_PROMPT, user_prompt)
    result = _parse_json_response(raw)

    if not result or "decision" not in result:
        logger.warning(f"AI moderation failed for complaint #{complaint_id}, falling back to admin")
        return None

    decision = result["decision"]
    confidence = float(result.get("confidence", 0.5))
    reason_short = result.get("reason_short", "Нарушение правил")
    reason_detailed = result.get("reason_detailed", "")
    notify_user = result.get("notify_user", True)

    # Если уверенность низкая — эскалируем админу
    # Для перманентного бана требуем повышенную уверенность (85%)
    min_confidence = 0.85 if decision == "ban_perm" else 0.7
    if confidence < min_confidence or decision == "escalate":
        await _escalate_to_admin(complaint_id, complaint, result)
        return result

    # Применяем решение
    await _apply_decision(
        complaint_id, accused_uid, reporter_uid,
        decision, reason_short, reason_detailed, confidence, notify_user
    )
    return result


async def _escalate_to_admin(complaint_id: int, complaint: dict, ai_result: dict):
    """Эскалация админу с рекомендацией AI"""
    async with _db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE complaints_log SET decided_by='pending', ai_reasoning=$1, ai_confidence=$2 WHERE id=$3",
            ai_result.get("reason_detailed", ""),
            float(ai_result.get("confidence", 0)),
            complaint_id,
        )

    decision_map = {
        "warn": "Предупреждение", "ban_3h": "Бан 3ч", "ban_24h": "Бан 24ч",
        "ban_perm": "Перм бан", "shadow_ban": "Shadow ban",
        "escalate": "Не уверен", "dismiss": "Отклонить",
    }
    ai_decision = decision_map.get(ai_result.get("decision", ""), "?")
    confidence = ai_result.get("confidence", 0)

    try:
        await _bot.send_message(
            _admin_id,
            f"🤖 AI не уверен — нужно твоё решение\n\n"
            f"🚩 Жалоба #{complaint_id}\n"
            f"📋 Причина: {complaint.get('reason', '?')}\n"
            f"🤖 Рекомендация AI: {ai_decision} ({confidence:.0%})\n"
            f"💬 {ai_result.get('reason_detailed', '')}\n\n"
            f"👤 На: {complaint['to_uid']} | От: {complaint['from_uid']}"
        )
    except Exception as e:
        logger.error(f"Failed to escalate to admin: {e}")


async def _apply_decision(
    complaint_id: int, accused_uid: int, reporter_uid: int,
    decision: str, reason_short: str, reason_detailed: str,
    confidence: float, notify_user: bool,
):
    """Применяет решение AI и обновляет БД"""

    action_text = {
        "warn": "Предупреждение (AI)",
        "ban_3h": "Бан 3ч (AI)",
        "ban_24h": "Бан 24ч (AI)",
        "ban_perm": "Перм бан (AI)",
        "shadow_ban": "Shadow ban (AI)",
        "dismiss": "Отклонена (AI)",
    }.get(decision, decision)

    # Обновляем жалобу
    async with _db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE complaints_log SET reviewed=TRUE, admin_action=$1, decided_by='ai', "
            "ai_reasoning=$2, ai_confidence=$3, decision_details=$4 WHERE id=$5",
            action_text, reason_short, confidence, reason_detailed, complaint_id,
        )

    # Применяем наказание
    if decision == "warn":
        async with _db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET warn_count=warn_count+1 WHERE uid=$1", accused_uid
            )
        if notify_user:
            try:
                await _bot.send_message(
                    accused_uid,
                    f"⚠️ Предупреждение: {reason_short}\n"
                    f"Следующее нарушение приведёт к бану."
                )
            except Exception:
                pass

    elif decision == "ban_3h":
        until = (datetime.now() + timedelta(hours=3)).isoformat()
        async with _db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, accused_uid)
        if notify_user:
            try:
                await _bot.send_message(accused_uid, f"🚫 Бан на 3 часа: {reason_short}")
            except Exception:
                pass

    elif decision == "ban_24h":
        until = (datetime.now() + timedelta(hours=24)).isoformat()
        async with _db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, accused_uid)
        if notify_user:
            try:
                await _bot.send_message(accused_uid, f"🚫 Бан на 24 часа: {reason_short}")
            except Exception:
                pass

    elif decision == "ban_perm":
        async with _db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until='permanent' WHERE uid=$1", accused_uid)
        if notify_user:
            try:
                await _bot.send_message(accused_uid, f"🚫 Перманентный бан: {reason_short}")
            except Exception:
                pass

    elif decision == "shadow_ban":
        async with _db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET shadow_ban=TRUE WHERE uid=$1", accused_uid)
        # Shadow ban — НИКОГДА не уведомляем пользователя

    elif decision == "dismiss":
        pass  # Ничего не делаем, жалоба просто отклонена

    # Уведомляем админа о принятом решении
    try:
        await _bot.send_message(
            _admin_id,
            f"🤖 AI решение по жалобе #{complaint_id}:\n"
            f"{action_text} ({confidence:.0%})\n"
            f"💬 {reason_detailed}"
        )
    except Exception:
        pass


# ====================== ПРОВЕРКА СООБЩЕНИЙ В РЕАЛЬНОМ ВРЕМЕНИ ======================

async def check_message(text: str, uid: int) -> dict | None:
    """
    Проверяет сообщение на нарушения.
    HARD_BAN_WORDS — всегда keyword-based (нулевая толерантность).
    SUSPECT_WORDS — keyword триггер → AI-анализ для подтверждения.
    Обычные сообщения НЕ отправляются в AI (экономия API и латенси).
    Возвращает: {"action": "hard_ban|shadow_ban", "reason": "..."} или None
    """
    txt_lower = text.lower()

    # 1. HARD BAN — keyword matching (CP/minors, без AI, мгновенно)
    hard_match = [w for w in HARD_BAN_WORDS if w in txt_lower]
    if hard_match:
        return {"action": "hard_ban", "reason": f"Запрещённый контент: {', '.join(hard_match)}"}

    # 2. Проверяем наличие подозрительных слов (keyword pre-filter)
    suspect_match = [w for w in SUSPECT_WORDS if w in txt_lower]
    if not suspect_match:
        return None  # Обычное сообщение — пропускаем без AI

    # 3. Подозрительные слова найдены — AI подтверждает (только для подозрительных)
    if not ANTHROPIC_API_KEY:
        # Fallback без AI: shadow ban по keyword (как раньше)
        return {"action": "shadow_ban", "reason": f"Подозрительный контент: {', '.join(suspect_match[:3])}"}

    raw = await _ask_claude(
        MESSAGE_CHECK_PROMPT,
        f"Сообщение: {text[:500]}\nНайденные подозрительные слова: {', '.join(suspect_match)}",
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
    )
    result = _parse_json_response(raw)
    if result and result.get("violation"):
        return {
            "action": result.get("type", "shadow_ban"),
            "reason": result.get("reason", "Нарушение правил"),
        }

    return None


# ====================== АУДИТ-ЛОГ ======================

async def get_audit_log(limit: int = 10, offset: int = 0) -> list:
    """Возвращает список решений по жалобам для аудит-лога"""
    if not _db_pool:
        return []
    async with _db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, to_uid, from_uid, reason, admin_action, decided_by, "
            "ai_reasoning, ai_confidence, decision_details, created_at "
            "FROM complaints_log WHERE reviewed=TRUE "
            "ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
    return [dict(r) for r in rows]


async def get_audit_total() -> int:
    """Общее число решений в аудит-логе"""
    if not _db_pool:
        return 0
    async with _db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=TRUE")


async def get_decision_detail(complaint_id: int) -> dict | None:
    """Полная информация о решении для аудит-лога"""
    if not _db_pool:
        return None
    async with _db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM complaints_log WHERE id=$1", complaint_id
        )
    return dict(row) if row else None


def format_audit_entry(entry: dict) -> str:
    """Форматирует запись аудит-лога для отображения"""
    decided = entry.get("decided_by", "?")
    icon = "🤖" if decided == "ai" else "👤" if decided == "admin" else "⚙️"
    action = entry.get("admin_action", "?")
    date = entry["created_at"].strftime("%d.%m %H:%M") if entry.get("created_at") else "?"
    confidence = entry.get("ai_confidence")
    conf_text = f" ({confidence:.0%})" if confidence is not None else ""

    return (
        f"{icon} #{entry.get('id', '?')} | {action}{conf_text}\n"
        f"   На: {entry.get('to_uid', '?')} | Причина: {entry.get('reason', '?')}\n"
        f"   {date}"
    )


def format_decision_detail(entry: dict) -> str:
    """Форматирует полную детализацию решения"""
    decided = entry.get("decided_by", "?")
    icon = "🤖" if decided == "ai" else "👤" if decided == "admin" else "⚙️"
    confidence = entry.get("ai_confidence")

    lines = [
        f"{icon} Жалоба #{entry['id']}",
        f"",
        f"👤 Обвиняемый: {entry['to_uid']}",
        f"👤 Жалобщик: {entry['from_uid']}",
        f"📋 Причина жалобы: {entry.get('reason', '?')}",
        f"",
        f"Решение: {entry.get('admin_action', '?')}",
        f"Принял: {'AI' if decided == 'ai' else 'Админ' if decided == 'admin' else 'Авто'}",
    ]
    if confidence is not None:
        lines.append(f"Уверенность AI: {confidence:.0%}")
    if entry.get("ai_reasoning"):
        lines.append(f"\n💬 AI: {entry['ai_reasoning']}")
    if entry.get("decision_details"):
        lines.append(f"📝 Детали: {entry['decision_details']}")
    chat_log = entry.get("chat_log") or ""
    if chat_log:
        lines.append(f"\n📄 Переписка:\n{chat_log[:300]}")

    date = entry["created_at"].strftime("%d.%m.%Y %H:%M") if entry.get("created_at") else "?"
    lines.append(f"\n🕐 {date}")

    return "\n".join(lines)
