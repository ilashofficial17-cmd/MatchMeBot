"""
MatchMe Bot — Constants and configuration.
Extracted from bot.py to reduce file size.
"""
from locales import TEXTS

# ====================== PRICING ======================
PRICE_MULTIPLIERS = {"ru": 1.0, "es": 1.3, "en": 2.0}

PREMIUM_PLANS = {
    "7d":  {"stars": 129,  "days": 7,   "label_key": "plan_label_7d",  "desc_key": "plan_desc_try",      "tier": "premium"},
    "1m":  {"stars": 349,  "days": 30,  "label_key": "plan_label_1m",  "desc_key": "plan_desc_popular",  "tier": "premium"},
    "3m":  {"stars": 749,  "days": 90,  "label_key": "plan_label_3m",  "desc_key": "plan_desc_discount", "tier": "premium"},
}

ENERGY_PACKS = {
    "e10":  {"stars": 29,  "amount": 10,  "label_key": "energy_pack_10",  "emoji": "🔋"},
    "e50":  {"stars": 99,  "amount": 50,  "label_key": "energy_pack_50",  "emoji": "🔋🔋"},
    "e150": {"stars": 249, "amount": 150, "label_key": "energy_pack_150", "emoji": "🔋🔋🔋"},
}

AB_PRICE_DISCOUNT_B = 0.85

GIFTS = {
    "rose":    {"emoji": "🌹", "days": 1, "stars": 19},
    "diamond": {"emoji": "💎", "days": 3, "stars": 49},
    "crown":   {"emoji": "👑", "days": 7, "stars": 99},
}


def get_plan_price(plan_key: str, lang: str, ab_group: str = None) -> int:
    """Returns plan price in Stars adjusted for region and A/B group."""
    base = PREMIUM_PLANS[plan_key]["stars"]
    mult = PRICE_MULTIPLIERS.get(lang, 2.0)
    price = int(base * mult)
    if ab_group == "B":
        price = int(price * AB_PRICE_DISCOUNT_B)
    return price


def get_chat_topics(lang: str) -> list:
    return TEXTS.get(lang, TEXTS["ru"]).get("chat_topics", TEXTS["ru"]["chat_topics"])


# ====================== LEVELS & STREAKS ======================
LEVEL_THRESHOLDS = [0, 10, 30, 75, 150, 300]
LEVEL_NAMES = {
    0: "level_0", 1: "level_1", 2: "level_2",
    3: "level_3", 4: "level_4", 5: "level_5",
}
STREAK_BONUSES = {3: 5, 7: 10, 14: 15, 30: 20}


# ====================== STOP WORDS ======================
STOP_WORDS = [
    "предлагаю услуги", "оказываю услуги", "интим услуги",
    "досуг", "escort", "эскорт", "проститутка", "проститут",
    "вирт за деньги", "вирт платно", "за донат",
    "подпишись на канал", "перейди по ссылке", "мой канал",
    "казино", "ставки на спорт", "заработок в телеграм",
    "крипта х10", "пассивный доход",
    "мне 12", "мне 13", "мне 14", "мне 15",
    "школьница ищу", "школьник ищу", "продаю", "порно за деньги",
]


