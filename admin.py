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
_PARTNER_ADS = None
_filter_ads = None
_get_chat_topics = None
_auto_topic_sent = set()  # (uid, partner) pairs that got auto-topic


def init(*, bot, dp, db_pool, admin_id, active_chats, ai_sessions, last_ai_msg,
         pairing_lock, get_all_queues, chat_logs, last_msg_time, msg_count,
         mutual_likes, clear_chat_log, get_user, update_user, increment_user,
         get_rating, remove_chat_from_db, AI_CHARACTERS,
         PARTNER_ADS=None, filter_ads=None, get_chat_topics=None):
    global _bot, _dp, _db_pool, _admin_id, _active_chats, _ai_sessions
    global _last_ai_msg, _pairing_lock, _get_all_queues, _chat_logs
    global _last_msg_time, _msg_count, _mutual_likes, _clear_chat_log
    global _get_user, _update_user, _increment_user, _get_rating
    global _remove_chat_from_db, _AI_CHARACTERS, _PARTNER_ADS, _filter_ads, _get_chat_topics
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
    _PARTNER_ADS = PARTNER_ADS or []
    _filter_ads = filter_ads
    _get_chat_topics = get_chat_topics


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
        [InlineKeyboardButton(text="🖼 Медиа персонажей", callback_data="admin:char_media")],
        [InlineKeyboardButton(text="📢 Маркетинг", callback_data="admin:marketing")],
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
    elif action == "char_media":
        # Show character list for media upload
        chars = _AI_CHARACTERS or {}
        buttons = []
        row = []
        for cid, cdata in chars.items():
            label = f"{cdata['emoji']} {cid}"
            row.append(InlineKeyboardButton(text=label, callback_data=f"charmedia:{cid}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        # Check which chars already have media
        has_media = set()
        async with _db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT character_id FROM ai_character_media WHERE gif_file_id IS NOT NULL")
            has_media = {r["character_id"] for r in rows}
        status = "✅" if has_media else "—"
        info = f"🖼 Медиа персонажей\n\nЗагружено: {len(has_media)}/{len(chars)}\n\nВыбери персонажа:"
        await callback.message.answer(info, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
    elif action == "marketing":
        await callback.message.answer(
            "📢 Маркетинг MatchMe",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Креативы рекламы", callback_data="mkt:creatives")],
                [InlineKeyboardButton(text="📊 Аналитика рекламы", callback_data="mkt:ad_stats")],
                [InlineKeyboardButton(text="🤖 Аналитика AI-чатов", callback_data="mkt:ai_stats")],
                [InlineKeyboardButton(text="💰 Доходы", callback_data="mkt:revenue")],
                [InlineKeyboardButton(text="⭐ Оценки чатов", callback_data="mkt:ratings")],
                [InlineKeyboardButton(text="🔬 A/B тест цен", callback_data="mkt:ab_prices")],
                [InlineKeyboardButton(text="📊 Когорты LTV", callback_data="mkt:cohorts")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back")],
            ])
        )
    elif action == "back":
        await callback.message.edit_text("🛡 Админ панель MatchMe", reply_markup=await kb_admin_main())
    await callback.answer()


@router.callback_query(F.data.startswith("mkt:"), StateFilter("*"))
async def marketing_handler(callback: types.CallbackQuery):
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]

    if action == "creatives":
        # Показать выбор языка
        await callback.message.answer(
            "📋 Выбери язык для просмотра креативов:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🇷🇺 RU", callback_data="mkt:cr:ru"),
                    InlineKeyboardButton(text="🇬🇧 EN", callback_data="mkt:cr:en"),
                    InlineKeyboardButton(text="🇪🇸 ES", callback_data="mkt:cr:es"),
                ],
                [InlineKeyboardButton(text="📊 Все (сводка)", callback_data="mkt:cr:all")],
            ])
        )

    elif action.startswith("cr:"):
        lang_filter = action.split(":")[1]
        if lang_filter == "all":
            # Сводка: какие креативы на каких языках
            text = "📋 Сводка креативов:\n\n"
            seen = {}
            for ad in _PARTNER_ADS:
                base = ad["text_key"].rsplit("_", 1)[0]  # ad_dzen, ad_vpnglobal, etc
                if base not in seen:
                    seen[base] = {"langs": set(), "modes": ad["modes"], "count": 0}
                if ad["langs"]:
                    seen[base]["langs"].update(ad["langs"])
                else:
                    seen[base]["langs"].update(["ru", "en", "es"])
                seen[base]["count"] += 1
            for base, info in seen.items():
                name = base.replace("ad_", "").upper()
                langs_str = ", ".join(sorted(info["langs"]))
                modes_str = ", ".join(info["modes"]) if info["modes"] else "все"
                text += f"📌 {name}\n   Языки: {langs_str} | Режимы: {modes_str} | Креативов: {info['count']}\n\n"
            text += f"Всего: {len(_PARTNER_ADS)} креативов"
            await callback.message.answer(text)
        else:
            # Показать креативы для выбранного языка
            ads = [ad for ad in _PARTNER_ADS if ad["langs"] is None or lang_filter in ad["langs"]]
            if not ads:
                await callback.message.answer(f"Нет креативов для {lang_filter.upper()}")
            else:
                for i, ad in enumerate(ads):
                    modes_str = ", ".join(ad["modes"]) if ad["modes"] else "все"
                    # Показываем текст на RU если есть, иначе EN
                    from locales import TEXTS
                    ad_text = TEXTS.get("ru", {}).get(ad["text_key"]) or TEXTS.get("en", {}).get(ad["text_key"]) or ad["text_key"]
                    btn_text = TEXTS.get("ru", {}).get(ad["btn_key"]) or TEXTS.get("en", {}).get(ad["btn_key"]) or ad["btn_key"]
                    langs = ", ".join(ad["langs"]) if ad["langs"] else "все"
                    header = f"📌 #{i+1} | Языки: {langs} | Режимы: {modes_str}\n"
                    header += f"🔘 Кнопка: {btn_text}\n\n"
                    await callback.message.answer(
                        header + ad_text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=btn_text, url=ad["url"])],
                        ])
                    )
                    if i >= 14:  # лимит чтобы не заспамить
                        await callback.message.answer(f"... и ещё {len(ads) - 15}")
                        break

    elif action == "ad_stats":
        # Выбор периода
        await callback.message.answer(
            "📊 Аналитика рекламы — выбери период:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Сегодня", callback_data="mkt:ads:1"),
                    InlineKeyboardButton(text="7 дней", callback_data="mkt:ads:7"),
                    InlineKeyboardButton(text="30 дней", callback_data="mkt:ads:30"),
                ],
                [InlineKeyboardButton(text="Всё время", callback_data="mkt:ads:0")],
            ])
        )

    elif action.startswith("ads:"):
        days = int(action.split(":")[1])
        period_cond = ""
        period_label = "всё время"
        if days > 0:
            period_cond = f"AND created_at > NOW() - INTERVAL '{days} days'"
            period_label = f"за {days} дн."

        async with _db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT ad_key, source, COUNT(*) as cnt
                FROM ad_events
                WHERE event_type = 'impression' {period_cond}
                GROUP BY ad_key, source
                ORDER BY cnt DESC
            """)
            total_impressions = await conn.fetchval(f"""
                SELECT COUNT(*) FROM ad_events
                WHERE event_type = 'impression' {period_cond}
            """) or 0
            total_clicks = await conn.fetchval(f"""
                SELECT COUNT(*) FROM ad_events
                WHERE event_type = 'click' {period_cond}
            """) or 0
            unique_users = await conn.fetchval(f"""
                SELECT COUNT(DISTINCT uid) FROM ad_events
                WHERE event_type = 'impression' {period_cond}
            """) or 0
            # Клики по креативам
            click_rows = await conn.fetch(f"""
                SELECT ad_key, source, COUNT(*) as cnt
                FROM ad_events
                WHERE event_type = 'click' {period_cond}
                GROUP BY ad_key, source
            """)

        overall_ctr = round(total_clicks / max(total_impressions, 1) * 100, 1)
        text = f"📊 Аналитика рекламы ({period_label})\n\n"
        text += f"Показов: {total_impressions} | Кликов: {total_clicks}\n"
        text += f"CTR: {overall_ctr}%\n"
        text += f"Уник. пользователей: {unique_users}\n\n"

        # Группируем клики по ad_key
        clicks_by_ad = {}
        for r in click_rows:
            key = r["ad_key"]
            if key not in clicks_by_ad:
                clicks_by_ad[key] = {"search": 0, "ai_chat": 0, "total": 0}
            clicks_by_ad[key][r["source"]] = r["cnt"]
            clicks_by_ad[key]["total"] += r["cnt"]

        if rows:
            by_ad = {}
            for r in rows:
                key = r["ad_key"]
                if key not in by_ad:
                    by_ad[key] = {"search": 0, "ai_chat": 0, "total": 0}
                by_ad[key][r["source"]] = r["cnt"]
                by_ad[key]["total"] += r["cnt"]

            text += "По креативам:\n"
            for key, data in sorted(by_ad.items(), key=lambda x: -x[1]["total"]):
                name = key.replace("ad_", "").replace("_", " ").upper()
                clicks = clicks_by_ad.get(key, {}).get("total", 0)
                ctr = round(clicks / max(data["total"], 1) * 100, 1)
                text += f"  {name}: {data['total']} показов, {clicks} кликов (CTR {ctr}%)\n"
                text += f"    поиск: {data['search']} / AI: {data['ai_chat']}\n"
        else:
            text += "Нет данных за этот период."

        await callback.message.answer(text)

    elif action == "ai_stats":
        async with _db_pool.acquire() as conn:
            # Общая статистика AI
            total_sessions = len(_ai_sessions)
            total_ai_msgs = await conn.fetchval(
                "SELECT COUNT(*) FROM ai_history WHERE role='user'"
            ) or 0
            unique_ai_users = await conn.fetchval(
                "SELECT COUNT(DISTINCT uid) FROM ai_history"
            ) or 0
            # Популярность персонажей (за всё время)
            char_stats = await conn.fetch("""
                SELECT character_id, COUNT(*) as msg_count, COUNT(DISTINCT uid) as user_count
                FROM ai_history
                WHERE role = 'user'
                GROUP BY character_id
                ORDER BY msg_count DESC
            """)
            # За последние 7 дней
            char_stats_week = await conn.fetch("""
                SELECT character_id, COUNT(*) as msg_count, COUNT(DISTINCT uid) as user_count
                FROM ai_history
                WHERE role = 'user' AND created_at > NOW() - INTERVAL '7 days'
                GROUP BY character_id
                ORDER BY msg_count DESC
            """)

        text = f"🤖 Аналитика AI-чатов\n\n"
        text += f"Активных сессий: {total_sessions}\n"
        text += f"Всего сообщений: {total_ai_msgs}\n"
        text += f"Уник. пользователей: {unique_ai_users}\n\n"

        if char_stats:
            text += "📊 Популярность (всё время):\n"
            for r in char_stats:
                cid = r["character_id"]
                char = (_AI_CHARACTERS or {}).get(cid, {})
                emoji = char.get("emoji", "")
                name = cid.replace("_", " ").title()
                text += f"  {emoji} {name}: {r['msg_count']} сообщ. / {r['user_count']} юзеров\n"

        if char_stats_week:
            text += f"\n📊 За 7 дней:\n"
            for r in char_stats_week:
                cid = r["character_id"]
                char = (_AI_CHARACTERS or {}).get(cid, {})
                emoji = char.get("emoji", "")
                name = cid.replace("_", " ").title()
                text += f"  {emoji} {name}: {r['msg_count']} сообщ. / {r['user_count']} юзеров\n"

        await callback.message.answer(text)

    elif action == "revenue":
        async with _db_pool.acquire() as conn:
            # Доходы от Premium
            total_premiums = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL AND premium_until != 'permanent'"
            ) or 0
            # Доходы от покупок (ab_events)
            purchases_total = await conn.fetchval(
                "SELECT COUNT(*) FROM ab_events WHERE event_type = 'purchase'"
            ) or 0
            purchases_week = await conn.fetchval(
                "SELECT COUNT(*) FROM ab_events WHERE event_type = 'purchase' AND created_at > NOW() - INTERVAL '7 days'"
            ) or 0
            # Подарки
            gifts_total = await conn.fetchval(
                "SELECT COUNT(*) FROM ab_events WHERE event_type = 'gift_sent'"
            ) or 0
            gifts_week = await conn.fetchval(
                "SELECT COUNT(*) FROM ab_events WHERE event_type = 'gift_sent' AND created_at > NOW() - INTERVAL '7 days'"
            ) or 0
            # Триалы
            trials_total = await conn.fetchval(
                "SELECT COUNT(*) FROM ab_events WHERE event_type = 'trial_activated'"
            ) or 0
            trials_conv = await conn.fetchval(
                "SELECT COUNT(*) FROM ab_events WHERE event_type = 'trial_shown'"
            ) or 1  # avoid div/0

        text = f"💰 Доходы MatchMe\n\n"
        text += f"💎 Активных Premium: {total_premiums}\n\n"
        text += f"🛒 Покупки:\n"
        text += f"  Всего: {purchases_total}\n"
        text += f"  За 7 дней: {purchases_week}\n\n"
        text += f"🎁 Подарки:\n"
        text += f"  Всего: {gifts_total}\n"
        text += f"  За 7 дней: {gifts_week}\n\n"
        text += f"🎟 Триалы:\n"
        text += f"  Активировано: {trials_total}\n"
        text += f"  Показано: {trials_conv}\n"
        text += f"  Конверсия: {round(trials_total / max(trials_conv, 1) * 100, 1)}%"

        await callback.message.answer(text)

    elif action == "ratings":
        async with _db_pool.acquire() as conn:
            total_ratings = await conn.fetchval("SELECT COUNT(*) FROM chat_ratings") or 0
            avg_rating = await conn.fetchval("SELECT ROUND(AVG(stars)::numeric, 2) FROM chat_ratings") or 0
            dist = await conn.fetch(
                "SELECT stars, COUNT(*) as cnt FROM chat_ratings GROUP BY stars ORDER BY stars"
            )
            avg_week = await conn.fetchval(
                "SELECT ROUND(AVG(stars)::numeric, 2) FROM chat_ratings WHERE created_at > NOW() - INTERVAL '7 days'"
            ) or 0
            total_week = await conn.fetchval(
                "SELECT COUNT(*) FROM chat_ratings WHERE created_at > NOW() - INTERVAL '7 days'"
            ) or 0

        text = f"⭐ Оценки чатов\n\n"
        text += f"Всего оценок: {total_ratings}\n"
        text += f"Средняя: {avg_rating} ⭐\n"
        text += f"За 7 дней: {total_week} оценок, ср. {avg_week} ⭐\n\n"
        if dist:
            text += "Распределение:\n"
            for r in dist:
                bar = "█" * r["cnt"] if r["cnt"] <= 20 else "█" * 20 + f"..{r['cnt']}"
                text += f"  {'⭐' * r['stars']}: {r['cnt']} {bar}\n"

        await callback.message.answer(text)

    elif action == "ab_prices":
        async with _db_pool.acquire() as conn:
            # A/B группы: показы цен vs покупки
            for group in ("A", "B"):
                shown = await conn.fetchval(
                    "SELECT COUNT(*) FROM ab_events WHERE ab_group=$1 AND event_type='price_shown'", group
                ) or 0
                purchased = await conn.fetchval(
                    "SELECT COUNT(*) FROM ab_events WHERE ab_group=$1 AND event_type='purchase'", group
                ) or 0
                trials = await conn.fetchval(
                    "SELECT COUNT(*) FROM ab_events WHERE ab_group=$1 AND event_type='trial_activated'", group
                ) or 0
                users_total = await conn.fetchval(
                    "SELECT COUNT(*) FROM users WHERE ab_group=$1", group
                ) or 0
                if group == "A":
                    text = f"🔬 A/B тест цен\n\n"
                    text += f"Группа A (полная цена):\n"
                else:
                    text += f"\nГруппа B (скидка 15%):\n"
                conv = round(purchased / max(shown, 1) * 100, 1)
                text += f"  Юзеров: {users_total}\n"
                text += f"  Показов цен: {shown}\n"
                text += f"  Покупок: {purchased} (конверсия: {conv}%)\n"
                text += f"  Триалов: {trials}\n"

        await callback.message.answer(text)

    elif action == "cohorts":
        async with _db_pool.acquire() as conn:
            # Когорты за последние 4 недели
            from datetime import timedelta
            text = "📊 Когортный анализ LTV\n\n"
            for weeks_ago in range(4):
                start_iv = timedelta(days=(weeks_ago + 1) * 7)
                end_iv = timedelta(days=weeks_ago * 7)
                cohort_size = await conn.fetchval("""
                    SELECT COUNT(*) FROM users
                    WHERE created_at >= NOW() - $1::interval AND created_at < NOW() - $2::interval
                """, start_iv, end_iv) or 0
                if cohort_size == 0:
                    continue
                # Покупки этой когорты
                purchases = await conn.fetchval("""
                    SELECT COUNT(*) FROM ab_events e
                    JOIN users u ON e.uid = u.uid
                    WHERE u.created_at >= NOW() - $1::interval AND u.created_at < NOW() - $2::interval
                    AND e.event_type = 'purchase'
                """, start_iv, end_iv) or 0
                # Подарки
                gifts = await conn.fetchval("""
                    SELECT COUNT(*) FROM ab_events e
                    JOIN users u ON e.uid = u.uid
                    WHERE u.created_at >= NOW() - $1::interval AND u.created_at < NOW() - $2::interval
                    AND e.event_type = 'gift_sent'
                """, start_iv, end_iv) or 0
                # Активные сейчас (за 7 дней)
                active_now = await conn.fetchval("""
                    SELECT COUNT(*) FROM users
                    WHERE created_at >= NOW() - $1::interval AND created_at < NOW() - $2::interval
                    AND last_seen > NOW() - INTERVAL '7 days'
                """, start_iv, end_iv) or 0
                # Среднее кол-во чатов
                avg_chats = await conn.fetchval("""
                    SELECT ROUND(AVG(total_chats)::numeric, 1) FROM users
                    WHERE created_at >= NOW() - $1::interval AND created_at < NOW() - $2::interval
                    AND total_chats > 0
                """, start_iv, end_iv) or 0

                retention = round(active_now / max(cohort_size, 1) * 100)
                conv_pct = round(purchases / max(cohort_size, 1) * 100, 1)
                week_label = f"Неделя -{weeks_ago + 1}" if weeks_ago > 0 else "Эта неделя"

                text += f"📅 {week_label} ({cohort_size} юзеров):\n"
                text += f"  Retention: {active_now}/{cohort_size} ({retention}%)\n"
                text += f"  Покупок: {purchases} (конв. {conv_pct}%)\n"
                text += f"  Подарков: {gifts}\n"
                text += f"  Ср. чатов: {avg_chats}\n\n"

            if "📅" not in text:
                text += "Нет данных. Когорты начнут формироваться по мере регистрации юзеров."

        await callback.message.answer(text)

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
async def _inactivity_tick(_cleanup_counter):
    """Одна итерация inactivity_checker. Вызывается из цикла с try/except."""
    now = datetime.now()

    # Авто-тема при тишине (2 мин без сообщений)
    if _get_chat_topics:
        for uid, partner in list(_active_chats.items()):
            if uid < partner:
                chat_key = (min(uid, partner), max(uid, partner))
                if chat_key in _auto_topic_sent:
                    continue
                last = max(
                    _last_msg_time.get(uid, now - timedelta(minutes=10)),
                    _last_msg_time.get(partner, now - timedelta(minutes=10))
                )
                silence = (now - last).total_seconds()
                if 120 < silence < 300:  # 2-5 мин тишины
                    _auto_topic_sent.add(chat_key)
                    try:
                        uid_lang = await _get_lang(uid)
                        p_lang = await _get_lang(partner)
                        topics = _get_chat_topics(uid_lang)
                        idx = random.randrange(len(topics))
                        topic = topics[idx]
                        await _bot.send_message(uid, t(uid_lang, "auto_topic", topic=topic))
                        p_topics = _get_chat_topics(p_lang)
                        p_topic = p_topics[idx] if idx < len(p_topics) else topic
                        await _bot.send_message(partner, t(p_lang, "auto_topic", topic=p_topic))
                    except Exception:
                        pass

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
        _auto_topic_sent.discard((min(uid, partner), max(uid, partner)))
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

    # Обновляем bot_stats для admin_bot (live-данные)
    try:
        online_pairs = len(_active_chats) // 2
        searching_count = sum(len(q) for q in _get_all_queues())
        ai_sessions_count = len(_ai_sessions)
        async with _db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO bot_stats (key, value, updated_at) VALUES ('online_pairs', $1, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value=$1, updated_at=NOW()", online_pairs
            )
            await conn.execute(
                "INSERT INTO bot_stats (key, value, updated_at) VALUES ('searching_count', $1, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value=$1, updated_at=NOW()", searching_count
            )
            await conn.execute(
                "INSERT INTO bot_stats (key, value, updated_at) VALUES ('ai_sessions_count', $1, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value=$1, updated_at=NOW()", ai_sessions_count
            )
    except Exception:
        pass

    # Polling admin_commands — исполняем pending команды от admin_bot
    try:
        async with _db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM admin_commands WHERE status='pending'")
            for row in rows:
                if row['command'] == 'kick':
                    uid = row['target_uid']
                    if uid in _active_chats:
                        partner = _active_chats[uid]
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
                        except Exception:
                            pass
                        try:
                            p_lang = await _get_lang(partner)
                            await _bot.send_message(partner, t(p_lang, "inactivity_end"), reply_markup=kb_main(p_lang))
                        except Exception:
                            pass
                await conn.execute(
                    "UPDATE admin_commands SET status='executed', executed_at=NOW() WHERE id=$1",
                    row['id']
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

    # Расширенная очистка раз в час (каждые 60 циклов)
    _cleanup_counter += 1
    if _cleanup_counter >= 60:
        _cleanup_counter = 0
        # chat_logs: удалить записи юзеров не в active_chats
        for uid_key in list(_chat_logs.keys()):
            if uid_key not in _active_chats:
                _chat_logs.pop(uid_key, None)
        # last_msg_time: удалить записи старше 30 минут (не в чате)
        for uid_key in list(_last_msg_time.keys()):
            lt = _last_msg_time.get(uid_key)
            if lt and uid_key not in _active_chats and (now - lt).total_seconds() > 1800:
                _last_msg_time.pop(uid_key, None)
                _msg_count.pop(uid_key, None)
        # AI sessions: удалить сессии старше 2 часов
        for uid_key in list(_last_ai_msg.keys()):
            lt = _last_ai_msg.get(uid_key)
            if lt and (now - lt).total_seconds() > 7200:
                _ai_sessions.pop(uid_key, None)
                _last_ai_msg.pop(uid_key, None)

    return _cleanup_counter


async def inactivity_checker():
    _cleanup_counter = 0
    while True:
        await asyncio.sleep(60)
        try:
            _cleanup_counter = await _inactivity_tick(_cleanup_counter)
        except Exception as e:
            logger.error(f"inactivity_checker error: {e}", exc_info=True)


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


# ====================== СТРИК-НАПОМИНАНИЯ + AI MISS-YOU ======================
async def streak_and_ai_push_task():
    """Runs every 4 hours: streak reminders + personalized AI push."""
    while True:
        await asyncio.sleep(14400)  # 4 часа
        try:
            async with _db_pool.acquire() as conn:
                # 1. Стрик-напоминания: юзеры со стриком >= 3, не заходили сегодня
                streak_users = await conn.fetch("""
                    SELECT uid, lang, streak_days, streak_last_date
                    FROM users
                    WHERE streak_days >= 3
                    AND streak_last_date = CURRENT_DATE - 1
                    AND last_seen::date < CURRENT_DATE
                    AND ban_until IS NULL
                    AND (last_reminder IS NULL OR last_reminder < NOW() - INTERVAL '12 hours')
                    LIMIT 50
                """)
                sent_streak = 0
                for row in streak_users:
                    try:
                        u_lang = row.get("lang") or "ru"
                        await _bot.send_message(
                            row["uid"],
                            t(u_lang, "streak_reminder", days=row["streak_days"]),
                            reply_markup=kb_main(u_lang)
                        )
                        await conn.execute(
                            "UPDATE users SET last_reminder = NOW() WHERE uid = $1", row["uid"]
                        )
                        sent_streak += 1
                    except Exception:
                        pass

                # 2. AI miss-you: юзеры с историей AI, не заходили 2+ дня
                ai_users = await conn.fetch("""
                    SELECT uid, character_id, lang FROM (
                        SELECT h.uid, h.character_id, u.lang,
                               ROW_NUMBER() OVER (PARTITION BY h.uid ORDER BY COUNT(*) DESC) AS rn
                        FROM ai_history h
                        JOIN users u ON u.uid = h.uid
                        WHERE u.last_seen < NOW() - INTERVAL '48 hours'
                        AND u.last_seen > NOW() - INTERVAL '14 days'
                        AND u.ban_until IS NULL
                        AND (u.last_reminder IS NULL OR u.last_reminder < NOW() - INTERVAL '24 hours')
                        AND h.role = 'user'
                        GROUP BY h.uid, h.character_id, u.lang
                    ) sub WHERE rn = 1
                    LIMIT 30
                """)
                sent_ai = 0
                for row in ai_users:
                    try:
                        char = (_AI_CHARACTERS or {}).get(row["character_id"])
                        if not char:
                            continue
                        u_lang = row.get("lang") or "ru"
                        char_name = t(u_lang, char["name_key"])
                        await _bot.send_message(
                            row["uid"],
                            t(u_lang, "ai_miss_you", emoji=char["emoji"], name=char_name),
                            reply_markup=kb_main(u_lang)
                        )
                        await conn.execute(
                            "UPDATE users SET last_reminder = NOW() WHERE uid = $1", row["uid"]
                        )
                        sent_ai += 1
                    except Exception:
                        pass

            if sent_streak or sent_ai:
                logger.info(f"Push: streak={sent_streak}, ai_miss={sent_ai}")

            # Очистка старых квестов (старше 7 дней) + сброс daily_bonus_claimed
            try:
                await conn.execute(
                    "DELETE FROM daily_quests WHERE quest_date < CURRENT_DATE - 7"
                )
                await conn.execute(
                    "UPDATE users SET daily_bonus_claimed = FALSE "
                    "WHERE daily_bonus_claimed = TRUE"
                )
            except Exception:
                pass

        except Exception as e:
            logger.error(f"streak_and_ai_push_task error: {e}")


# ====================== WIN-BACK СИСТЕМА ======================

WINBACK_MESSAGES = {
    "ru": {
        1: "⏳ Твой Premium заканчивается завтра!\n\nНе теряй приоритетный поиск, VIP-персонажей и автоперевод.\nПродли сейчас — и не пропусти ни одного интересного собеседника.",
        2: "💔 Твой Premium закончился.\n\nБез Premium поиск медленнее, рекламы больше.\nВернись — ты заслуживаешь лучший опыт.",
        3: "👋 Скучаем по тебе!\n\nТвои VIP-персонажи ждут.\nВозвращайся в Premium — почувствуй разницу снова.",
        4: "🎁 Последний шанс!\n\nMatchMe Premium — приоритет поиска, VIP AI, без рекламы.\nНе упусти — вернись прямо сейчас.",
    },
    "en": {
        1: "⏳ Your Premium expires tomorrow!\n\nDon't lose priority search, VIP characters and auto-translate.\nRenew now — don't miss out on great conversations.",
        2: "💔 Your Premium has expired.\n\nWithout Premium, search is slower and there are more ads.\nCome back — you deserve a better experience.",
        3: "👋 We miss you!\n\nYour VIP characters are waiting.\nReturn to Premium — feel the difference again.",
        4: "🎁 Last chance!\n\nMatchMe Premium — priority search, VIP AI, no ads.\nDon't miss out — come back now.",
    },
    "es": {
        1: "⏳ ¡Tu Premium expira mañana!\n\nNo pierdas búsqueda prioritaria, personajes VIP y traducción automática.\nRenueva ahora — no te pierdas buenas conversaciones.",
        2: "💔 Tu Premium ha expirado.\n\nSin Premium, la búsqueda es más lenta y hay más anuncios.\nVuelve — mereces una mejor experiencia.",
        3: "👋 ¡Te extrañamos!\n\nTus personajes VIP te esperan.\nVuelve a Premium — siente la diferencia otra vez.",
        4: "🎁 ¡Última oportunidad!\n\nMatchMe Premium — búsqueda prioritaria, IA VIP, sin anuncios.\nNo lo dejes pasar — vuelve ahora.",
    },
}


async def winback_task():
    """Background task: sends win-back messages to users with expiring/expired premium."""
    while True:
        await asyncio.sleep(3600)  # каждый час
        try:
            now = datetime.now()
            async with _db_pool.acquire() as conn:
                # Stage 1: Premium expires within 24h
                rows_expiring = await conn.fetch("""
                    SELECT uid, lang, premium_until, winback_stage FROM users
                    WHERE premium_until IS NOT NULL
                    AND premium_until != 'permanent'
                    AND winback_stage = 0
                    AND ban_until IS NULL
                    AND accepted_rules = TRUE
                    LIMIT 50
                """)
                # Stage 2-4: Already expired
                rows_expired = await conn.fetch("""
                    SELECT uid, lang, premium_expired_at, winback_stage FROM users
                    WHERE premium_expired_at IS NOT NULL
                    AND winback_stage BETWEEN 1 AND 3
                    AND premium_until IS NULL
                    AND ban_until IS NULL
                    LIMIT 50
                """)

            sent = 0
            # Stage 1: 24h before expiry
            for row in rows_expiring:
                try:
                    p_until = datetime.fromisoformat(row["premium_until"])
                    hours_left = (p_until - now).total_seconds() / 3600
                    if hours_left <= 24 and hours_left > 0:
                        uid = row["uid"]
                        u_lang = row.get("lang") or "ru"
                        msg = WINBACK_MESSAGES.get(u_lang, WINBACK_MESSAGES["ru"])[1]
                        from keyboards import kb_premium
                        await _bot.send_message(uid, msg, reply_markup=kb_premium(u_lang))
                        async with _db_pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE users SET winback_stage=1 WHERE uid=$1", uid
                            )
                        sent += 1
                except Exception:
                    pass

            # Stage 2: Just expired (mark expiry time)
            # This handles the transition: premium_until passed -> set premium_expired_at
            try:
                async with _db_pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE users
                        SET premium_expired_at = NOW(),
                            premium_until = NULL,
                            premium_tier = NULL,
                            winback_stage = GREATEST(winback_stage, 1)
                        WHERE premium_until IS NOT NULL
                        AND premium_until != 'permanent'
                        AND premium_until < $1
                    """, now.isoformat())
            except Exception:
                pass

            # Stage 2-4: Progressive win-back after expiry
            for row in rows_expired:
                try:
                    uid = row["uid"]
                    stage = row["winback_stage"]
                    expired_at = row["premium_expired_at"]
                    if not expired_at:
                        continue
                    days_since = (now - expired_at).total_seconds() / 86400
                    u_lang = row.get("lang") or "ru"

                    next_stage = None
                    if stage == 1 and days_since >= 0.1:  # right after expiry
                        next_stage = 2
                    elif stage == 2 and days_since >= 3:
                        next_stage = 3
                    elif stage == 3 and days_since >= 7:
                        next_stage = 4

                    if next_stage:
                        msg = WINBACK_MESSAGES.get(u_lang, WINBACK_MESSAGES["ru"]).get(next_stage)
                        if msg:
                            from keyboards import kb_premium
                            await _bot.send_message(uid, msg, reply_markup=kb_premium(u_lang))
                            async with _db_pool.acquire() as conn:
                                await conn.execute(
                                    "UPDATE users SET winback_stage=$2 WHERE uid=$1", uid, next_stage
                                )
                            sent += 1
                except Exception:
                    pass

            if sent:
                logger.info(f"Win-back: отправлено {sent}")

            # ===== ПОДАРКИ ВОЗВРАЩЕНИЯ =====
            from constants import RETURN_GIFT_TIERS
            now_rg = datetime.now()
            inactive_users = await conn.fetch("""
                SELECT uid, lang, last_seen, return_gift_stage, ai_energy_used, premium_until, bonus_energy
                FROM users
                WHERE last_seen < NOW() - INTERVAL '3 days'
                AND ban_until IS NULL
                AND accepted_rules = TRUE
                AND (return_gift_given IS NULL OR return_gift_given < NOW() - INTERVAL '7 days')
                LIMIT 30
            """)
            rg_sent = 0
            for row in inactive_users:
                try:
                    uid_rg = row["uid"]
                    u_lang = row.get("lang") or "ru"
                    last_seen = row["last_seen"]
                    if not last_seen:
                        continue
                    days_inactive = (now_rg - last_seen).total_seconds() / 86400
                    current_stage = row.get("return_gift_stage", 0) or 0
                    # Определяем тир
                    chosen_tier = None
                    for tier_num in sorted(RETURN_GIFT_TIERS.keys(), reverse=True):
                        tier = RETURN_GIFT_TIERS[tier_num]
                        if days_inactive >= tier["days_min"] and tier_num > current_stage:
                            chosen_tier = tier_num
                            break
                    if not chosen_tier:
                        continue
                    tier_cfg = RETURN_GIFT_TIERS[chosen_tier]
                    # Начисляем энергию в bonus_energy
                    from constants import MAX_BONUS_ENERGY
                    cur_bonus = row.get("bonus_energy", 0) or 0
                    new_bonus_val = min(cur_bonus + tier_cfg["energy"], MAX_BONUS_ENERGY)
                    updates = {
                        "bonus_energy": new_bonus_val,
                        "return_gift_stage": chosen_tier,
                        "return_gift_given": now_rg,
                        "return_gifts_total": (row.get("return_gifts_total", 0) or 0) + 1,
                    }
                    # Trial Premium для тиров 3-4
                    if tier_cfg["trial_days"] > 0 and not row.get("premium_until"):
                        trial_until = now_rg + timedelta(days=tier_cfg["trial_days"])
                        updates["premium_until"] = trial_until.isoformat()
                        updates["premium_tier"] = "premium"
                    set_parts = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
                    vals = list(updates.values())
                    await conn.execute(
                        f"UPDATE users SET {set_parts} WHERE uid=$1", uid_rg, *vals
                    )
                    await _bot.send_message(
                        uid_rg, t(u_lang, f"return_gift_{chosen_tier}"),
                        reply_markup=kb_main(u_lang)
                    )
                    rg_sent += 1
                except Exception:
                    pass
            if rg_sent:
                logger.info(f"Return gifts: отправлено {rg_sent}")

        except Exception as e:
            logger.error(f"winback_task error: {e}")


