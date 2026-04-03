"""
Admin Bot — главная админ-панель: /admin, stats, retention, online, find, notify_update.
Перенесено из admin.py.
"""

import asyncio
import logging

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import ADMIN_ID
from admin_bot.db import db_pool, get_stat

logger = logging.getLogger("admin-bot")

router = Router()

MODE_NAMES = {"simple": "Общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}


class AdminState(StatesGroup):
    waiting_user_id = State()
    waiting_char_gif = State()
    waiting_support_reply = State()


async def get_pending_complaints():
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE") or 0


async def get_open_tickets():
    try:
        async with db_pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM support_tickets WHERE status='open'") or 0
    except Exception:
        return 0


async def kb_admin_main():
    pending = await get_pending_complaints()
    badge = f" ({pending})" if pending > 0 else ""
    tickets = await get_open_tickets()
    ticket_badge = f" ({tickets})" if tickets > 0 else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📈 Retention", callback_data="admin:retention")],
        [InlineKeyboardButton(text=f"🚩 Жалобы{badge}", callback_data="admin:complaints")],
        [InlineKeyboardButton(text="📋 Аудит-лог", callback_data="admin:audit")],
        [InlineKeyboardButton(text="👥 Онлайн", callback_data="admin:online")],
        [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin:find")],
        [InlineKeyboardButton(text="🔧 Уведомить об обновлении", callback_data="admin:notify_update")],
        [InlineKeyboardButton(text="🖼 Медиа персонажей", callback_data="admin:char_media")],
        [InlineKeyboardButton(text="📢 Маркетинг", callback_data="admin:marketing")],
        [InlineKeyboardButton(text=f"📩 Саппорт{ticket_badge}", callback_data="admin:support")],
    ])


def kb_user_actions(target_uid, is_shadow=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Бан 3ч", callback_data=f"uadm:ban3:{target_uid}"),
         InlineKeyboardButton(text="🚫 Бан 24ч", callback_data=f"uadm:ban24:{target_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан", callback_data=f"uadm:banperm:{target_uid}"),
         InlineKeyboardButton(text="✅ Разбан", callback_data=f"uadm:unban:{target_uid}")],
        [InlineKeyboardButton(
            text="👻 Снять shadow" if is_shadow else "👻 Shadow ban",
            callback_data=f"uadm:shadowtoggle:{target_uid}",
        )],
        [InlineKeyboardButton(text="⚠️ Предупреждение", callback_data=f"uadm:warn:{target_uid}"),
         InlineKeyboardButton(text="👢 Кик", callback_data=f"uadm:kick:{target_uid}")],
        [InlineKeyboardButton(text="💎 Дать Premium", callback_data=f"uadm:premium:{target_uid}"),
         InlineKeyboardButton(text="💎 Забрать Premium", callback_data=f"uadm:unpremium:{target_uid}")],
        [InlineKeyboardButton(text="🗑 Удалить полностью", callback_data=f"uadm:fulldelete:{target_uid}")],
    ])


