from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from locales import t
from constants import ENERGY_PACKS, get_price

CHANNEL_ID = "@MATCHMEHUB"

# INTERESTS_MAP: значения хранятся в БД как ключи локализации
INTERESTS_MAP = {
    "simple": ["int_talk", "int_humor", "int_advice", "int_music", "int_games"],
    "flirt":  ["int_flirt_light", "int_compliments", "int_sexting", "int_virtual_date", "int_flirt_games"],
    "kink":   ["int_bdsm", "int_bondage", "int_roleplay", "int_domsub", "int_petplay", "int_other_fetish"],
}

# ====================== KEYBOARDS ======================

def kb_main(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_search")), KeyboardButton(text=t(lang, "btn_find"))],
        [KeyboardButton(text=t(lang, "btn_ai_chat")), KeyboardButton(text=t(lang, "btn_profile"))],
        [KeyboardButton(text=t(lang, "btn_quests")), KeyboardButton(text=t(lang, "btn_settings"))],
        [KeyboardButton(text=t(lang, "btn_help"))],
    ], resize_keyboard=True)


def kb_lang():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇬🇧 English"), KeyboardButton(text="🇪🇸 Español")]
    ], resize_keyboard=True)


def kb_privacy(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_accept_privacy"), callback_data="privacy:accept")],
        [InlineKeyboardButton(text=t(lang, "btn_decline_privacy"), callback_data="privacy:decline")],
    ])


def kb_rules(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_accept_rules"))]
    ], resize_keyboard=True)


def kb_rules_profile(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_start_form"))]
    ], resize_keyboard=True)


def kb_cancel_reg(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_cancel_reg"))]
    ], resize_keyboard=True)


def kb_gender(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_male")), KeyboardButton(text=t(lang, "btn_female"))],
        [KeyboardButton(text=t(lang, "btn_other"))],
        [KeyboardButton(text=t(lang, "btn_cancel_reg"))],
    ], resize_keyboard=True)


def kb_mode(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_mode_simple"))],
        [KeyboardButton(text=t(lang, "btn_mode_flirt"))],
        [KeyboardButton(text=t(lang, "btn_mode_kink"))],
        [KeyboardButton(text=t(lang, "btn_cancel_reg"))],
    ], resize_keyboard=True)


def kb_cancel_search(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_cancel_search"))]
    ], resize_keyboard=True)


def kb_chat(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_like")), KeyboardButton(text=t(lang, "btn_topic"))],
        [KeyboardButton(text=t(lang, "btn_next")), KeyboardButton(text=t(lang, "btn_stop"))],
        [KeyboardButton(text=t(lang, "btn_complaint")), KeyboardButton(text=t(lang, "btn_home"))],
    ], resize_keyboard=True)


def kb_search_gender(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_find_male")), KeyboardButton(text=t(lang, "btn_find_female"))],
        [KeyboardButton(text=t(lang, "btn_find_other")), KeyboardButton(text=t(lang, "btn_find_any"))],
        [KeyboardButton(text=t(lang, "btn_back"))],
    ], resize_keyboard=True)


def kb_after_chat(partner_uid, lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_continue"), callback_data=f"mutual:{partner_uid}")],
        [InlineKeyboardButton(text=t(lang, "btn_find_new"), callback_data="goto:find")],
        [InlineKeyboardButton(text=t(lang, "btn_to_menu"), callback_data="goto:menu")],
    ])


def kb_channel_bonus(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📢 {CHANNEL_ID}", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
        [InlineKeyboardButton(text=t(lang, "btn_check_channel"), callback_data="channel:check")],
        [InlineKeyboardButton(text=t(lang, "btn_skip_channel"), callback_data="channel:skip")],
    ])