# ====================== МЕДИА ПЕРСОНАЖЕЙ ======================

@router.callback_query(F.data.startswith("charmedia:"), StateFilter("*"))
async def char_media_select(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != _admin_id:
        await callback.answer()
        return
    char_id = callback.data.split(":", 1)[1]
    chars = _AI_CHARACTERS or {}
    if char_id not in chars:
        await callback.answer("Персонаж не найден", show_alert=True)
        return
    char = chars[char_id]
    # Check current media
    async with _db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT gif_file_id, photo_file_id, blurred_file_id, hot_photo_file_id, hot_gif_file_id FROM ai_character_media WHERE character_id=$1",
            char_id
        )
    gif_status = "✅" if (row and row["gif_file_id"]) else "❌"
    photo_status = "✅" if (row and row["photo_file_id"]) else "❌"
    hot_status = "✅" if (row and row.get("hot_photo_file_id")) else "❌"
    hot_gif_status = "✅" if (row and row.get("hot_gif_file_id")) else "❌"

    text = (
        f"{char['emoji']} <b>{char_id}</b>\n\n"
        f"{gif_status} GIF (превью)\n"
        f"{photo_status} Фото — 15 ⭐\n"
        f"{hot_status} 🔥 Hot фото — 50 ⭐\n"
        f"{hot_gif_status} 🔥 Hot GIF — 100 ⭐\n\n"
        f"Загрузка: GIF → превью, GIF+hot → hot GIF\n"
        f"Фото → платное, Фото+hot → горячее"
    )
    # Build view/delete buttons for existing media
    media_buttons = []
    slots = [
        ("gif_file_id", "👁 GIF", "🗑 GIF"),
        ("photo_file_id", "👁 Фото", "🗑 Фото"),
        ("hot_photo_file_id", "👁 Hot фото", "🗑 Hot фото"),
        ("hot_gif_file_id", "👁 Hot GIF", "🗑 Hot GIF"),
    ]
    for field, view_label, del_label in slots:
        if row and row.get(field):
            media_buttons.append([
                InlineKeyboardButton(text=view_label, callback_data=f"cmview:{char_id}:{field}"),
                InlineKeyboardButton(text=del_label, callback_data=f"cmdel:{char_id}:{field}"),
            ])
    kb = InlineKeyboardMarkup(inline_keyboard=media_buttons) if media_buttons else None

    await state.set_state(AdminState.waiting_char_gif)
    await state.update_data(media_char_id=char_id)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.message(StateFilter(AdminState.waiting_char_gif))