def kb_complaint_action(complaint_id, accused_uid, reporter_uid, has_log=False, stop_words=False):
    sw_text = "⚠️ Стоп-слова: ДА" if stop_words else "Стоп-слова: нет"
    buttons = [[InlineKeyboardButton(text=sw_text, callback_data="noop")]]
    if has_log:
        buttons.append([InlineKeyboardButton(text="📄 Показать лог", callback_data=f"clog:show:{complaint_id}")])
    buttons += [
        [InlineKeyboardButton(text="🚫 Бан 3ч", callback_data=f"cadm:ban3:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="🚫 Бан 24ч", callback_data=f"cadm:ban24:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан", callback_data=f"cadm:banperm:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение", callback_data=f"cadm:warn:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупредить жалобщика", callback_data=f"cadm:warnrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="🚫 Бан жалобщику", callback_data=f"cadm:banrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="👻 Shadow ban", callback_data=f"cadm:shadow:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"cadm:dismiss:{complaint_id}:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ====================== /admin ======================
@router.message(Command("admin"), StateFilter("*"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛡 Админ панель MatchMe", reply_markup=await kb_admin_main())


@router.callback_query(F.data.startswith("admin:"), StateFilter("*"))
async def admin_actions(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]

    if action == "stats":
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE ban_until IS NOT NULL")
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
            total_complaints = await conn.fetchval("SELECT COUNT(*) FROM complaints_log")
            pending = await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE")
        online_now = await get_stat("online_pairs", 0)
        in_search = await get_stat("searching_count", 0)
        ai_sessions = await get_stat("ai_sessions_count", 0)
        await callback.message.answer(
            f"📊 Статистика MatchMe:\n\n"
            f"👥 Всего: {total}\n"
            f"🟢 За 24ч: {today}\n"
            f"⭐ Premium: {premiums}\n"
            f"💬 В чатах: {online_now} пар\n"
            f"🤖 С ИИ: {ai_sessions}\n"
            f"🔍 В поиске: {in_search}\n"
            f"🚫 Забанено: {banned}\n"
            f"🚩 Жалоб: {total_complaints} (⏳{pending})"
        )

    elif action == "retention":
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
            new_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE") or 0
            new_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'") or 0
            d1 = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 1 AND last_seen::date >= CURRENT_DATE"
            ) or 0
            d1_base = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 1"
            ) or 1
            d7 = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 7 AND last_seen > NOW() - INTERVAL '24 hours'"
            ) or 0
            d7_base = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 7"
            ) or 1
            d30 = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 30 AND last_seen > NOW() - INTERVAL '7 days'"
            ) or 0
            d30_base = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE - 30"
            ) or 1
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL") or 0
            avg_chats = await conn.fetchval("SELECT ROUND(AVG(total_chats)::numeric, 1) FROM users WHERE total_chats > 0") or 0
        prem_pct = round(premiums / max(total, 1) * 100, 1)
        await callback.message.answer(
            f"📈 Retention MatchMe:\n\n"
            f"📥 Новые сегодня: {new_today}\n"
            f"📥 Новые за неделю: {new_week}\n\n"
            f"📊 D1: {d1}/{d1_base} ({round(d1/max(d1_base,1)*100)}%)\n"
            f"📊 D7: {d7}/{d7_base} ({round(d7/max(d7_base,1)*100)}%)\n"
            f"📊 D30: {d30}/{d30_base} ({round(d30/max(d30_base,1)*100)}%)\n\n"
            f"💎 Premium конверсия: {premiums}/{total} ({prem_pct}%)\n"
            f"💬 Ср. чатов на юзера: {avg_chats}"
        )

    elif action == "complaints":
        # Delegate to moderation router
        from admin_bot.moderation.router import show_complaints
        await show_complaints(callback)

    elif action == "online":
        online_now = await get_stat("online_pairs", 0)
        ai_sessions = await get_stat("ai_sessions_count", 0)
        in_search = await get_stat("searching_count", 0)
        await callback.message.answer(
            f"👥 Онлайн:\n\n"
            f"💬 В чатах: {online_now} пар\n"
            f"🤖 С ИИ: {ai_sessions}\n"
            f"🔍 В поиске: {in_search}"
        )

    elif action == "find":
        await state.set_state(AdminState.waiting_user_id)
        await callback.message.answer("🔍 Введи Telegram ID:")

    elif action == "char_media":
        from admin_bot.admin.media import show_char_media_list
        await show_char_media_list(callback)

    elif action == "notify_update":
        await callback.message.answer(
            "Через сколько минут?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="1 мин", callback_data="upd:1"),
                 InlineKeyboardButton(text="2 мин", callback_data="upd:2")],
                [InlineKeyboardButton(text="5 мин", callback_data="upd:5"),
                 InlineKeyboardButton(text="🔴 Сейчас", callback_data="upd:0")],
            ])
        )

    elif action == "audit":
        from admin_bot.moderation.audit import show_audit_log
        await show_audit_log(callback)

    elif action == "marketing":
        from admin_bot.admin.marketing import show_marketing_menu
        await show_marketing_menu(callback)

    elif action == "support":
        from admin_bot.support.router import show_admin_tickets
        await show_admin_tickets(callback)

    elif action == "back":
        await callback.message.edit_text("🛡 Админ панель MatchMe", reply_markup=await kb_admin_main())

    await callback.answer()