def kb_ai_characters(user_tier=None, mode="simple", lang="ru"):
    buttons = []
    # Блок 1 — Общение
    buttons.append([InlineKeyboardButton(text=t(lang, "ai_block_simple"), callback_data="noop")])
    buttons.append([
        InlineKeyboardButton(text=t(lang, "char_luna"), callback_data="aichar:luna"),
        InlineKeyboardButton(text=t(lang, "char_max_simple"), callback_data="aichar:max_simple"),
    ])
    buttons.append([
        InlineKeyboardButton(text=t(lang, "char_aurora"), callback_data="aichar:aurora"),
        InlineKeyboardButton(text=t(lang, "char_alex"), callback_data="aichar:alex"),
    ])
    # Блок 2 — Флирт
    buttons.append([InlineKeyboardButton(text=t(lang, "ai_block_flirt"), callback_data="noop")])
    buttons.append([
        InlineKeyboardButton(text=t(lang, "char_mia"), callback_data="aichar:mia"),
        InlineKeyboardButton(text=t(lang, "char_kai"), callback_data="aichar:kai"),
    ])
    buttons.append([
        InlineKeyboardButton(text=t(lang, "char_diana"), callback_data="aichar:diana"),
        InlineKeyboardButton(text=t(lang, "char_leon"), callback_data="aichar:leon"),
    ])
    # Блок 3 — Kink
    buttons.append([InlineKeyboardButton(text=t(lang, "ai_block_kink"), callback_data="noop")])
    buttons.append([
        InlineKeyboardButton(text=t(lang, "char_lilit"), callback_data="aichar:lilit"),
        InlineKeyboardButton(text=t(lang, "char_eva"), callback_data="aichar:eva"),
    ])
    buttons.append([
        InlineKeyboardButton(text=t(lang, "char_damir"), callback_data="aichar:damir"),
        InlineKeyboardButton(text=t(lang, "char_ars"), callback_data="aichar:ars"),
    ])
    buttons.append([
        InlineKeyboardButton(text=t(lang, "char_master"), callback_data="aichar:master"),
    ])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_buy_energy"), callback_data="energy_shop")])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_ai_info"), callback_data="aichar:info")])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="aichar:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_ai_chat(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_change_char")), KeyboardButton(text=t(lang, "btn_end_ai_chat"))],
        [KeyboardButton(text=t(lang, "btn_erase_memory")), KeyboardButton(text=t(lang, "btn_find_live"))],
    ], resize_keyboard=True)


