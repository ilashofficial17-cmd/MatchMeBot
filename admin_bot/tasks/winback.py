"""
Admin Bot — winback_task(): win-back сообщения + подарки возвращения.
Перенесено из admin.py. Отправка через main_bot (BOT_TOKEN).
"""

import asyncio
import logging
from datetime import datetime, timedelta

from locales import t
from keyboards import kb_main, kb_premium

logger = logging.getLogger("admin-bot")

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


async def winback_task(main_bot, db_pool):
    """Каждый час: win-back + подарки возвращения."""
    while True:
        await asyncio.sleep(3600)
        try:
            now = datetime.now()
            async with db_pool.acquire() as conn:
                rows_expiring = await conn.fetch("""
                    SELECT uid, lang, premium_until, winback_stage FROM users
                    WHERE premium_until IS NOT NULL
                    AND premium_until != 'permanent'
                    AND winback_stage = 0
                    AND ban_until IS NULL AND accepted_rules = TRUE
                    LIMIT 50
                """)
                rows_expired = await conn.fetch("""
                    SELECT uid, lang, premium_expired_at, winback_stage FROM users
                    WHERE premium_expired_at IS NOT NULL
                    AND winback_stage BETWEEN 1 AND 3
                    AND premium_until IS NULL AND ban_until IS NULL
                    LIMIT 50
                """)

            sent = 0
            for row in rows_expiring:
                try:
                    p_until = datetime.fromisoformat(row["premium_until"])
                    hours_left = (p_until - now).total_seconds() / 3600
                    if 0 < hours_left <= 24:
                        uid = row["uid"]
                        u_lang = row.get("lang") or "ru"
                        msg = WINBACK_MESSAGES.get(u_lang, WINBACK_MESSAGES["ru"])[1]
                        await main_bot.send_message(uid, msg, reply_markup=kb_premium(u_lang))
                        async with db_pool.acquire() as conn:
                            await conn.execute("UPDATE users SET winback_stage=1 WHERE uid=$1", uid)
                        sent += 1
                except Exception:
                    pass

            # Transition expired premiums
            try:
                async with db_pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE users
                        SET premium_expired_at = NOW(), premium_until = NULL,
                            premium_tier = NULL, winback_stage = GREATEST(winback_stage, 1)
                        WHERE premium_until IS NOT NULL
                        AND premium_until != 'permanent'
                        AND premium_until < $1
                    """, now.isoformat())
            except Exception:
                pass

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
                    if stage == 1 and days_since >= 0.1:
                        next_stage = 2
                    elif stage == 2 and days_since >= 3:
                        next_stage = 3
                    elif stage == 3 and days_since >= 7:
                        next_stage = 4
                    if next_stage:
                        msg = WINBACK_MESSAGES.get(u_lang, WINBACK_MESSAGES["ru"]).get(next_stage)
                        if msg:
                            await main_bot.send_message(uid, msg, reply_markup=kb_premium(u_lang))
                            async with db_pool.acquire() as conn:
                                await conn.execute("UPDATE users SET winback_stage=$2 WHERE uid=$1", uid, next_stage)
                            sent += 1
                except Exception:
                    pass

            if sent:
                logger.info(f"Win-back: отправлено {sent}")

            # ===== ПОДАРКИ ВОЗВРАЩЕНИЯ =====
            from constants import RETURN_GIFT_TIERS, MAX_BONUS_ENERGY
            async with db_pool.acquire() as conn:
                inactive_users = await conn.fetch("""
                    SELECT uid, lang, last_seen, return_gift_stage, ai_energy_used, premium_until, bonus_energy
                    FROM users
                    WHERE last_seen < NOW() - INTERVAL '3 days'
                    AND ban_until IS NULL AND accepted_rules = TRUE
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
                        days_inactive = (now - last_seen).total_seconds() / 86400
                        current_stage = row.get("return_gift_stage", 0) or 0
                        chosen_tier = None
                        for tier_num in sorted(RETURN_GIFT_TIERS.keys(), reverse=True):
                            tier = RETURN_GIFT_TIERS[tier_num]
                            if days_inactive >= tier["days_min"] and tier_num > current_stage:
                                chosen_tier = tier_num
                                break
                        if not chosen_tier:
                            continue
                        tier_cfg = RETURN_GIFT_TIERS[chosen_tier]
                        cur_bonus = row.get("bonus_energy", 0) or 0
                        new_bonus_val = min(cur_bonus + tier_cfg["energy"], MAX_BONUS_ENERGY)
                        updates = {
                            "bonus_energy": new_bonus_val,
                            "return_gift_stage": chosen_tier,
                            "return_gift_given": now,
                            "return_gifts_total": (row.get("return_gifts_total", 0) or 0) + 1,
                        }
                        if tier_cfg["trial_days"] > 0 and not row.get("premium_until"):
                            trial_until = now + timedelta(days=tier_cfg["trial_days"])
                            updates["premium_until"] = trial_until.isoformat()
                            updates["premium_tier"] = "premium"
                        set_parts = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
                        vals = list(updates.values())
                        await conn.execute(f"UPDATE users SET {set_parts} WHERE uid=$1", uid_rg, *vals)
                        await main_bot.send_message(uid_rg, t(u_lang, f"return_gift_{chosen_tier}"), reply_markup=kb_main(u_lang))
                        rg_sent += 1
                    except Exception:
                        pass
                if rg_sent:
                    logger.info(f"Return gifts: отправлено {rg_sent}")

        except Exception as e:
            logger.error(f"winback_task error: {e}")
