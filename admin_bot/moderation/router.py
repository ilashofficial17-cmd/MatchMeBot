"""
Admin Bot — модерация: жалобы (admin:complaints) + cadm:* хэндлеры.
Перенесено из admin.py.
"""

import logging
from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import ADMIN_ID
import admin_bot.db as _db
from locales import t

logger = logging.getLogger("admin-bot")

router = Router()


async def _get_user(uid):
    async with _db.db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
    return dict(row) if row else None


async def _get_lang(uid: int) -> str:
    u = await _get_user(uid)
    return (u.get("lang") or "ru") if u else "ru"


async def show_complaints(callback: types.CallbackQuery):
    """Показать список нерассмотренных жалоб (вызывается из admin:complaints)."""
    from admin_bot.admin.router import kb_complaint_action
    async with _db.db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM complaints_log WHERE reviewed=FALSE ORDER BY created_at ASC LIMIT 5")
    if not rows:
        await callback.message.answer("✅ Нет жалоб.")
    else:
        for r in rows:
            ru = await _get_user(r["from_uid"])
            pu = await _get_user(r["to_uid"])
            has_log = bool(r.get("chat_log"))
            stop_words_found = bool(r.get("stop_words_found"))
            await callback.message.answer(
                f"🚩 Жалоба #{r['id']}\n\n"
                f"👤 От: {r['from_uid']} ({ru.get('name','?') if ru else '?'})\n"
                f"👤 На: {r['to_uid']} ({pu.get('name','?') if pu else '?'})\n"
                f"📋 {r['reason']} | 🕐 {r['created_at'].strftime('%d.%m %H:%M')}",
                reply_markup=kb_complaint_action(r["id"], r["to_uid"], r["from_uid"], has_log, stop_words_found)
            )


@router.callback_query(F.data.startswith("cadm:"), StateFilter("*"))
async def admin_complaint_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    complaint_id = int(parts[2])
    target_uid = int(parts[3]) if parts[3] != "0" else None

    from admin_bot.main import main_bot

    async def mark_reviewed(action_text):
        async with _db.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE complaints_log SET reviewed=TRUE, admin_action=$1, decided_by='admin' WHERE id=$2",
                action_text, complaint_id
            )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if action == "ban3" and target_uid:
        until = (datetime.now() + timedelta(hours=3)).isoformat()
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, target_uid)
        await mark_reviewed("Бан 3ч")
        await callback.message.answer(f"✅ Бан 3ч → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_ban3h_complaint"))
        except Exception:
            pass

    elif action == "ban24" and target_uid:
        until = (datetime.now() + timedelta(hours=24)).isoformat()
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, target_uid)
        await mark_reviewed("Бан 24ч")
        await callback.message.answer(f"✅ Бан 24ч → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_ban24h_complaint"))
        except Exception:
            pass

    elif action == "banperm" and target_uid:
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until='permanent' WHERE uid=$1", target_uid)
        await mark_reviewed("Перм бан")
        await callback.message.answer(f"✅ Перм бан → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_banperm_user"))
        except Exception:
            pass

    elif action == "warn" and target_uid:
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET warn_count=warn_count+1 WHERE uid=$1", target_uid)
        await mark_reviewed("Предупреждение")
        await callback.message.answer(f"✅ Предупреждение → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_warn_next_ban"))
        except Exception:
            pass

    elif action == "warnrep" and target_uid:
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET warn_count=warn_count+1 WHERE uid=$1", target_uid)
        await mark_reviewed("Предупреждение жалобщику")
        await callback.message.answer(f"✅ Ложная жалоба. Предупреждение → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_false_complaint"))
        except Exception:
            pass

    elif action == "banrep" and target_uid:
        until = (datetime.now() + timedelta(hours=24)).isoformat()
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, target_uid)
        await mark_reviewed("Бан жалобщику")
        await callback.message.answer(f"✅ Ложная жалоба. Бан 24ч → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_ban_abuse"))
        except Exception:
            pass

    elif action == "shadow" and target_uid:
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET shadow_ban=TRUE WHERE uid=$1", target_uid)
        await mark_reviewed("Shadow ban")
        await callback.message.answer(f"👻 Shadow ban → {target_uid}")

    elif action == "dismiss":
        await mark_reviewed("Отклонена")
        await callback.message.answer(f"✅ Жалоба #{complaint_id} отклонена.")

    await callback.answer("✅ Готово")
