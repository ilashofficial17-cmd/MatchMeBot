"""
Payment & Premium handlers extracted from bot.py.

All handlers use router = Router() instead of dp.
Dependencies are injected via init().
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
)

from locales import t, TEXTS
import redis_state

logger = logging.getLogger("matchme")

router = Router()

# ── Dependencies (set by init()) ──────────────────────────────────────────────
_bot = None
_db_pool = None
_use_redis = False
_admin_id = None

# helper functions
_get_user = None
_get_lang = None
_update_user = None
_is_premium = None
_get_premium_tier = None
_log_ab_event = None
_get_ab_group = None
_needs_onboarding_fn = None
_unavailable_fn = None

# keyboards
_kb_main = None
_kb_premium = None

# constants
_PREMIUM_PLANS = None
_GIFTS = None
_ENERGY_PACKS = None
_MAX_BONUS_ENERGY = None
_get_plan_price = None
_AB_PRICE_DISCOUNT_B = None


def _all(key):
    """All language variants for a locale key — for F.text.in_() filters."""
    return {TEXTS[lang][key] for lang in TEXTS if key in TEXTS[lang]}


def init(
    *,
    bot,
    db_pool,
    use_redis,
    admin_id,
    # helper functions
    get_user,
    get_lang,
    update_user,
    is_premium,
    get_premium_tier,
    log_ab_event,
    get_ab_group,
    needs_onboarding_fn,
    unavailable_fn,
    # keyboards
    kb_main,
    kb_premium,
    # constants
    PREMIUM_PLANS,
    GIFTS,
    ENERGY_PACKS,
    MAX_BONUS_ENERGY,
    get_plan_price,
    AB_PRICE_DISCOUNT_B,
):
    """Dependency injection — call once at startup before including the router."""
    global _bot, _db_pool, _use_redis, _admin_id
    global _get_user, _get_lang, _update_user, _is_premium, _get_premium_tier
    global _log_ab_event, _get_ab_group, _needs_onboarding_fn, _unavailable_fn
    global _kb_main, _kb_premium
    global _PREMIUM_PLANS, _GIFTS, _ENERGY_PACKS, _MAX_BONUS_ENERGY
    global _get_plan_price, _AB_PRICE_DISCOUNT_B

    _bot = bot
    _db_pool = db_pool
    _use_redis = use_redis
    _admin_id = admin_id

    _get_user = get_user
    _get_lang = get_lang
    _update_user = update_user
    _is_premium = is_premium
    _get_premium_tier = get_premium_tier
    _log_ab_event = log_ab_event
    _get_ab_group = get_ab_group
    _needs_onboarding_fn = needs_onboarding_fn
    _unavailable_fn = unavailable_fn

    _kb_main = kb_main
    _kb_premium = kb_premium

    _PREMIUM_PLANS = PREMIUM_PLANS
    _GIFTS = GIFTS
    _ENERGY_PACKS = ENERGY_PACKS
    _MAX_BONUS_ENERGY = MAX_BONUS_ENERGY
    _get_plan_price = get_plan_price
    _AB_PRICE_DISCOUNT_B = AB_PRICE_DISCOUNT_B


# ====================== ТРИАЛ PREMIUM ======================
@router.callback_query(F.data == "trial:activate", StateFilter("*"))
async def activate_trial(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    u = await _get_user(uid)
    if not u:
        await callback.answer()
        return
    if u.get("trial_used"):
        await callback.answer(t(lang, "trial_already_used"), show_alert=True)
        return
    if await _is_premium(uid):
        await callback.answer(t(lang, "channel_already_premium"), show_alert=True)
        # Уже Premium — помечаем триал как использованный, не трогаем подписку
        await _update_user(uid, trial_used=True)
        return
    base = datetime.now()
    current_until = u.get("premium_until")
    if current_until and current_until != "permanent":
        try:
            existing = datetime.fromisoformat(current_until)
            if existing > base:
                base = existing
        except Exception:
            pass
    until = base + timedelta(days=3)
    await _update_user(uid, premium_until=until.isoformat(), premium_tier="premium", trial_used=True)
    await _log_ab_event(uid, "trial_activated")
    try:
        await callback.message.edit_text(t(lang, "trial_activated", until=until.strftime('%d.%m.%Y %H:%M')))
    except Exception:
        pass
    await callback.answer()


# ====================== PREMIUM MENU ======================
@router.message(Command("premium"), StateFilter("*"))
async def cmd_premium(message: types.Message, state):
    if await _needs_onboarding_fn(message, state):
        return
    uid = message.from_user.id
    lang = await _get_lang(uid)
    user_tier = await _get_premium_tier(uid)
    u = await _get_user(uid)
    status_text = ""
    if user_tier:
        if uid == _admin_id or (u and u.get("premium_until") == "permanent"):
            status_text = t(lang, "premium_status_eternal", tier="Premium")
        else:
            p_until = (u.get("premium_until") or "") if u else ""
            try:
                until = datetime.fromisoformat(p_until)
                status_text = t(lang, "premium_status_until", tier="Premium", until=until.strftime('%d.%m.%Y'))
            except Exception:
                status_text = t(lang, "premium_status_eternal", tier="Premium")
    ab_group = u.get("ab_group") if u else None
    prices = {k: _get_plan_price(k, lang, ab_group) for k in _PREMIUM_PLANS}
    await message.answer(t(lang, "premium_title", status=status_text), reply_markup=_kb_premium(lang, plan_prices=prices))


@router.callback_query(F.data == "premium_show", StateFilter("*"))
async def premium_show_cb(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    user_tier = await _get_premium_tier(uid)
    u = await _get_user(uid)
    status_text = ""
    if user_tier:
        if uid == _admin_id or (u and u.get("premium_until") == "permanent"):
            status_text = t(lang, "premium_status_eternal", tier="Premium")
        else:
            p_until = (u.get("premium_until") or "") if u else ""
            try:
                until = datetime.fromisoformat(p_until)
                status_text = t(lang, "premium_status_until", tier="Premium", until=until.strftime('%d.%m.%Y'))
            except Exception:
                status_text = t(lang, "premium_status_eternal", tier="Premium")
    ab_group = u.get("ab_group") if u else None
    prices = {k: _get_plan_price(k, lang, ab_group) for k in _PREMIUM_PLANS}
    await callback.message.answer(t(lang, "premium_title", status=status_text), reply_markup=_kb_premium(lang, plan_prices=prices))
    await callback.answer()


@router.callback_query(F.data == "buy:info", StateFilter("*"))
async def premium_info(callback: types.CallbackQuery):
    lang = await _get_lang(callback.from_user.id)
    await callback.message.answer(t(lang, "premium_info"))
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"), StateFilter("*"))
async def buy_premium(callback: types.CallbackQuery):
    uid = callback.from_user.id
    plan_key = callback.data.split(":", 1)[1]
    if plan_key not in _PREMIUM_PLANS:
        lang = await _get_lang(callback.from_user.id)
        await callback.answer(t(lang, "premium_unknown_plan"), show_alert=True)
        return
    plan = _PREMIUM_PLANS[plan_key]
    lang = await _get_lang(uid)
    u = await _get_user(uid)
    ab_group = u.get("ab_group") if u else None
    label = t(lang, plan["label_key"])
    desc = t(lang, plan["desc_key"])
    stars = _get_plan_price(plan_key, lang, ab_group)
    # Логируем A/B ценовой тест
    await _log_ab_event(uid, "price_shown", f"{plan_key}:{stars}")
    await callback.answer()
    await _bot.send_invoice(
        chat_id=uid,
        title=f"MatchMe Premium — {label}",
        description=t(lang, "invoice_desc", tier="Premium", label=label, desc=desc),
        payload=f"premium_{plan_key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Premium {label}", amount=stars)],
    )


# ====================== GIFT PAYMENT HELPER ======================
async def _handle_gift_payment(uid, payload):
    """Process a gift payment: grant premium to recipient."""
    parts = payload.split("_", 2)
    if len(parts) != 3:
        return
    gift_type = parts[1]
    try:
        partner_uid = int(parts[2])
    except ValueError:
        logger.warning(f"Invalid gift payload: {payload}")
        return
    gift = _GIFTS.get(gift_type)
    if not gift:
        return
    lang = await _get_lang(uid)
    p_lang = await _get_lang(partner_uid)

    # Grant premium to partner
    base = datetime.now()
    p_user = await _get_user(partner_uid)
    if p_user:
        current_until = p_user.get("premium_until")
        if current_until and current_until != "permanent":
            try:
                existing = datetime.fromisoformat(current_until)
                if existing > base:
                    base = existing
            except Exception:
                pass
    until = base + timedelta(days=gift["days"])
    await _update_user(partner_uid, premium_until=until.isoformat(), premium_tier="premium",
                       winback_stage=0, premium_expired_at=None)

    # Sender confirmation
    try:
        await _bot.send_message(uid, t(lang, "gift_sent", emoji=gift["emoji"], days=gift["days"]))
    except Exception:
        pass

    # Recipient "opening" visual
    try:
        opening_msg = await _bot.send_message(partner_uid, t(p_lang, "gift_opening"))
        await asyncio.sleep(1.5)
        await opening_msg.edit_text(
            t(p_lang, "gift_received",
              emoji=gift["emoji"],
              gift_name=t(p_lang, f"gift_{gift_type}"),
              days=gift["days"],
              until=until.strftime('%d.%m.%Y'))
        )
    except Exception:
        try:
            await _bot.send_message(partner_uid,
                t(p_lang, "gift_received",
                  emoji=gift["emoji"],
                  gift_name=t(p_lang, f"gift_{gift_type}"),
                  days=gift["days"],
                  until=until.strftime('%d.%m.%Y')))
        except Exception:
            pass
    await _log_ab_event(uid, "gift_sent", gift_type)


# ====================== CHECKOUT ======================
@router.pre_checkout_query(StateFilter("*"))
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment, StateFilter("*"))
async def successful_payment(message: types.Message):
    uid = message.from_user.id
    payload = message.successful_payment.invoice_payload

    # Gift payments
    if payload.startswith("gift_"):
        await _handle_gift_payment(uid, payload)
        return

    # Energy pack payments
    if payload.startswith("energy_"):
        pack_key = payload[len("energy_"):]
        pack = _ENERGY_PACKS.get(pack_key)
        if not pack:
            logger.warning(f"Unknown energy pack: {pack_key}")
            return
        lang = await _get_lang(uid)
        u = await _get_user(uid)
        bonus = u.get("bonus_energy", 0) if u else 0
        new_bonus = min(bonus + pack["amount"], _MAX_BONUS_ENERGY)
        await _update_user(uid, bonus_energy=new_bonus)
        await message.answer(t(lang, "energy_purchased", amount=pack["amount"]))
        return

    plan_key = payload.replace("premium_", "")
    if plan_key not in _PREMIUM_PLANS:
        logger.warning(f"Invalid plan_key in payload: {plan_key}")
        return
    plan = _PREMIUM_PLANS[plan_key]
    u = await _get_user(uid)
    base = datetime.now()
    # Продлеваем от текущей даты окончания если есть
    if u:
        current_until = u.get("premium_until")
        if current_until and current_until != "permanent":
            try:
                existing = datetime.fromisoformat(current_until)
                if existing > base:
                    base = existing
            except Exception:
                pass
    until = base + timedelta(days=plan["days"])
    await _update_user(uid, premium_until=until.isoformat(), premium_tier="premium",
                       winback_stage=0, premium_expired_at=None)
    await _log_ab_event(uid, "purchase", plan_key)
    lang = await _get_lang(uid)
    label = t(lang, plan["label_key"])
    await message.answer(
        t(lang, "premium_activated",
          tier="Premium",
          label=label,
          until=until.strftime('%d.%m.%Y'),
          benefits=t(lang, "benefit_premium")),
        reply_markup=_kb_main(lang)
    )
