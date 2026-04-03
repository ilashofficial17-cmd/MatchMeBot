"""
Admin Bot — саппорт-система: баг-репорты и обжалования банов.
Reply keyboard навигация для юзеров. Inline только для админ-действий.
"""

import logging

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import ADMIN_ID, BOT_USERNAME, CHANNEL_ID
import admin_bot.db as _db
from admin_bot.keyboards import kb_support_user
from locales import t

logger = logging.getLogger("admin-bot")

router = Router()


class SupportState(StatesGroup):
    waiting_bug_text = State()
    waiting_appeal_text = State()
    waiting_admin_reply = State()


# ====================== USER REPLY BUTTONS ======================
@router.message(F.text.in_({
    t("ru", "support_bug_btn"),
    t("en", "support_bug_btn"),
    t("es", "support_bug_btn"),
}))
async def btn_bug_report(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid == ADMIN_ID:
        return
    lang = await _get_user_lang(uid)
    await state.set_state(SupportState.waiting_bug_text)
    await message.answer(t(lang, "support_describe_bug"))


@router.message(F.text.in_({
    t("ru", "support_appeal_btn"),
    t("en", "support_appeal_btn"),
    t("es", "support_appeal_btn"),
}))
async def btn_ban_appeal(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid == ADMIN_ID:
        return
    lang = await _get_user_lang(uid)
    async with _db.db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ban_until FROM users WHERE uid=$1", uid)
    if not row or not row["ban_until"]:
        await message.answer(t(lang, "support_not_banned"))
    else:
        await state.set_state(SupportState.waiting_appeal_text)
        await message.answer(t(lang, "support_describe_appeal"))


@router.message(F.text.in_({
    t("ru", "support_my_tickets_btn"),
    t("en", "support_my_tickets_btn"),
    t("es", "support_my_tickets_btn"),
}))
async def btn_my_tickets(message: types.Message):
    uid = message.from_user.id
    if uid == ADMIN_ID:
        return
    lang = await _get_user_lang(uid)
    async with _db.db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, type, status, message, created_at, admin_reply "
            "FROM support_tickets WHERE uid=$1 ORDER BY created_at DESC LIMIT 10",
            uid,
        )
    if not rows:
        await message.answer(t(lang, "support_no_tickets"), reply_markup=kb_support_user(lang))
        return
    text = ""
    for r in rows:
        icon = "🐛" if r["type"] == "bug" else "🔓"
        status_icon = "✅" if r["status"] == "resolved" else "❌" if r["status"] == "rejected" else "⏳"
        date = r["created_at"].strftime("%d.%m %H:%M")
        preview = r["message"][:40].replace("\n", " ")
        text += f"{icon} #{r['id']} {status_icon} — {preview}...\n   🕐 {date}\n"
        if r.get("admin_reply"):
            text += f"   💬 {r['admin_reply'][:50]}...\n"
        text += "\n"
    await message.answer(
        t(lang, "support_ticket_list") + "\n\n" + text,
        reply_markup=kb_support_user(lang),
    )


# ====================== LEGACY SUPPORT CALLBACKS (backward compat) ======================
@router.callback_query(F.data.startswith("support:"), StateFilter("*"))
async def support_callback(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    action = callback.data.split(":", 1)[1]

    if action == "bug":
        lang = await _get_user_lang(uid)
        await state.set_state(SupportState.waiting_bug_text)
        await callback.message.answer(t(lang, "support_describe_bug"))

    elif action == "ban_appeal":
        lang = await _get_user_lang(uid)
        async with _db.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT ban_until FROM users WHERE uid=$1", uid)
        if not row or not row["ban_until"]:
            await callback.message.answer(t(lang, "support_not_banned"))
        else:
            await state.set_state(SupportState.waiting_appeal_text)
            await callback.message.answer(t(lang, "support_describe_appeal"))

    await callback.answer()


# ====================== FSM: получение текста ======================
@router.message(StateFilter(SupportState.waiting_bug_text))
async def receive_bug_report(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_user_lang(uid)
    text = (message.text or "").strip()
    if not text:
        await message.answer(t(lang, "support_describe_bug"))
        return
    username = message.from_user.username or ""
    await state.clear()

    async with _db.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO support_tickets (uid, username, type, message) "
            "VALUES ($1, $2, 'bug', $3) RETURNING id",
            uid, username, text[:2000],
        )
    ticket_id = row["id"]
    await message.answer(t(lang, "support_ticket_created", id=ticket_id), reply_markup=kb_support_user(lang))

    from admin_bot.main import admin_bot
    try:
        await admin_bot.send_message(
            ADMIN_ID,
            f"🐛 Новый баг-репорт #{ticket_id} от @{username} (uid={uid}):\n{text[:500]}"
        )
    except Exception:
        pass


@router.message(StateFilter(SupportState.waiting_appeal_text))
async def receive_ban_appeal(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    lang = await _get_user_lang(uid)
    text = (message.text or "").strip()
    if not text:
        await message.answer(t(lang, "support_describe_appeal"))
        return
    username = message.from_user.username or ""
    await state.clear()

    async with _db.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO support_tickets (uid, username, type, message) "
            "VALUES ($1, $2, 'ban_appeal', $3) RETURNING id",
            uid, username, text[:2000],
        )
    ticket_id = row["id"]
    await message.answer(t(lang, "support_appeal_created", id=ticket_id), reply_markup=kb_support_user(lang))

    from admin_bot.main import admin_bot
    try:
        await admin_bot.send_message(
            ADMIN_ID,
            f"🔓 Запрос на разбан #{ticket_id} от uid={uid} (@{username}):\n{text[:500]}"
        )
    except Exception:
        pass


# ====================== ADMIN SUPPORT VIEW ======================
async def show_admin_tickets(callback: types.CallbackQuery):
    """Список открытых тикетов (вызывается из admin:support callback)."""
    async with _db.db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, uid, username, type, message, created_at "
            "FROM support_tickets WHERE status='open' ORDER BY created_at ASC LIMIT 20"
        )
    count = len(rows)
    if not rows:
        await callback.message.answer("📩 Саппорт: нет открытых тикетов.")
        return

    text = f"📩 Саппорт ({count} открытых)\n\n"
    buttons = []
    for r in rows:
        icon = "🐛" if r["type"] == "bug" else "🔓"
        username = r["username"] or str(r["uid"])
        preview = r["message"][:30].replace("\n", " ")
        text += f"#{r['id']} {icon} @{username} — {preview}...\n"
        buttons.append([InlineKeyboardButton(
            text=f"#{r['id']} {icon} @{username}",
            callback_data=f"spt:view:{r['id']}"
        )])
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


async def show_admin_tickets_msg(message: types.Message):
    """Список открытых тикетов (вызывается из reply-кнопки)."""
    async with _db.db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, uid, username, type, message, created_at "
            "FROM support_tickets WHERE status='open' ORDER BY created_at ASC LIMIT 20"
        )
    count = len(rows)
    if not rows:
        await message.answer("📩 Саппорт: нет открытых тикетов.")
        return

    text = f"📩 Саппорт ({count} открытых)\n\n"
    buttons = []
    for r in rows:
        icon = "🐛" if r["type"] == "bug" else "🔓"
        username = r["username"] or str(r["uid"])
        preview = r["message"][:30].replace("\n", " ")
        text += f"#{r['id']} {icon} @{username} — {preview}...\n"
        buttons.append([InlineKeyboardButton(
            text=f"#{r['id']} {icon} @{username}",
            callback_data=f"spt:view:{r['id']}"
        )])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("spt:"), StateFilter("*"))
