"""
Admin Bot — управление пользователями: uadm:* хэндлеры.
Перенесено из admin.py. Кик — через admin_commands вместо in-memory.
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


async def _get_lang(uid: int) -> str:
    async with _db.db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lang FROM users WHERE uid=$1", uid)
    return (row["lang"] or "ru") if row and row.get("lang") else "ru"


@router.callback_query(F.data.startswith("uadm:"), StateFilter("*"))
async def admin_user_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    target_uid = int(parts[2])

    from admin_bot.main import main_bot

    if action == "ban3":
        until = (datetime.now() + timedelta(hours=3)).isoformat()
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, target_uid)
        await callback.answer("✅ Бан 3ч")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_ban3h"))
        except Exception:
            pass

    elif action == "ban24":
        until = (datetime.now() + timedelta(hours=24)).isoformat()
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=$1 WHERE uid=$2", until, target_uid)
        await callback.answer("✅ Бан 24ч")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_ban24h"))
        except Exception:
            pass

    elif action == "banperm":
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until='permanent' WHERE uid=$1", target_uid)
        await callback.answer("✅ Перм бан")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_banperm_user"))
        except Exception:
            pass

    elif action == "unban":
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET ban_until=NULL WHERE uid=$1", target_uid)
        await callback.answer("✅ Разбан")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_unban"))
        except Exception:
            pass

    elif action == "warn":
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET warn_count=warn_count+1 WHERE uid=$1", target_uid)
        await callback.answer("✅ Предупреждение")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_warn_user"))
        except Exception:
            pass

    elif action == "kick":
        # Кик через admin_commands — основной бот подхватит за 60с
        async with _db.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO admin_commands (command, target_uid) VALUES ('kick', $1)",
                target_uid,
            )
        await callback.answer("✅ Кик отправлен (до 60с)")
        await callback.message.answer(f"👢 Команда кика для {target_uid} отправлена. Основной бот исполнит в течение 60 секунд.")

    elif action == "premium":
        until = (datetime.now() + timedelta(days=30)).isoformat()
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET premium_until=$1 WHERE uid=$2", until, target_uid)
        await callback.answer("✅ Premium 30д")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_premium_granted"))
        except Exception:
            pass

    elif action == "unpremium":
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET premium_until=NULL WHERE uid=$1", target_uid)
        await callback.answer("✅ Premium забран")
        try:
            u_lang = await _get_lang(target_uid)
            await main_bot.send_message(target_uid, t(u_lang, "adm_premium_removed"))
        except Exception:
            pass

    elif action == "shadowtoggle":
        async with _db.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT shadow_ban FROM users WHERE uid=$1", target_uid)
        current = row["shadow_ban"] if row else False
        async with _db.db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET shadow_ban=$1 WHERE uid=$2", not current, target_uid)
        if current:
            await callback.answer("✅ Shadow ban снят")
            await callback.message.answer(f"👻 Shadow ban снят с {target_uid}")
        else:
            await callback.answer("✅ Shadow ban установлен")
            await callback.message.answer(f"👻 Shadow ban установлен для {target_uid}")

    elif action == "fulldelete":
        await callback.message.answer(
            f"⚠️ Удалить пользователя {target_uid} полностью?\n"
            f"Это удалит ВСЕ данные из БД. Пользователь сможет зарегистрироваться заново.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, удалить полностью", callback_data=f"uadm:confirmdelete:{target_uid}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="noop")],
            ])
        )
        await callback.answer()

    elif action == "confirmdelete":
        # Kick from chat via admin_commands
        async with _db.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO admin_commands (command, target_uid) VALUES ('kick', $1)",
                target_uid,
            )
            await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1 OR uid2=$1", target_uid)
            await conn.execute("DELETE FROM complaints_log WHERE from_uid=$1 OR to_uid=$1", target_uid)
            await conn.execute("DELETE FROM users WHERE uid=$1", target_uid)
        await callback.message.answer(f"🗑 Пользователь {target_uid} полностью удалён из БД.")
        await callback.answer("✅ Удалён")