@router.callback_query(F.data.startswith("upd:"), StateFilter("*"))
async def handle_update_notify(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    minutes = int(callback.data.split(":")[1])
    # Notify active users via main_bot
    from admin_bot.main import main_bot
    from locales import t
    sent = 0
    async with db_pool.acquire() as conn:
        all_users = await conn.fetch("SELECT uid, lang FROM users WHERE last_seen > NOW() - INTERVAL '7 days'")
    for row in all_users:
        try:
            u_lang = row.get("lang") or "ru"
            text = t(u_lang, "adm_update_now") if minutes == 0 else t(u_lang, "adm_update_soon", minutes=minutes)
            await main_bot.send_message(row["uid"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await callback.message.answer(f"✅ Отправлено {sent} пользователям.")
    await callback.answer()


@router.message(StateFilter(AdminState.waiting_user_id))
async def admin_find_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("❗ ID должен быть числом.")
        return
    await state.clear()
    target_uid = int(txt)
    async with db_pool.acquire() as conn:
        u = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", target_uid)
    if not u:
        await message.answer(f"❌ Пользователь {target_uid} не найден.")
        return
    u = dict(u)
    g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
    ban_status = "Нет"
    if u.get("ban_until"):
        ban_status = "Навсегда 🚫" if u["ban_until"] == "permanent" else f"до {str(u['ban_until'])[:16]}"
    prem_status = "Нет"
    if u.get("premium_until"):
        prem_status = "Вечный ⭐" if u["premium_until"] == "permanent" else f"до {str(u['premium_until'])[:16]} ⭐"
    is_shadow = u.get("shadow_ban", False)
    shadow_status = "👻 ДА" if is_shadow else "Нет"
    rating = u.get("total_rating", 0)
    total_rates = u.get("total_rates", 0)
    avg_rating = round(rating / max(total_rates, 1), 1)
    await message.answer(
        f"👤 {target_uid}:\n"
        f"Имя: {u.get('name','—')} | Возраст: {u.get('age','—')}\n"
        f"Пол: {g_map.get(u.get('gender',''), '—')} | Режим: {MODE_NAMES.get(u.get('mode',''), '—')}\n"
        f"⭐ Рейтинг: {avg_rating} | 👍 Лайков: {u.get('likes',0)}\n"
        f"💬 Чатов: {u.get('total_chats',0)} | 🚩 Жалоб: {u.get('complaints',0)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count',0)}\n"
        f"🚫 Бан: {ban_status} | 💎 Premium: {prem_status}\n"
        f"👻 Shadow ban: {shadow_status}",
        reply_markup=kb_user_actions(target_uid, is_shadow=is_shadow)
    )


@router.callback_query(F.data.startswith("clog:"), StateFilter("*"))
async def show_chat_log(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    complaint_id = int(parts[2])
    if action == "show":
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT chat_log FROM complaints_log WHERE id=$1", complaint_id)
        if not row or not row["chat_log"]:
            await callback.message.answer("📄 Пусто.")
        else:
            await callback.message.answer(
                f"📄 Жалоба #{complaint_id}:\n\n{row['chat_log']}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"clog:delete:{complaint_id}")]
                ])
            )
    elif action == "delete":
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data == "noop", StateFilter("*"))
async def noop_handler(callback: types.CallbackQuery):
    await callback.answer()
