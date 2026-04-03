"""
Admin Bot — маркетинг: mkt:* хэндлеры.
Перенесено из admin.py.
"""

import logging
from datetime import timedelta

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import ADMIN_ID
import admin_bot.db as _db

logger = logging.getLogger("admin-bot")

router = Router()

# AI_CHARACTERS для аналитики
try:
    from ai_characters import AI_CHARACTERS
except ImportError:
    AI_CHARACTERS = {}


async def show_marketing_menu(callback: types.CallbackQuery):
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


@router.callback_query(F.data.startswith("mkt:"), StateFilter("*"))
async def marketing_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]

    if action == "creatives":
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
        # Get partner ads from config if available
        try:
            from bot import PARTNER_ADS
        except ImportError:
            PARTNER_ADS = []

        if lang_filter == "all":
            text = "📋 Сводка креативов:\n\n"
            seen = {}
            for ad in PARTNER_ADS:
                base = ad["text_key"].rsplit("_", 1)[0]
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
            text += f"Всего: {len(PARTNER_ADS)} креативов"
            await callback.message.answer(text)
        else:
            ads = [ad for ad in PARTNER_ADS if ad["langs"] is None or lang_filter in ad["langs"]]
            if not ads:
                await callback.message.answer(f"Нет креативов для {lang_filter.upper()}")
            else:
                from locales import TEXTS
                for i, ad in enumerate(ads):
                    modes_str = ", ".join(ad["modes"]) if ad["modes"] else "все"
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
                    if i >= 14:
                        await callback.message.answer(f"... и ещё {len(ads) - 15}")
                        break

    elif action == "ad_stats":
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
        async with _db.db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT ad_key, source, COUNT(*) as cnt
                FROM ad_events
                WHERE event_type = 'impression' {period_cond}
                GROUP BY ad_key, source ORDER BY cnt DESC
            """)
            total_impressions = await conn.fetchval(f"""
                SELECT COUNT(*) FROM ad_events WHERE event_type = 'impression' {period_cond}
            """) or 0
            total_clicks = await conn.fetchval(f"""
                SELECT COUNT(*) FROM ad_events WHERE event_type = 'click' {period_cond}
            """) or 0
            unique_users = await conn.fetchval(f"""
                SELECT COUNT(DISTINCT uid) FROM ad_events WHERE event_type = 'impression' {period_cond}
            """) or 0
            click_rows = await conn.fetch(f"""
                SELECT ad_key, source, COUNT(*) as cnt
                FROM ad_events WHERE event_type = 'click' {period_cond}
                GROUP BY ad_key, source
            """)
        overall_ctr = round(total_clicks / max(total_impressions, 1) * 100, 1)
        text = f"📊 Аналитика рекламы ({period_label})\n\n"
        text += f"Показов: {total_impressions} | Кликов: {total_clicks}\n"
        text += f"CTR: {overall_ctr}%\nУник. пользователей: {unique_users}\n\n"
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
        from admin_bot.db import get_stat
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
        await callback.message.answer(text)

    elif action == "revenue":
        async with _db.db_pool.acquire() as conn:
            total_premiums = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL AND premium_until != 'permanent'"
            ) or 0
            purchases_total = await conn.fetchval("SELECT COUNT(*) FROM ab_events WHERE event_type = 'purchase'") or 0
            purchases_week = await conn.fetchval(
                "SELECT COUNT(*) FROM ab_events WHERE event_type = 'purchase' AND created_at > NOW() - INTERVAL '7 days'"
            ) or 0
            gifts_total = await conn.fetchval("SELECT COUNT(*) FROM ab_events WHERE event_type = 'gift_sent'") or 0
            gifts_week = await conn.fetchval(
                "SELECT COUNT(*) FROM ab_events WHERE event_type = 'gift_sent' AND created_at > NOW() - INTERVAL '7 days'"
            ) or 0
            trials_total = await conn.fetchval("SELECT COUNT(*) FROM ab_events WHERE event_type = 'trial_activated'") or 0
            trials_conv = await conn.fetchval("SELECT COUNT(*) FROM ab_events WHERE event_type = 'trial_shown'") or 1
        text = f"💰 Доходы MatchMe\n\n"
        text += f"💎 Активных Premium: {total_premiums}\n\n"
        text += f"🛒 Покупки:\n  Всего: {purchases_total}\n  За 7 дней: {purchases_week}\n\n"
        text += f"🎁 Подарки:\n  Всего: {gifts_total}\n  За 7 дней: {gifts_week}\n\n"
        text += f"🎟 Триалы:\n  Активировано: {trials_total}\n  Показано: {trials_conv}\n"
        text += f"  Конверсия: {round(trials_total / max(trials_conv, 1) * 100, 1)}%"
        await callback.message.answer(text)

    elif action == "ratings":
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
        await callback.message.answer(text)

    elif action == "ab_prices":
        text = ""
        async with _db.db_pool.acquire() as conn:
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
                    text = f"🔬 A/B тест цен\n\nГруппа A (полная цена):\n"
                else:
                    text += f"\nГруппа B (скидка 15%):\n"
                conv = round(purchased / max(shown, 1) * 100, 1)
                text += f"  Юзеров: {users_total}\n  Показов цен: {shown}\n"
                text += f"  Покупок: {purchased} (конверсия: {conv}%)\n  Триалов: {trials}\n"
        await callback.message.answer(text)

    elif action == "cohorts":
        async with _db.db_pool.acquire() as conn:
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
                purchases = await conn.fetchval("""
                    SELECT COUNT(*) FROM ab_events e JOIN users u ON e.uid = u.uid
                    WHERE u.created_at >= NOW() - $1::interval AND u.created_at < NOW() - $2::interval
                    AND e.event_type = 'purchase'
                """, start_iv, end_iv) or 0
                gifts = await conn.fetchval("""
                    SELECT COUNT(*) FROM ab_events e JOIN users u ON e.uid = u.uid
                    WHERE u.created_at >= NOW() - $1::interval AND u.created_at < NOW() - $2::interval
                    AND e.event_type = 'gift_sent'
                """, start_iv, end_iv) or 0
                active_now = await conn.fetchval("""
                    SELECT COUNT(*) FROM users
                    WHERE created_at >= NOW() - $1::interval AND created_at < NOW() - $2::interval
                    AND last_seen > NOW() - INTERVAL '7 days'
                """, start_iv, end_iv) or 0
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
                text += f"  Подарков: {gifts}\n  Ср. чатов: {avg_chats}\n\n"
            if "📅" not in text:
                text += "Нет данных. Когорты начнут формироваться по мере регистрации юзеров."
        await callback.message.answer(text)

    await callback.answer()
