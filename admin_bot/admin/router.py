"""
Admin Bot — главная админ-панель: reply-кнопки + inline действия.
Секции: Админка (🔍🚩📋📩🖼🔧), Аналитика (👥📈👁🤖⭐).
"""

import asyncio
import logging

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import ADMIN_ID
import admin_bot.db as _db
from admin_bot.db import get_stat

logger = logging.getLogger("admin-bot")

router = Router()

MODE_NAMES = {"simple": "Общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}

# AI_CHARACTERS для аналитики
try:
    from ai_characters import AI_CHARACTERS
except ImportError:
    AI_CHARACTERS = {}


class AdminState(StatesGroup):
    waiting_user_id = State()
    waiting_char_gif = State()
    waiting_support_reply = State()


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


# ====================== СЕКЦИЯ: АДМИНКА (reply buttons) ======================
@router.message(F.text == "🔍 Найти юзера")
async def btn_find_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.waiting_user_id)
    await message.answer("🔍 Введи Telegram ID:")


@router.message(F.text == "🚩 Жалобы")
async def btn_complaints(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    from admin_bot.moderation.router import show_complaints_msg
    await show_complaints_msg(message)


@router.message(F.text == "📋 Аудит")
async def btn_audit(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    from admin_bot.moderation.audit import show_audit_log_msg
    await show_audit_log_msg(message)


@router.message(F.text == "📩 Саппорт")
async def btn_support(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    from admin_bot.support.router import show_admin_tickets_msg
    await show_admin_tickets_msg(message)


@router.message(F.text == "🖼 Медиа")
async def btn_media(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    from admin_bot.admin.media import show_char_media_list_msg
    await show_char_media_list_msg(message)


@router.message(F.text == "🔧 Уведомление")
async def btn_notify(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "Через сколько минут?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1 мин", callback_data="upd:1"),
             InlineKeyboardButton(text="2 мин", callback_data="upd:2")],
            [InlineKeyboardButton(text="5 мин", callback_data="upd:5"),
             InlineKeyboardButton(text="🔴 Сейчас", callback_data="upd:0")],
        ])
    )


