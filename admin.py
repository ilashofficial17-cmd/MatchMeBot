import asyncio
import random
import logging
from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import AdminState
from keyboards import kb_main, kb_complaint_action, kb_user_actions
from locales import t
import moderation

MODE_NAMES = {"simple": "Общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}

router = Router()
logger = logging.getLogger("matchme")

REMINDER_TEMPLATES = {
    "ru": [
        "🔥 Сейчас онлайн {n} человек — самое время для поиска!",
        "💬 Давно не заходил? У нас новые пользователи ждут общения!",
        "🤖 Попробуй AI собеседника — {char} ждёт тебя!",
        "👋 Давно тебя не было! В MatchMe сейчас {n} человек онлайн. Заходи пообщаться!",
        "💬 {char} скучает по тебе! Зайди продолжить разговор.",
    ],
    "en": [
        "🔥 {n} people are online now — perfect time to find someone!",
        "💬 Haven't been here in a while? New users are waiting!",
        "🤖 Try an AI companion — {char} is waiting for you!",
        "👋 We miss you! {n} people are online on MatchMe right now. Come chat!",
        "💬 {char} misses you! Come back to continue the conversation.",
    ],
    "es": [
        "🔥 ¡{n} personas en línea ahora — el momento perfecto para buscar!",
        "💬 ¿Hace tiempo que no vienes? ¡Nuevos usuarios te esperan!",
        "🤖 Prueba un compañero IA — ¡{char} te espera!",
        "👋 ¡Te extrañamos! Hay {n} personas en línea en MatchMe. ¡Ven a chatear!",
        "💬 ¡{char} te extraña! Vuelve a continuar la conversación.",
    ],
}

# ====================== Инжектируемые зависимости ======================
_bot = None
_dp = None
_db_pool = None
_admin_id = None
_active_chats = None
_ai_sessions = None
_last_ai_msg = None
_pairing_lock = None
_get_all_queues = None
_chat_logs = None
_last_msg_time = None
_msg_count = None
_mutual_likes = None
_clear_chat_log = None
_get_user = None
_update_user = None
_increment_user = None
_get_rating = None
_remove_chat_from_db = None
_AI_CHARACTERS = None


def init(*, bot, dp, db_pool, admin_id, active_chats, ai_sessions, last_ai_msg,
         pairing_lock, get_all_queues, chat_logs, last_msg_time, msg_count,
         mutual_likes, clear_chat_log, get_user, update_user, increment_user,
         get_rating, remove_chat_from_db, AI_CHARACTERS):
    global _bot, _dp, _db_pool, _admin_id, _active_chats, _ai_sessions
    global _last_ai_msg, _pairing_lock, _get_all_queues, _chat_logs
    global _last_msg_time, _msg_count, _mutual_likes, _clear_chat_log
    global _get_user, _update_user, _increment_user, _get_rating
    global _remove_chat_from_db, _AI_CHARACTERS
    _bot = bot
    _dp = dp
    _db_pool = db_pool
    _admin_id = admin_id
    _active_chats = active_chats
    _ai_sessions = ai_sessions
    _last_ai_msg = last_ai_msg
    _pairing_lock = pairing_lock
    _get_all_queues = get_all_queues
    _chat_logs = chat_logs
    _last_msg_time = last_msg_time
    _msg_count = msg_count
    _mutual_likes = mutual_likes
    _clear_chat_log = clear_chat_log
    _get_user = get_user
    _update_user = update_user
    _increment_user = increment_user
    _get_rating = get_rating
    _remove_chat_from_db = remove_chat_from_db
    _AI_CHARACTERS = AI_CHARACTERS


async def _get_lang(uid: int) -> str:
    u = await _get_user(uid)
    return (u.get("lang") or "ru") if u else "ru"


async def get_pending_complaints():
    async with _db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE") or 0


async def kb_admin_main():
    pending = await get_pending_complaints()
    badge = f" ({pending})" if pending > 0 else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📈 Retention", callback_data="admin:retention")],
        [InlineKeyboardButton(text=f"🚩 Жалобы{badge}", callback_data="admin:complaints")],
        [InlineKeyboardButton(text="📋 Аудит-лог", callback_data="admin:audit")],
        [InlineKeyboardButton(text="👥 Онлайн", callback_data="admin:online")],
        [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin:find")],
        [InlineKeyboardButton(text="🔧 Уведомить об обновлении", callback_data="admin:notify_update")],
    ])


