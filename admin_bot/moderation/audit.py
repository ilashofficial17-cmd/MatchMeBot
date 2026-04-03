"""
Admin Bot — аудит-лог: audit:* хэндлеры + get_audit_log, format_*.
Перенесено из admin.py + moderation.py.
"""

import logging

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import ADMIN_ID
from admin_bot.db import db_pool

logger = logging.getLogger("admin-bot")

router = Router()


async def get_audit_log(limit: int = 10, offset: int = 0) -> list:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, to_uid, from_uid, reason, admin_action, decided_by, "
            "ai_reasoning, ai_confidence, decision_details, created_at "
            "FROM complaints_log WHERE reviewed=TRUE "
            "ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
    return [dict(r) for r in rows]


async def get_audit_total() -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=TRUE")


async def get_decision_detail(complaint_id: int) -> dict | None:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM complaints_log WHERE id=$1", complaint_id)
    return dict(row) if row else None


def format_audit_entry(entry: dict) -> str:
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
    decided = entry.get("decided_by", "?")
    icon = "🤖" if decided == "ai" else "👤" if decided == "admin" else "⚙️"
    confidence = entry.get("ai_confidence")
    lines = [
        f"{icon} Жалоба #{entry['id']}", "",
        f"👤 Обвиняемый: {entry['to_uid']}",
        f"👤 Жалобщик: {entry['from_uid']}",
        f"📋 Причина жалобы: {entry.get('reason', '?')}", "",
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


async def show_audit_log(callback: types.CallbackQuery, offset: int = 0):
    """Показать аудит-лог (вызывается из admin:audit)."""
    total = await get_audit_total()
    entries = await get_audit_log(limit=10, offset=offset)
    if not entries:
        await callback.message.answer("📋 Аудит-лог пуст.")
    else:
        text = f"📋 Аудит-лог ({total} решений):\n\n"
        text += "\n\n".join(format_audit_entry(e) for e in entries)
        buttons = []
        for e in entries:
            buttons.append([InlineKeyboardButton(
                text=f"#{e['id']} — подробнее",
                callback_data=f"audit:detail:{e['id']}"
            )])
        if offset + 10 < total:
            buttons.append([InlineKeyboardButton(text="➡️ Ещё", callback_data=f"audit:page:{offset+10}")])
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("audit:"), StateFilter("*"))
async def audit_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    if parts[1] == "detail":
        complaint_id = int(parts[2])
        entry = await get_decision_detail(complaint_id)
        if entry:
            await callback.message.answer(format_decision_detail(entry))
        else:
            await callback.message.answer("Запись не найдена.")
    elif parts[1] == "page":
        offset = int(parts[2])
        await show_audit_log(callback, offset=offset)
    await callback.answer()