# ====================== PARTNER ADS ======================
PARTNER_ADS = [
    # --- Dzen VPN — только RU ---
    {
        "text_key": "ad_dzen_1",
        "url": "https://t.me/vpn_dzen_bot?start=_tgr_sp0QqEc0YmVi",
        "btn_key": "btn_ad_connect",
        "langs": ["ru"],
        "modes": None,
    },
    {
        "text_key": "ad_dzen_2",
        "url": "https://t.me/vpn_dzen_bot?start=_tgr_sp0QqEc0YmVi",
        "btn_key": "btn_ad_connect",
        "langs": ["ru"],
        "modes": None,
    },
    {
        "text_key": "ad_dzen_3",
        "url": "https://t.me/vpn_dzen_bot?start=_tgr_sp0QqEc0YmVi",
        "btn_key": "btn_ad_connect",
        "langs": ["ru"],
        "modes": None,
    },
    # --- Buy VPN Global — EN + ES ---
    {
        "text_key": "ad_vpnglobal_1",
        "url": "https://t.me/BuyVPN_Global_bot?start=_tgr_YDRuRzQwYzhi",
        "btn_key": "btn_ad_get_vpn",
        "langs": ["en", "es"],
        "modes": None,
    },
    {
        "text_key": "ad_vpnglobal_2",
        "url": "https://t.me/BuyVPN_Global_bot?start=_tgr_YDRuRzQwYzhi",
        "btn_key": "btn_ad_get_vpn",
        "langs": ["en", "es"],
        "modes": None,
    },
    # --- Playbox — EN + ES, только kink ---
    {
        "text_key": "ad_playbox_1",
        "url": "https://t.me/playbox?start=_tgr_BStO_C8wYjBi",
        "btn_key": "btn_ad_playbox",
        "langs": ["en", "es"],
        "modes": ["kink"],
    },
    {
        "text_key": "ad_playbox_2",
        "url": "https://t.me/playbox?start=_tgr_BStO_C8wYjBi",
        "btn_key": "btn_ad_playbox",
        "langs": ["en", "es"],
        "modes": ["kink"],
    },
    # --- SMS PRO — только RU, все режимы ---
    {
        "text_key": "ad_smspro_1",
        "url": "https://t.me/Virtnumbers_buyBot?start=_tgr_josfGNMwMGYy",
        "btn_key": "btn_ad_smspro",
        "langs": ["ru"],
        "modes": None,
    },
    {
        "text_key": "ad_smspro_2",
        "url": "https://t.me/Virtnumbers_buyBot?start=_tgr_josfGNMwMGYy",
        "btn_key": "btn_ad_smspro",
        "langs": ["ru"],
        "modes": None,
    },
    # --- BoundLess3D — все языки, только kink/flirt ---
    {
        "text_key": "ad_boundless_1",
        "url": "https://t.me/Boundless3D_bot?start=_tgr_3hwFzf1kYjg6",
        "btn_key": "btn_ad_boundless",
        "langs": None,
        "modes": ["kink", "flirt"],
    },
    {
        "text_key": "ad_boundless_2",
        "url": "https://t.me/Boundless3D_bot?start=_tgr_3hwFzf1kYjg6",
        "btn_key": "btn_ad_boundless",
        "langs": None,
        "modes": ["kink", "flirt"],
    },
    # --- Song Stop Spot — EN + ES, все режимы ---
    {
        "text_key": "ad_songstop_1",
        "url": "https://t.me/SongStop45_Bot?start=_tgr_3RjjOGkyZWUy",
        "btn_key": "btn_ad_songstop",
        "langs": ["en", "es"],
        "modes": None,
    },
    {
        "text_key": "ad_songstop_2",
        "url": "https://t.me/SongStop45_Bot?start=_tgr_3RjjOGkyZWUy",
        "btn_key": "btn_ad_songstop",
        "langs": ["en", "es"],
        "modes": None,
    },
    # --- Детектор совместимости — RU + EN, simple/flirt ---
    {
        "text_key": "ad_sovmest_1",
        "url": "https://t.me/Sovmestdetect_bot?start=_tgr_srusCgVlOWEy",
        "btn_key": "btn_ad_sovmest",
        "langs": ["ru", "en"],
        "modes": ["simple", "flirt"],
    },
    {
        "text_key": "ad_sovmest_2",
        "url": "https://t.me/Sovmestdetect_bot?start=_tgr_srusCgVlOWEy",
        "btn_key": "btn_ad_sovmest",
        "langs": ["ru", "en"],
        "modes": ["simple", "flirt"],
    },
    # --- Звёздный бот — только RU, все режимы ---
    {
        "text_key": "ad_stars_1",
        "url": "https://t.me/BGC_Stars_bot?start=_tgr_z8puL2EwZDNi",
        "btn_key": "btn_ad_stars",
        "langs": ["ru"],
        "modes": None,
    },
    {
        "text_key": "ad_stars_2",
        "url": "https://t.me/BGC_Stars_bot?start=_tgr_z8puL2EwZDNi",
        "btn_key": "btn_ad_stars",
        "langs": ["ru"],
        "modes": None,
    },
    # --- Luna AI — RU + EN + ES, только kink ---
    {
        "text_key": "ad_luna_1",
        "url": "https://t.me/LunaCoreSystemBot?start=_tgr_24olCJ5iNTQy",
        "btn_key": "btn_ad_luna",
        "langs": None,
        "modes": ["kink"],
    },
    {
        "text_key": "ad_luna_2",
        "url": "https://t.me/LunaCoreSystemBot?start=_tgr_24olCJ5iNTQy",
        "btn_key": "btn_ad_luna",
        "langs": None,
        "modes": ["kink"],
    },
]


def filter_ads(lang: str, mode: str) -> list:
    """Filters ads by user language and mode."""
    result = []
    for ad in PARTNER_ADS:
        if ad["langs"] is not None and lang not in ad["langs"]:
            continue
        if ad["modes"] is not None and mode not in ad["modes"]:
            continue
        result.append(ad)
    return result