def kb_interests(mode, selected, lang="ru"):
    interest_keys = INTERESTS_MAP.get(mode, [])
    buttons = []
    for key in interest_keys:
        mark = "✅ " if key in selected else ""
        buttons.append([InlineKeyboardButton(text=f"{mark}{t(lang, key)}", callback_data=f"int:{key}")])
    buttons.append([InlineKeyboardButton(text="✅ " + t(lang, "edit_done"), callback_data="int:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_complaint(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "rep_minor"), callback_data="rep:minor")],
        [InlineKeyboardButton(text=t(lang, "rep_spam"), callback_data="rep:spam")],
        [InlineKeyboardButton(text=t(lang, "rep_abuse"), callback_data="rep:abuse")],
        [InlineKeyboardButton(text=t(lang, "rep_nsfw"), callback_data="rep:nsfw")],
        [InlineKeyboardButton(text=t(lang, "rep_other"), callback_data="rep:other")],
        [InlineKeyboardButton(text=t(lang, "rep_cancel"), callback_data="rep:cancel")],
    ])


def kb_edit(lang="ru", show_premium_btn=False):
    buttons = [
        [InlineKeyboardButton(text=t(lang, "edit_btn_name"), callback_data="edit:name"),
         InlineKeyboardButton(text=t(lang, "edit_btn_age"), callback_data="edit:age")],
        [InlineKeyboardButton(text=t(lang, "edit_btn_gender"), callback_data="edit:gender"),
         InlineKeyboardButton(text=t(lang, "edit_btn_mode"), callback_data="edit:mode")],
        [InlineKeyboardButton(text=t(lang, "edit_btn_interests"), callback_data="edit:interests")],
    ]
    if show_premium_btn:
        buttons.append([InlineKeyboardButton(text=t(lang, "settings_buy_premium"), callback_data="premium_show")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_complaint_action(complaint_id, accused_uid, reporter_uid, has_log=False, stop_words=False, lang="ru"):
    sw_text = t(lang, "adm_stopwords_yes") if stop_words else t(lang, "adm_stopwords_no")
    buttons = [[InlineKeyboardButton(text=sw_text, callback_data="noop")]]
    if has_log:
        buttons.append([InlineKeyboardButton(text=t(lang, "adm_show_log"), callback_data=f"clog:show:{complaint_id}")])
    buttons += [
        [InlineKeyboardButton(text=t(lang, "adm_ban3"), callback_data=f"cadm:ban3:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_ban24"), callback_data=f"cadm:ban24:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_banperm"), callback_data=f"cadm:banperm:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_warn"), callback_data=f"cadm:warn:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_warn_rep"), callback_data=f"cadm:warnrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_ban_rep"), callback_data=f"cadm:banrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_shadow"), callback_data=f"cadm:shadow:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_dismiss"), callback_data=f"cadm:dismiss:{complaint_id}:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_user_actions(target_uid, is_shadow=False, lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "adm_uban3"), callback_data=f"uadm:ban3:{target_uid}"),
         InlineKeyboardButton(text=t(lang, "adm_uban24"), callback_data=f"uadm:ban24:{target_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_ubanperm"), callback_data=f"uadm:banperm:{target_uid}"),
         InlineKeyboardButton(text=t(lang, "adm_unban_btn"), callback_data=f"uadm:unban:{target_uid}")],
        [InlineKeyboardButton(
            text=t(lang, "adm_shadow_remove") if is_shadow else t(lang, "adm_shadow_set"),
            callback_data=f"uadm:shadowtoggle:{target_uid}",
        )],
        [InlineKeyboardButton(text=t(lang, "adm_uwarn"), callback_data=f"uadm:warn:{target_uid}"),
         InlineKeyboardButton(text=t(lang, "adm_kick"), callback_data=f"uadm:kick:{target_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_give_premium"), callback_data=f"uadm:premium:{target_uid}"),
         InlineKeyboardButton(text=t(lang, "adm_take_premium"), callback_data=f"uadm:unpremium:{target_uid}")],
        [InlineKeyboardButton(text=t(lang, "adm_fulldelete"), callback_data=f"uadm:fulldelete:{target_uid}")],
    ])


def kb_premium(lang="ru", plan_prices: dict | None = None):
    """plan_prices: {"7d": 129, "1m": 349, ...} — цены с учётом региона."""
    buttons = []
    plan_labels = {"7d": "plan_label_7d", "1m": "plan_label_1m", "3m": "plan_label_3m"}
    plan_badges = {"7d": "", "1m": "🔥 ", "3m": "💎 "}
    plan_discounts = {
        "7d": "",
        "1m": "",
        "3m": {"ru": " (-28%)", "en": " (-28%)", "es": " (-28%)"},
    }
    for key in ("7d", "1m", "3m"):
        label = t(lang, plan_labels[key])
        badge = plan_badges[key]
        discount = plan_discounts[key]
        discount_text = discount.get(lang, discount.get("ru", "")) if isinstance(discount, dict) else discount
        if plan_prices and key in plan_prices:
            price = plan_prices[key]
            buttons.append([InlineKeyboardButton(
                text=f"{badge}{label} — {price} ⭐{discount_text}",
                callback_data=f"buy:{key}"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text=t(lang, f"prem_{key}"), callback_data=f"buy:{key}"
            )])
    buttons.append([InlineKeyboardButton(text=t(lang, "prem_compare"), callback_data="buy:info")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_energy_shop(lang="ru"):
    buttons = []
    pack_list = list(ENERGY_PACKS.items())
    for i, (key, pack) in enumerate(pack_list):
        price = get_price(key, lang)
        label = t(lang, pack["label_key"])
        badge = ""
        if i == 1:
            badge = " 🔥"
        elif i == 2:
            badge = " 💎"
        buttons.append([InlineKeyboardButton(
            text=f"{pack['emoji']} {label} — {price} ⭐{badge}",
            callback_data=f"energy_buy:{key}"
        )])
    buttons.append([InlineKeyboardButton(text=t(lang, "energy_shop_premium_cta"), callback_data="premium_show")])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="energy_buy:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
