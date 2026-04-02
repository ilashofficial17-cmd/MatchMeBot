import logging
from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.types import LabeledPrice

from locales import t
from keyboards import kb_energy_shop
from constants import ENERGY_PACKS, PRICE_MULTIPLIERS

router = Router()
logger = logging.getLogger("matchme")

# ====================== Injected dependencies ======================
_bot = None
_get_user = None
_update_user = None
_get_lang = None


def setup(bot, get_user, update_user, get_lang):
    global _bot, _get_user, _update_user, _get_lang
    _bot = bot
    _get_user = get_user
    _update_user = update_user
    _get_lang = get_lang


def _energy_bar(left: int, total: int) -> str:
    """Visual energy bar."""
    pct = left / total if total > 0 else 0
    filled = round(pct * 10)
    bar = "▰" * filled + "▱" * (10 - filled)
    return bar


@router.callback_query(F.data == "energy_shop", StateFilter("*"))
async def energy_shop_show(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    u = await _get_user(uid)
    from ai_chat import DAILY_ENERGY
    from ai_chat import get_energy_info
    from datetime import datetime
    user_tier = None
    try:
        from ai_chat import _get_premium_tier
        user_tier = await _get_premium_tier(uid)
    except Exception:
        pass
    ai_bonus = u.get("ai_bonus", 0) if u else 0
    tier_key = "premium" if user_tier else "free"
    max_energy = DAILY_ENERGY.get(tier_key, 30) + ai_bonus
    energy_used = u.get("ai_energy_used", 0) if u else 0
    reset_time = u.get("ai_messages_reset") if u else None
    if reset_time and (datetime.now() - reset_time).total_seconds() > 86400:
        energy_used = 0
    energy_left = max(max_energy - energy_used, 0)
    bar = _energy_bar(energy_left, max_energy)
    # Calculate reset time remaining
    if reset_time:
        elapsed = (datetime.now() - reset_time).total_seconds()
        remaining = max(0, 86400 - elapsed)
        hrs = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
    else:
        hrs, mins = 24, 0
    await callback.message.answer(
        t(lang, "energy_shop_title",
          left=energy_left, max=max_energy, bar=bar,
          hours=hrs, mins=mins),
        reply_markup=kb_energy_shop(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("energy_buy:"), StateFilter("*"))
async def energy_buy(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = await _get_lang(uid)
    pack_key = callback.data.split(":", 1)[1]
    if pack_key == "back":
        await callback.answer()
        try:
            await callback.message.delete()
        except Exception:
            pass
        return
    if pack_key not in ENERGY_PACKS:
        await callback.answer(t(lang, "energy_pack_not_found"), show_alert=True)
        return
    pack = ENERGY_PACKS[pack_key]
    mult = PRICE_MULTIPLIERS.get(lang, 2.0)
    price = int(pack["stars"] * mult)
    label = t(lang, pack["label_key"])
    await callback.answer()
    await _bot.send_invoice(
        chat_id=uid,
        title=t(lang, "energy_invoice_title"),
        description=t(lang, "energy_invoice_desc", amount=pack["amount"], label=label),
        payload=f"energy_{pack_key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=price)],
    )
