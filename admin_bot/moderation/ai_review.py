"""
Admin Bot — AI-модерация жалоб.
Скопировано из moderation.py (оригинал НЕ удалён — check_message остаётся в bot.py).
"""

import json
import logging
from datetime import datetime, timedelta

from ai_utils import get_ai_answer
from locales import t

logger = logging.getLogger("admin-bot")

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

_MODERATION_MODEL = "openai/gpt-4o-mini"


def _parse_json_response(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
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
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        logger.error(f"Failed to parse AI response: {text[:200]}")
        return None


async def ai_review_complaint(complaint_id: int, db_pool, bot, admin_id) -> dict | None:
    """AI анализирует жалобу и принимает решение."""
    async with db_pool.acquire() as conn:
        complaint = await conn.fetchrow("SELECT * FROM complaints_log WHERE id=$1", complaint_id)
    if not complaint:
        return None

    accused_uid = complaint["to_uid"]
    reporter_uid = complaint["from_uid"]
    chat_log = complaint.get("chat_log", "")
    reason = complaint.get("reason", "")

    async with db_pool.acquire() as conn:
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
        f"ЖАЛОБА #{complaint_id}\nПричина: {reason}\n\n"
        f"ИСТОРИЯ ОБВИНЯЕМОГО:\n{history_text}\n\n"
        f"ПЕРЕПИСКА:\n{chat_log[:2000]}"
    )

    raw = await get_ai_answer(user_prompt, MODERATION_SYSTEM_PROMPT, _MODERATION_MODEL)
    result = _parse_json_response(raw)

    if not result or "decision" not in result:
        logger.warning(f"AI moderation failed for complaint #{complaint_id}, falling back to admin")
        return None

    decision = result["decision"]
    confidence = float(result.get("confidence", 0.5))
    reason_short = result.get("reason_short", "Нарушение правил")
    reason_detailed = result.get("reason_detailed", "")
    notify_user = result.get("notify_user", True)

    min_confidence = 0.85 if decision == "ban_perm" else 0.7
    if confidence < min_confidence or decision == "escalate":
        await _escalate_to_admin(complaint_id, complaint, result, bot, admin_id, db_pool)
        return result

    await _apply_decision(
        complaint_id, accused_uid, reporter_uid,
        decision, reason_short, reason_detailed, confidence, notify_user,
        bot, admin_id, db_pool,
    )
    return result


async def _escalate_to_admin(complaint_id, complaint, ai_result, bot, admin_id, db_pool):
    async with db_pool.acquire() as conn:
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
        await bot.send_message(
            admin_id,
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
    complaint_id, accused_uid, reporter_uid,
    decision, reason_short, reason_detailed, confidence, notify_user,
    bot, admin_id, db_pool,
):
    action_text = {
        "warn": "Предупреждение (AI)", "ban_3h": "Бан 3ч (AI)", "ban_24h": "Бан 24ч (AI)",
        "ban_perm": "Перм бан (AI)", "shadow_ban": "Shadow ban (AI)", "dismiss": "Отклонена (AI)",
    }.get(decision, decision)

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE complaints_log SET reviewed=TRUE, admin_action=$1, decided_by='ai', "
            "ai_reasoning=$2, ai_confidence=$3, decision_details=$4 WHERE id=$5",
            action_text, reason_short, confidence, reason_detailed, complaint_id,
        )

    lang = "ru"
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT lang FROM users WHERE uid=$1", accused_uid)
            if row and row["lang"]:
                lang = row["lang"]
    except Exception:
        pass

    if decision == "warn":
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET warn_count=warn_count+1 WHERE uid=$1", accused_uid)
        if notify_user:
            try:
                await bot.send_message(accused_uid, t(lang, "mod_warn", reason=reason_short))
            except Exception:
                pass
    elif decision == "ban_3h":
        until = (datetime.now() + timedelta(hours=3)).isoformat()
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, accused_uid)
        if notify_user:
            try:
                await bot.send_message(accused_uid, t(lang, "mod_ban3h", reason=reason_short))
            except Exception:
                pass
    elif decision == "ban_24h":
        until = (datetime.now() + timedelta(hours=24)).isoformat()
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, accused_uid)
        if notify_user:
            try:
                await bot.send_message(accused_uid, t(lang, "mod_ban24h", reason=reason_short))
            except Exception:
                pass
    elif decision == "ban_perm":
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until='permanent' WHERE uid=$1", accused_uid)
        if notify_user:
            try:
                await bot.send_message(accused_uid, t(lang, "mod_banperm", reason=reason_short))
            except Exception:
                pass
    elif decision == "shadow_ban":
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET shadow_ban=TRUE WHERE uid=$1", accused_uid)
    elif decision == "dismiss":
        pass

    try:
        await bot.send_message(
            admin_id,
            f"🤖 AI решение по жалобе #{complaint_id}:\n{action_text} ({confidence:.0%})\n💬 {reason_detailed}"
        )
    except Exception:
        pass