# ====================== АДМИН ПАНЕЛЬ ======================
@router.message(Command("admin"), StateFilter("*"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != _admin_id:
        return
    await message.answer("🛡 Админ панель MatchMe", reply_markup=await kb_admin_main())


@router.callback_query(F.data.startswith("admin:"), StateFilter("*"))
async def admin_actions(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]
    if action == "stats":
        async with _db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE ban_until IS NOT NULL")
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
            total_complaints = await conn.fetchval("SELECT COUNT(*) FROM complaints_log")
            pending = await conn.fetchval("SELECT COUNT(*) FROM complaints_log WHERE reviewed=FALSE")
        online_now = len(_active_chats) // 2
        in_search = sum(len(q) for q in _get_all_queues())
        await callback.message.answer(
            f"📊 Статистика MatchMe:\n\n"
            f"👥 Всего: {total}\n"
            f"🟢 За 24ч: {today}\n"
            f"⭐ Premium: {premiums}\n"
            f"💬 В чатах: {online_now} пар\n"
            f"🤖 С ИИ: {len(_ai_sessions)}\n"
            f"🔍 В поиске: {in_search}\n"
            f"🚫 Забанено: {banned}\n"
            f"🚩 Жалоб: {total_complaints} (⏳{pending})"
        )
    elif action == "retention":
        async with _db_pool.acquire() as conn:
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
        async with _db_pool.acquire() as conn:
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
    elif action == "online":
        await callback.message.answer(
            f"👥 Онлайн:\n\n"
            f"💬 В чатах: {len(_active_chats)//2} пар\n"
            f"🤖 С ИИ: {len(_ai_sessions)}\n"
            f"⚡ Анон: {sum(1 for q in _get_all_queues()[:1] for _ in q)}\n"
            f"🔍 В поиске: {sum(len(q) for q in _get_all_queues())}"
        )
    elif action == "find":
        await state.set_state(AdminState.waiting_user_id)
        await callback.message.answer("🔍 Введи Telegram ID:")
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
        total = await moderation.get_audit_total()
        entries = await moderation.get_audit_log(limit=10, offset=0)
        if not entries:
            await callback.message.answer("📋 Аудит-лог пуст.")
        else:
            text = f"📋 Аудит-лог ({total} решений):\n\n"
            text += "\n\n".join(moderation.format_audit_entry(e) for e in entries)
            buttons = []
            for e in entries:
                buttons.append([InlineKeyboardButton(
                    text=f"#{e['id']} — подробнее",
                    callback_data=f"audit:detail:{e['id']}"
                )])
            if total > 10:
                buttons.append([InlineKeyboardButton(text="➡️ Ещё", callback_data="audit:page:10")])
            await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("clog:"), StateFilter("*"))
async def show_chat_log(callback: types.CallbackQuery):
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    complaint_id = int(parts[2])
    if action == "show":
        async with _db_pool.acquire() as conn:
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
        try: await callback.message.delete()
        except Exception: pass
    await callback.answer()


@router.callback_query(F.data.startswith("upd:"), StateFilter("*"))
async def handle_update_notify(callback: types.CallbackQuery):
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    minutes = int(callback.data.split(":")[1])
    sent = 0
    for uid, partner in list(_active_chats.items()):
        if uid < partner:
            try:
                uid_lang = await _get_lang(uid)
                p_lang = await _get_lang(partner)
                uid_text = t(uid_lang, "adm_update_now") if minutes == 0 else t(uid_lang, "adm_update_soon", minutes=minutes)
                p_text = t(p_lang, "adm_update_now") if minutes == 0 else t(p_lang, "adm_update_soon", minutes=minutes)
                await _bot.send_message(uid, uid_text, reply_markup=kb_main(uid_lang))
                await _bot.send_message(partner, p_text, reply_markup=kb_main(p_lang))
                sent += 2
            except Exception: pass
    async with _db_pool.acquire() as conn:
        all_users = await conn.fetch("SELECT uid, lang FROM users WHERE last_seen > NOW() - INTERVAL '7 days'")
    active_uids = set(_active_chats.keys())
    for row in all_users:
        if row["uid"] in active_uids: continue
        try:
            u_lang = row.get("lang") or "ru"
            text = t(u_lang, "adm_update_now") if minutes == 0 else t(u_lang, "adm_update_soon", minutes=minutes)
            await _bot.send_message(row["uid"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception: pass
    await callback.message.answer(f"✅ Отправлено {sent} пользователям.")
    await callback.answer()


@router.message(StateFilter(AdminState.waiting_user_id))
async def admin_find_user(message: types.Message, state: FSMContext):
    if message.from_user.id != _admin_id:
        return
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("❗ ID должен быть числом.")
        return
    await state.clear()
    target_uid = int(txt)
    u = await _get_user(target_uid)
    if not u:
        await message.answer(f"❌ Пользователь {target_uid} не найден.")
        return
    g_map = {"male": "Парень 👨", "female": "Девушка 👩", "other": "Другое ⚧"}
    ban_status = "Нет"
    if u.get("ban_until"):
        ban_status = "Навсегда 🚫" if u["ban_until"] == "permanent" else f"до {u['ban_until'][:16]}"
    prem_status = "Нет"
    if u.get("premium_until"):
        prem_status = "Вечный ⭐" if u["premium_until"] == "permanent" else f"до {u['premium_until'][:16]} ⭐"
    in_chat = "✅" if target_uid in _active_chats else "❌"
    with_ai = "✅" if target_uid in _ai_sessions else "❌"
    in_queue = "✅" if any(target_uid in q for q in _get_all_queues()) else "❌"
    is_shadow = u.get("shadow_ban", False)
    shadow_status = "👻 ДА" if is_shadow else "Нет"
    await message.answer(
        f"👤 {target_uid}:\n"
        f"Имя: {u.get('name','—')} | Возраст: {u.get('age','—')}\n"
        f"Пол: {g_map.get(u.get('gender',''), '—')} | Режим: {MODE_NAMES.get(u.get('mode',''), '—')}\n"
        f"⭐ Рейтинг: {_get_rating(u)} | 👍 Лайков: {u.get('likes',0)}\n"
        f"💬 Чатов: {u.get('total_chats',0)} | 🚩 Жалоб: {u.get('complaints',0)}\n"
        f"⚠️ Предупреждений: {u.get('warn_count',0)}\n"
        f"🚫 Бан: {ban_status} | 💎 Premium: {prem_status}\n"
        f"👻 Shadow ban: {shadow_status}\n"
        f"💬 В чате: {in_chat} | 🤖 С ИИ: {with_ai} | 🔍 В поиске: {in_queue}",
        reply_markup=kb_user_actions(target_uid, is_shadow=is_shadow)
    )


@router.callback_query(F.data.startswith("cadm:"), StateFilter("*"))
async def admin_complaint_action(callback: types.CallbackQuery):
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    complaint_id = int(parts[2])
    target_uid = int(parts[3]) if parts[3] != "0" else None

    async def mark_reviewed(action_text):
        async with _db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE complaints_log SET reviewed=TRUE, admin_action=$1, decided_by='admin' WHERE id=$2",
                action_text, complaint_id
            )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass

    if action == "ban3" and target_uid:
        until = datetime.now() + timedelta(hours=3)
        await _update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан 3ч")
        await callback.message.answer(f"✅ Бан 3ч → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_ban3h_complaint"))
        except Exception: pass
    elif action == "ban24" and target_uid:
        until = datetime.now() + timedelta(hours=24)
        await _update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан 24ч")
        await callback.message.answer(f"✅ Бан 24ч → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_ban24h_complaint"))
        except Exception: pass
    elif action == "banperm" and target_uid:
        await _update_user(target_uid, ban_until="permanent")
        await mark_reviewed("Перм бан")
        await callback.message.answer(f"✅ Перм бан → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_banperm_user"))
        except Exception: pass
    elif action == "warn" and target_uid:
        await _increment_user(target_uid, warn_count=1)
        await mark_reviewed("Предупреждение")
        await callback.message.answer(f"✅ Предупреждение → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_warn_next_ban"))
        except Exception: pass
    elif action == "warnrep" and target_uid:
        await _increment_user(target_uid, warn_count=1)
        await mark_reviewed("Предупреждение жалобщику")
        await callback.message.answer(f"✅ Ложная жалоба. Предупреждение → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_false_complaint"))
        except Exception: pass
    elif action == "banrep" and target_uid:
        until = datetime.now() + timedelta(hours=24)
        await _update_user(target_uid, ban_until=until.isoformat())
        await mark_reviewed("Бан жалобщику")
        await callback.message.answer(f"✅ Ложная жалоба. Бан 24ч → {target_uid}")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_ban_abuse"))
        except Exception: pass
    elif action == "shadow" and target_uid:
        await _update_user(target_uid, shadow_ban=True)
        await mark_reviewed("Shadow ban")
        await callback.message.answer(f"👻 Shadow ban → {target_uid}")
    elif action == "dismiss":
        await mark_reviewed("Отклонена")
        await callback.message.answer(f"✅ Жалоба #{complaint_id} отклонена.")
    await callback.answer("✅ Готово")