async def char_media_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != _admin_id:
        return

    data = await state.get_data()
    char_id = data.get("media_char_id")
    if not char_id:
        await state.clear()
        await message.answer("Ошибка — попробуй заново через /admin")
        return

    chars = _AI_CHARACTERS or {}
    char = chars.get(char_id)
    emoji = char["emoji"] if char else ""

    caption = (message.caption or "").strip().lower()

    if message.animation:
        file_id = message.animation.file_id
        if caption == "hot":
            # Hot GIF
            async with _db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ai_character_media (character_id, hot_gif_file_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET hot_gif_file_id=$2, updated_at=NOW()
                """, char_id, file_id)
            await message.answer(
                f"🔥 Hot GIF для {emoji} <b>{char_id}</b> сохранён!\n\n"
                f"Отправь ещё медиа или нажми /admin для выхода.",
                parse_mode="HTML"
            )
        else:
            # Regular GIF (preview)
            async with _db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ai_character_media (character_id, gif_file_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET gif_file_id=$2, updated_at=NOW()
                """, char_id, file_id)
            await message.answer(
                f"✅ GIF для {emoji} <b>{char_id}</b> сохранён!\n\n"
                f"Отправь ещё медиа или нажми /admin для выхода.",
                parse_mode="HTML"
            )
    elif message.photo:
        file_id = message.photo[-1].file_id
        if caption == "hot":
            # Hot photo (intimate, 50 stars)
            async with _db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ai_character_media (character_id, hot_photo_file_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET hot_photo_file_id=$2, updated_at=NOW()
                """, char_id, file_id)
            await message.answer(
                f"🔥 Hot фото для {emoji} <b>{char_id}</b> сохранено!\n\n"
                f"Отправь ещё медиа или нажми /admin для выхода.",
                parse_mode="HTML"
            )
        else:
            # Regular paid photo (15 stars)
            async with _db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ai_character_media (character_id, photo_file_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET photo_file_id=$2, updated_at=NOW()
                """, char_id, file_id)
            await message.answer(
                f"✅ Фото для {emoji} <b>{char_id}</b> сохранено!\n\n"
                f"Отправь фото с подписью hot для горячего фото.\n"
                f"Или отправь ещё медиа / /admin для выхода.",
                parse_mode="HTML"
            )
    elif message.text and message.text.startswith("/"):
        await state.clear()
        return  # Let other handlers process commands
    else:
        await message.answer(
            "⚠️ Отправь GIF, фото, или с подписью hot.\n"
            "Или /admin для выхода."
        )