async def support_admin_action(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    ticket_id = int(parts[2])

    if action == "view":
        async with _db.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM support_tickets WHERE id=$1", ticket_id)
        if not row:
            await callback.message.answer("Тикет не найден.")
            await callback.answer()
            return
        icon = "🐛" if row["type"] == "bug" else "🔓"
        username = row["username"] or str(row["uid"])
        text = (
            f"{icon} Тикет #{row['id']}\n\n"
            f"👤 @{username} (uid={row['uid']})\n"
            f"Тип: {row['type']}\n"
            f"🕐 {row['created_at'].strftime('%d.%m %H:%M')}\n\n"
            f"💬 {row['message']}"
        )
        buttons = [
            [InlineKeyboardButton(text="✅ Решено", callback_data=f"spt:resolve:{ticket_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"spt:reject:{ticket_id}")],
            [InlineKeyboardButton(text="💬 Ответить", callback_data=f"spt:reply:{ticket_id}")],
        ]
        if row["type"] == "ban_appeal":
            buttons.append([InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"spt:unban:{ticket_id}")])
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    elif action == "resolve":
        async with _db.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT uid FROM support_tickets WHERE id=$1", ticket_id)
            await conn.execute(
                "UPDATE support_tickets SET status='resolved', resolved_at=NOW() WHERE id=$1", ticket_id
            )
        await callback.message.answer(f"✅ Тикет #{ticket_id} решён.")
        if row:
            from admin_bot.main import main_bot
            try:
                lang = await _get_user_lang(row["uid"])
                await main_bot.send_message(row["uid"], t(lang, "support_resolved", id=ticket_id))
            except Exception:
                pass

    elif action == "reject":
        async with _db.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT uid FROM support_tickets WHERE id=$1", ticket_id)
            await conn.execute(
                "UPDATE support_tickets SET status='rejected', resolved_at=NOW() WHERE id=$1", ticket_id
            )
        await callback.message.answer(f"❌ Тикет #{ticket_id} отклонён.")
        if row:
            from admin_bot.main import main_bot
            try:
                lang = await _get_user_lang(row["uid"])
                await main_bot.send_message(row["uid"], t(lang, "support_rejected", id=ticket_id))
            except Exception:
                pass

    elif action == "reply":
        from admin_bot.admin.router import AdminState
        await state.set_state(AdminState.waiting_support_reply)
        await state.update_data(reply_ticket_id=ticket_id)
        await callback.message.answer(f"💬 Введи ответ для тикета #{ticket_id}:")

    elif action == "unban":
        async with _db.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT uid FROM support_tickets WHERE id=$1", ticket_id)
            if row:
                await conn.execute("UPDATE users SET ban_until=NULL WHERE uid=$1", row["uid"])
            await conn.execute(
                "UPDATE support_tickets SET status='resolved', resolved_at=NOW() WHERE id=$1", ticket_id
            )
        await callback.message.answer(f"🔓 Разбан + тикет #{ticket_id} решён.")
        if row:
            from admin_bot.main import main_bot
            try:
                lang = await _get_user_lang(row["uid"])
                await main_bot.send_message(row["uid"], t(lang, "support_unbanned"))
            except Exception:
                pass

    await callback.answer()


async def handle_support_reply(message: types.Message, state: FSMContext):
    """Вызывается из main для обработки ответа админа на тикет."""
    data = await state.get_data()
    ticket_id = data.get("reply_ticket_id")
    if not ticket_id:
        await state.clear()
        return
    await state.clear()

    reply_text = (message.text or "").strip()
    if not reply_text:
        await message.answer("Пустой ответ, попробуй заново.")
        return

    async with _db.db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT uid FROM support_tickets WHERE id=$1", ticket_id)
        await conn.execute(
            "UPDATE support_tickets SET admin_reply=$1 WHERE id=$2",
            reply_text[:2000], ticket_id,
        )
    await message.answer(f"✅ Ответ отправлен на тикет #{ticket_id}.")

    if row:
        from admin_bot.main import main_bot
        try:
            lang = await _get_user_lang(row["uid"])
            await main_bot.send_message(
                row["uid"], t(lang, "support_reply", id=ticket_id, text=reply_text)
            )
        except Exception:
            pass


async def _get_user_lang(uid: int) -> str:
    try:
        async with _db.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT lang FROM users WHERE uid=$1", uid)
        return (row["lang"] or "ru") if row and row.get("lang") else "ru"
    except Exception:
        return "ru"