@router.callback_query(F.data.startswith("audit:"), StateFilter("*"))
async def audit_handler(callback: types.CallbackQuery):
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    if parts[1] == "detail":
        complaint_id = int(parts[2])
        entry = await moderation.get_decision_detail(complaint_id)
        if entry:
            await callback.message.answer(moderation.format_decision_detail(entry))
        else:
            await callback.message.answer("Запись не найдена.")
    elif parts[1] == "page":
        offset = int(parts[2])
        total = await moderation.get_audit_total()
        entries = await moderation.get_audit_log(limit=10, offset=offset)
        if not entries:
            await callback.message.answer("Больше записей нет.")
        else:
            text = f"📋 Аудит-лог ({offset+1}-{offset+len(entries)} из {total}):\n\n"
            text += "\n\n".join(moderation.format_audit_entry(e) for e in entries)
            buttons = []
            for e in entries:
                buttons.append([InlineKeyboardButton(
                    text=f"#{e['id']} — подробнее",
                    callback_data=f"audit:detail:{e['id']}"
                )])
            if offset + 10 < total:
                buttons.append([InlineKeyboardButton(text="➡️ Ещё", callback_data=f"audit:page:{offset+10}")])
            await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("uadm:"), StateFilter("*"))
async def admin_user_action(callback: types.CallbackQuery):
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]
    target_uid = int(parts[2])
    if action == "ban3":
        until = datetime.now() + timedelta(hours=3)
        await _update_user(target_uid, ban_until=until.isoformat())
        await callback.answer("✅ Бан 3ч")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_ban3h"))
        except Exception: pass
    elif action == "ban24":
        until = datetime.now() + timedelta(hours=24)
        await _update_user(target_uid, ban_until=until.isoformat())
        await callback.answer("✅ Бан 24ч")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_ban24h"))
        except Exception: pass
    elif action == "banperm":
        await _update_user(target_uid, ban_until="permanent")
        await callback.answer("✅ Перм бан")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_banperm_user"))
        except Exception: pass
    elif action == "unban":
        await _update_user(target_uid, ban_until=None)
        await callback.answer("✅ Разбан")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_unban"))
        except Exception: pass
    elif action == "warn":
        await _increment_user(target_uid, warn_count=1)
        await callback.answer("✅ Предупреждение")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_warn_user"))
        except Exception: pass
    elif action == "kick":
        if target_uid in _active_chats:
            partner = _active_chats.pop(target_uid, None)
            if partner: _active_chats.pop(partner, None)
            await _remove_chat_from_db(target_uid, partner)
            try:
                u_lang = await _get_lang(target_uid)
                await _bot.send_message(target_uid, t(u_lang, "adm_kick_user"), reply_markup=kb_main(u_lang))
            except Exception: pass
            if partner:
                try:
                    p_lang = await _get_lang(partner)
                    await _bot.send_message(partner, t(p_lang, "partner_left"), reply_markup=kb_main(p_lang))
                except Exception: pass
            await callback.answer("✅ Кикнут")
        else:
            await callback.answer("Не в чате", show_alert=True)
    elif action == "premium":
        until = datetime.now() + timedelta(days=30)
        await _update_user(target_uid, premium_until=until.isoformat())
        await callback.answer("✅ Premium 30д")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_premium_granted"), reply_markup=kb_main(u_lang))
        except Exception: pass
    elif action == "unpremium":
        await _update_user(target_uid, premium_until=None)
        await callback.answer("✅ Premium забран")
        try:
            u_lang = await _get_lang(target_uid)
            await _bot.send_message(target_uid, t(u_lang, "adm_premium_removed"))
        except Exception: pass
    elif action == "shadowtoggle":
        tu = await _get_user(target_uid)
        current = tu.get("shadow_ban", False) if tu else False
        await _update_user(target_uid, shadow_ban=not current)
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
        if target_uid in _active_chats:
            partner = _active_chats.pop(target_uid, None)
            if partner:
                _active_chats.pop(partner, None)
                await _remove_chat_from_db(target_uid, partner)
                try:
                    p_lang = await _get_lang(partner)
                    await _bot.send_message(partner, t(p_lang, "partner_left"), reply_markup=kb_main(p_lang))
                except Exception: pass
        _ai_sessions.pop(target_uid, None)
        _last_ai_msg.pop(target_uid, None)
        async with _pairing_lock:
            for q in _get_all_queues():
                q.discard(target_uid)
        try:
            key = StorageKey(bot_id=_bot.id, chat_id=target_uid, user_id=target_uid)
            await FSMContext(_dp.storage, key=key).clear()
        except Exception: pass
        async with _db_pool.acquire() as conn:
            await conn.execute("DELETE FROM active_chats_db WHERE uid1=$1 OR uid2=$1", target_uid)
            await conn.execute("DELETE FROM complaints_log WHERE from_uid=$1 OR to_uid=$1", target_uid)
            await conn.execute("DELETE FROM users WHERE uid=$1", target_uid)
        await callback.message.answer(f"🗑 Пользователь {target_uid} полностью удалён из БД.")
        await callback.answer("✅ Удалён")