_FIELD_LABELS = {
    "gif_file_id": "GIF",
    "photo_file_id": "Фото",
    "hot_photo_file_id": "Hot фото",
    "hot_gif_file_id": "Hot GIF",
}


@router.callback_query(F.data.startswith("cmview:"), StateFilter("*"))
async def char_media_view(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != _admin_id:
        await callback.answer()
        return
    _, char_id, field = callback.data.split(":", 2)
    if field not in _FIELD_LABELS:
        await callback.answer("Неизвестный слот", show_alert=True)
        return
    async with _db_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {field} FROM ai_character_media WHERE character_id=$1",
            char_id
        )
    if not row or not row[field]:
        await callback.answer("Файл не найден", show_alert=True)
        return
    file_id = row[field]
    label = _FIELD_LABELS.get(field, field)
    try:
        if "gif" in field:
            await _bot.send_animation(callback.from_user.id, file_id,
                caption=f"{label} — {char_id}")
        else:
            await _bot.send_photo(callback.from_user.id, file_id,
                caption=f"{label} — {char_id}")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("cmdel:"), StateFilter("*"))
async def char_media_delete(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != _admin_id:
        await callback.answer()
        return
    _, char_id, field = callback.data.split(":", 2)
    if field not in _FIELD_LABELS:
        await callback.answer("Неизвестный слот", show_alert=True)
        return
    async with _db_pool.acquire() as conn:
        await conn.execute(
            f"UPDATE ai_character_media SET {field}=NULL, updated_at=NOW() WHERE character_id=$1",
            char_id
        )
    label = _FIELD_LABELS[field]
    await callback.answer(f"🗑 {label} удалён для {char_id}", show_alert=True)
    # Refresh the media view
    try:
        await callback.message.delete()
    except Exception:
        pass
    # Re-trigger char media select
    callback.data = f"charmedia:{char_id}"
    await char_media_select(callback, state)