# ====================== СЕКЦИЯ: АНАЛИТИКА (reply buttons) ======================
@router.message(F.text == "👥 Общая")
async def btn_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with _db.db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
        banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE ban_until = 'permanent' OR (ban_until IS NOT NULL AND ban_until > NOW()::text)")
        premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until = 'permanent' OR (premium_until IS NOT NULL AND premium_until > NOW()::text)")
        total_complaints = await conn.fetchval("SELECT COUNT(*) FROM complaints_log")
        pending = await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE")
    online_now = await get_stat("online_pairs", 0)
    in_search = await get_stat("searching_count", 0)
    ai_sessions = await get_stat("ai_sessions_count", 0)
    await message.answer(
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


@router.message(F.text == "📈 Retention")
async def btn_retention(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with _db.db_pool.acquire() as conn:
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
        premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until = 'permanent' OR (premium_until IS NOT NULL AND premium_until > NOW()::text)") or 0
        avg_chats = await conn.fetchval("SELECT ROUND(AVG(total_chats)::numeric, 1) FROM users WHERE total_chats > 0") or 0
    prem_pct = round(premiums / max(total, 1) * 100, 1)
    await message.answer(
        f"📈 Retention MatchMe:\n\n"
        f"📥 Новые сегодня: {new_today}\n"
        f"📥 Новые за неделю: {new_week}\n\n"
        f"📊 D1: {d1}/{d1_base} ({round(d1/max(d1_base,1)*100)}%)\n"
        f"📊 D7: {d7}/{d7_base} ({round(d7/max(d7_base,1)*100)}%)\n"
        f"📊 D30: {d30}/{d30_base} ({round(d30/max(d30_base,1)*100)}%)\n\n"
        f"💎 Premium конверсия: {premiums}/{total} ({prem_pct}%)\n"
        f"💬 Ср. чатов на юзера: {avg_chats}"
    )


@router.message(F.text == "👁 Онлайн")
async def btn_online(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    online_now = await get_stat("online_pairs", 0)
    ai_sessions = await get_stat("ai_sessions_count", 0)
    in_search = await get_stat("searching_count", 0)
    await message.answer(
        f"👥 Онлайн:\n\n"
        f"💬 В чатах: {online_now} пар\n"
        f"🤖 С ИИ: {ai_sessions}\n"
        f"🔍 В поиске: {in_search}"
    )


@router.message(F.text == "🤖 AI чаты")
async def btn_ai_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    ai_sessions = await get_stat("ai_sessions_count", 0)
    async with _db.db_pool.acquire() as conn:
        total_ai_msgs = await conn.fetchval("SELECT COUNT(*) FROM ai_history WHERE role='user'") or 0
        unique_ai_users = await conn.fetchval("SELECT COUNT(DISTINCT uid) FROM ai_history") or 0
        char_stats = await conn.fetch("""
            SELECT character_id, COUNT(*) as msg_count, COUNT(DISTINCT uid) as user_count
            FROM ai_history WHERE role = 'user'
            GROUP BY character_id ORDER BY msg_count DESC
        """)
        char_stats_week = await conn.fetch("""
            SELECT character_id, COUNT(*) as msg_count, COUNT(DISTINCT uid) as user_count
            FROM ai_history WHERE role = 'user' AND created_at > NOW() - INTERVAL '7 days'
            GROUP BY character_id ORDER BY msg_count DESC
        """)
    text = f"🤖 Аналитика AI-чатов\n\n"
    text += f"Активных сессий: {ai_sessions}\n"
    text += f"Всего сообщений: {total_ai_msgs}\nУник. пользователей: {unique_ai_users}\n\n"
    if char_stats:
        text += "📊 Популярность (всё время):\n"
        for r in char_stats:
            cid = r["character_id"]
            char = AI_CHARACTERS.get(cid, {})
            emoji = char.get("emoji", "")
            name = cid.replace("_", " ").title()
            text += f"  {emoji} {name}: {r['msg_count']} сообщ. / {r['user_count']} юзеров\n"
    if char_stats_week:
        text += f"\n📊 За 7 дней:\n"
        for r in char_stats_week:
            cid = r["character_id"]
            char = AI_CHARACTERS.get(cid, {})
            emoji = char.get("emoji", "")
            name = cid.replace("_", " ").title()
            text += f"  {emoji} {name}: {r['msg_count']} сообщ. / {r['user_count']} юзеров\n"
    await message.answer(text)


@router.message(F.text == "⭐ Оценки")
async def btn_ratings(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with _db.db_pool.acquire() as conn:
        total_ratings = await conn.fetchval("SELECT COUNT(*) FROM chat_ratings") or 0
        avg_rating = await conn.fetchval("SELECT ROUND(AVG(stars)::numeric, 2) FROM chat_ratings") or 0
        dist = await conn.fetch("SELECT stars, COUNT(*) as cnt FROM chat_ratings GROUP BY stars ORDER BY stars")
        avg_week = await conn.fetchval(
            "SELECT ROUND(AVG(stars)::numeric, 2) FROM chat_ratings WHERE created_at > NOW() - INTERVAL '7 days'"
        ) or 0
        total_week = await conn.fetchval(
            "SELECT COUNT(*) FROM chat_ratings WHERE created_at > NOW() - INTERVAL '7 days'"
        ) or 0
    text = f"⭐ Оценки чатов\n\n"
    text += f"Всего оценок: {total_ratings}\nСредняя: {avg_rating} ⭐\n"
    text += f"За 7 дней: {total_week} оценок, ср. {avg_week} ⭐\n\n"
    if dist:
        text += "Распределение:\n"
        for r in dist:
            bar = "█" * r["cnt"] if r["cnt"] <= 20 else "█" * 20 + f"..{r['cnt']}"
            text += f"  {'⭐' * r['stars']}: {r['cnt']} {bar}\n"
    await message.answer(text)


# ====================== СЕКЦИЯ: АДМИНКА — стоп-слова (reply button) ======================
@router.message(F.text == "🚫 Стоп-слова")
async def btn_stopwords(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    from admin_bot.admin.stopwords import show_stopwords
    await show_stopwords(message)


# ====================== СЕКЦИЯ: АНАЛИТИКА — воронка (reply button) ======================
@router.message(F.text == "🔄 Воронка")
async def btn_funnel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await _show_funnel(message, days=7)


async def _show_funnel(target, days: int = 7):
    """Показать воронку регистрации. target — Message или CallbackQuery."""
    if days > 0:
        interval = f"NOW() - INTERVAL '{days} days'"
        period_label = f"за {days} дн."
    else:
        interval = "'1970-01-01'"
        period_label = "всё время"

    async with _db.db_pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE created_at > {interval}") or 0
        lang_sel = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE lang IS NOT NULL AND created_at > {interval}") or 0
        name_ent = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE name IS NOT NULL AND created_at > {interval}") or 0
        age_ent = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE age IS NOT NULL AND created_at > {interval}") or 0
        gender_sel = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE gender IS NOT NULL AND created_at > {interval}") or 0
        mode_sel = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE mode IS NOT NULL AND created_at > {interval}") or 0
        interests_sel = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE interests IS NOT NULL AND interests != '' AND created_at > {interval}") or 0
        first_chat = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE total_chats >= 1 AND created_at > {interval}") or 0

    def pct(v):
        return round(v / max(total, 1) * 100) if total else 0

    text = (
        f"🔄 Воронка регистрации ({period_label})\n\n"
        f"/start нажали: {total}\n"
        f"Язык выбрали: {lang_sel} ({pct(lang_sel)}%)\n"
        f"Имя ввели: {name_ent} ({pct(name_ent)}%)\n"
        f"Возраст: {age_ent} ({pct(age_ent)}%)\n"
        f"Пол: {gender_sel} ({pct(gender_sel)}%)\n"
        f"Режим: {mode_sel} ({pct(mode_sel)}%)\n"
        f"Интересы: {interests_sel} ({pct(interests_sel)}%)\n"
        f"Первый чат: {first_chat} ({pct(first_chat)}%)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="24ч", callback_data="funnel:1"),
            InlineKeyboardButton(text="7 дней", callback_data="funnel:7"),
            InlineKeyboardButton(text="30 дней", callback_data="funnel:30"),
            InlineKeyboardButton(text="Всё время", callback_data="funnel:0"),
        ]
    ])
    if isinstance(target, types.Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.answer(text, reply_markup=kb)


# ====================== СЕКЦИЯ: МАРКЕТИНГ — рассылка (reply button) ======================
@router.message(F.text == "📨 Рассылка")
async def btn_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    from admin_bot.admin.broadcast import show_broadcast_menu
    await show_broadcast_menu(message)


# ====================== LEGACY COMMANDS ======================
@router.message(Command("admin"), StateFilter("*"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    from admin_bot.keyboards import kb_main_menu
    from locales import t
    await message.answer(t("ru", "admin_main_menu"), reply_markup=kb_main_menu())


# ====================== INLINE CALLBACKS ======================
@router.callback_query(F.data.startswith("upd:"), StateFilter("*"))
async def handle_update_notify(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    minutes = int(callback.data.split(":")[1])
    from admin_bot.main import main_bot
    from locales import t
    sent = 0
    async with _db.db_pool.acquire() as conn:
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


@router.callback_query(F.data.startswith("funnel:"), StateFilter("*"))
async def funnel_period(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    days = int(callback.data.split(":")[1])
    await _show_funnel(callback, days=days)
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
    async with _db.db_pool.acquire() as conn:
        u = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", target_uid)
    if not u:
        await message.answer(f"❌ Пользователь {target_uid} не найден.")
        return
    u = dict(u)
    # Рейтинг из chat_ratings (avg stars) — в users таблице нет этих полей
    async with _db.db_pool.acquire() as conn:
        avg_rating = await conn.fetchval(
            "SELECT ROUND(AVG(stars)::numeric, 1) FROM chat_ratings WHERE partner_uid=$1",
            target_uid
        ) or 0
    g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
    ban_status = "Нет"
    if u.get("ban_until"):
        ban_status = "Навсегда 🚫" if u["ban_until"] == "permanent" else f"до {str(u['ban_until'])[:16]}"
    prem_status = "Нет"
    if u.get("premium_until"):
        prem_status = "Вечный ⭐" if u["premium_until"] == "permanent" else f"до {str(u['premium_until'])[:16]} ⭐"
    is_shadow = u.get("shadow_ban", False)
    shadow_status = "👻 ДА" if is_shadow else "Нет"
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
        async with _db.db_pool.acquire() as conn:
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