# ====================== ТАЙМЕР НЕАКТИВНОСТИ ======================
async def inactivity_checker():
    while True:
        await asyncio.sleep(60)
        now = datetime.now()

        # Завершаем неактивные чаты
        to_end = []
        for uid, partner in list(_active_chats.items()):
            if uid < partner:
                last = max(_last_msg_time.get(uid, now - timedelta(minutes=10)), _last_msg_time.get(partner, now - timedelta(minutes=10)))
                if (now - last).total_seconds() > 420:
                    to_end.append((uid, partner))
        for uid, partner in to_end:
            async with _pairing_lock:
                _active_chats.pop(uid, None)
                _active_chats.pop(partner, None)
            await _remove_chat_from_db(uid, partner)
            _clear_chat_log(uid, partner)
            for chat_uid in (uid, partner):
                try:
                    key = StorageKey(bot_id=_bot.id, chat_id=chat_uid, user_id=chat_uid)
                    await FSMContext(_dp.storage, key=key).clear()
                except Exception:
                    pass
            try:
                uid_lang = await _get_lang(uid)
                await _bot.send_message(uid, t(uid_lang, "inactivity_end"), reply_markup=kb_main(uid_lang))
            except Exception: pass
            try:
                p_lang = await _get_lang(partner)
                await _bot.send_message(partner, t(p_lang, "inactivity_end"), reply_markup=kb_main(p_lang))
            except Exception: pass

        # Завершаем неактивные AI чаты (10 мин)
        ai_to_end = []
        for uid_key in list(_ai_sessions.keys()):
            last_ai = _last_ai_msg.get(uid_key)
            if last_ai and (now - last_ai).total_seconds() > 600:
                ai_to_end.append(uid_key)
        for uid_key in ai_to_end:
            _ai_sessions.pop(uid_key, None)
            _last_ai_msg.pop(uid_key, None)
            try:
                key = StorageKey(bot_id=_bot.id, chat_id=uid_key, user_id=uid_key)
                await FSMContext(_dp.storage, key=key).clear()
            except Exception: pass
            try:
                ai_lang = await _get_lang(uid_key)
                await _bot.send_message(uid_key, t(ai_lang, "inactivity_ai_end"), reply_markup=kb_main(ai_lang))
            except Exception: pass

        # Обновляем bot_stats для channel_bot (live-данные)
        try:
            online_pairs = len(_active_chats) // 2
            searching_count = sum(len(q) for q in _get_all_queues())
            async with _db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO bot_stats (key, value, updated_at) VALUES ('online_pairs', $1, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=$1, updated_at=NOW()", online_pairs
                )
                await conn.execute(
                    "INSERT INTO bot_stats (key, value, updated_at) VALUES ('searching_count', $1, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=$1, updated_at=NOW()", searching_count
                )
        except Exception:
            pass

        # Очистка памяти: удаляем старые записи msg_count и last_msg_time
        for uid_key in list(_last_msg_time.keys()):
            last_time = _last_msg_time.get(uid_key)
            if last_time and uid_key not in _active_chats and (now - last_time).total_seconds() > 600:
                _last_msg_time.pop(uid_key, None)
                _msg_count.pop(uid_key, None)

        # Очистка мёртвых душ из очередей (по last_seen)
        async with _pairing_lock:
            for q in _get_all_queues():
                for uid_key in list(q):
                    if uid_key in _active_chats:
                        q.discard(uid_key)

        # Очистка просроченных mutual_likes
        for uid_key in list(_mutual_likes.keys()):
            if not _mutual_likes[uid_key]:
                del _mutual_likes[uid_key]


# ====================== НАПОМИНАНИЯ + AI REFILL ======================
async def reminder_task():
    while True:
        await asyncio.sleep(7200)  # каждые 2 часа
        try:
            online_count = len(_active_chats) // 2 + sum(len(q) for q in _get_all_queues())
            char_data = random.choice(list(_AI_CHARACTERS.values()))
            char_name = t("ru", char_data["name_key"])
            async with _db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT uid, lang, ai_msg_basic, ai_msg_premium, premium_until, last_seen
                    FROM users
                    WHERE last_seen < NOW() - INTERVAL '24 hours'
                    AND (last_reminder IS NULL OR last_reminder < NOW() - INTERVAL '24 hours')
                    AND ban_until IS NULL
                    AND accepted_rules = TRUE
                    ORDER BY last_seen DESC
                    LIMIT 30
                """)
            sent = 0
            for row in rows:
                uid = row["uid"]
                try:
                    days_inactive = 0
                    if row["last_seen"]:
                        days_inactive = (datetime.now() - row["last_seen"]).days
                    is_prem = bool(row.get("premium_until"))
                    used_ai = (row.get("ai_msg_basic", 0) >= 15 or row.get("ai_msg_premium", 0) >= 8)
                    u_lang = row.get("lang") or "ru"
                    u_char_name = t(u_lang, char_data["name_key"])
                    if days_inactive >= 3 and used_ai and not is_prem:
                        await _bot.send_message(uid,
                            t(u_lang, "reminder_ai_bonus"),
                            reply_markup=kb_main(u_lang)
                        )
                        async with _db_pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE users SET ai_bonus = LEAST(ai_bonus + 5, 15), last_reminder = NOW() WHERE uid = $1",
                                uid
                            )
                    else:
                        templates = REMINDER_TEMPLATES.get(u_lang, REMINDER_TEMPLATES["ru"])
                        template = random.choice(templates)
                        text = template.format(n=max(online_count, 3), char=u_char_name)
                        await _bot.send_message(uid, text, reply_markup=kb_main(u_lang))
                        async with _db_pool.acquire() as conn:
                            await conn.execute("UPDATE users SET last_reminder = NOW() WHERE uid = $1", uid)
                    sent += 1
                except Exception:
                    pass
            if sent:
                logger.info(f"Напоминания: отправлено {sent}")
        except Exception as e:
            logger.error(f"reminder_task error: {e}")
