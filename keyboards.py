from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from locales import t

CHANNEL_ID = "@MATCHMEHUB"

# Интересы хранятся в БД как есть — не переводим
INTERESTS_MAP = {
    "simple": ["Разговор по душам 🗣", "Юмор и мемы 😂", "Советы по жизни 💡", "Музыка 🎵", "Игры 🎮"],
    "flirt":  ["Лёгкий флирт 😏", "Комплименты 💌", "Секстинг 🔥", "Виртуальные свидания 💑", "Флирт и игры 🎭"],
    "kink":   ["BDSM 🖤", "Bondage 🔗", "Roleplay 🎭", "Dom/Sub ⛓", "Pet play 🐾", "Другой фетиш ✨"],
}

# ====================== КЛАВИАТУРЫ ======================

def kb_main(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_search")), KeyboardButton(text=t(lang, "btn_find"))],
        [KeyboardButton(text=t(lang, "btn_ai_chat")), KeyboardButton(text=t(lang, "btn_profile"))],
        [KeyboardButton(text=t(lang, "btn_settings")), KeyboardButton(text=t(lang, "btn_help"))],
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
        [KeyboardButton(text=t(lang, "btn_next")), KeyboardButton(text=t(lang, "btn_stop"))],
        [KeyboardButton(text=t(lang, "btn_like")), KeyboardButton(text=t(lang, "btn_complaint"))],
        [KeyboardButton(text=t(lang, "btn_topic")), KeyboardButton(text=t(lang, "btn_home"))],
    ], resize_keyboard=True)


def kb_search_gender(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_find_male")), KeyboardButton(text=t(lang, "btn_find_female"))],
        [KeyboardButton(text=t(lang, "btn_find_other")), KeyboardButton(text=t(lang, "btn_find_any"))],
        [KeyboardButton(text=t(lang, "btn_back"))],
    ], resize_keyboard=True)


def kb_after_chat(partner_uid, lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ " + t(lang, "mutual_request_sent").split("\n")[0], callback_data=f"mutual:{partner_uid}")],
        [InlineKeyboardButton(text=t(lang, "btn_find"), callback_data="goto:find")],
        [InlineKeyboardButton(text=t(lang, "btn_home"), callback_data="goto:menu")],
    ])


def kb_channel_bonus(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📢 {CHANNEL_ID}", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
        [InlineKeyboardButton(text=t(lang, "btn_check_channel"), callback_data="channel:check")],
        [InlineKeyboardButton(text=t(lang, "btn_skip_channel"), callback_data="channel:skip")],
    ])


def kb_ai_characters(user_tier=None, mode="simple", lang="ru"):
    buttons = []
    if mode in ["simple", "any"]:
        buttons.append([
            InlineKeyboardButton(text="👨 Данил", callback_data="aichar:danil"),
            InlineKeyboardButton(text="👩 Полина", callback_data="aichar:polina"),
        ])
    if mode in ["flirt", "any"]:
        buttons.append([
            InlineKeyboardButton(text="😏 Макс", callback_data="aichar:max"),
            InlineKeyboardButton(text="💋 Виолетта", callback_data="aichar:violetta"),
        ])
    if mode in ["kink", "any"]:
        buttons.append([
            InlineKeyboardButton(text="🐾 Алиса", callback_data="aichar:alisa"),
            InlineKeyboardButton(text="😈 Дмитри", callback_data="aichar:dmitri"),
        ])
        buttons.append([InlineKeyboardButton(text="🎭 Ролевой мастер", callback_data="aichar:rolemaster")])
    buttons.append([InlineKeyboardButton(text="🧠 " + t(lang, "ai_power_soon").replace("🔧 ", ""), callback_data="aichar:power_soon")])
    if mode != "any":
        buttons.append([InlineKeyboardButton(text="🔀 " + t(lang, "btn_find_any").replace("🔀 ", ""), callback_data="aichar:all")])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="aichar:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_ai_chat(lang="ru"):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "btn_change_char")), KeyboardButton(text=t(lang, "btn_end_ai_chat"))],
        [KeyboardButton(text=t(lang, "btn_find_live"))],
        [KeyboardButton(text=t(lang, "btn_home"))],
    ], resize_keyboard=True)


def kb_interests(mode, selected, lang="ru"):
    interests = INTERESTS_MAP.get(mode, [])
    buttons = []
    for interest in interests:
        mark = "✅ " if interest in selected else ""
        buttons.append([InlineKeyboardButton(text=f"{mark}{interest}", callback_data=f"int:{interest}")])
    buttons.append([InlineKeyboardButton(text="✅ " + t(lang, "edit_done"), callback_data="int:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_complaint(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔞 Несовершеннолетние", callback_data="rep:minor")],
        [InlineKeyboardButton(text="💰 Спам / Реклама", callback_data="rep:spam")],
        [InlineKeyboardButton(text="😡 Угрозы / Оскорбления", callback_data="rep:abuse")],
        [InlineKeyboardButton(text="🔞 Пошлятина без согласия", callback_data="rep:nsfw")],
        [InlineKeyboardButton(text="🔄 Другое", callback_data="rep:other")],
        [InlineKeyboardButton(text=t(lang, "btn_back") + " Отмена", callback_data="rep:cancel")],
    ])


def kb_edit():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Имя", callback_data="edit:name"),
         InlineKeyboardButton(text="🎂 Возраст", callback_data="edit:age")],
        [InlineKeyboardButton(text="⚧ Пол", callback_data="edit:gender"),
         InlineKeyboardButton(text="💬 Режим", callback_data="edit:mode")],
        [InlineKeyboardButton(text="🎯 Интересы", callback_data="edit:interests")],
    ])


def kb_complaint_action(complaint_id, accused_uid, reporter_uid, has_log=False, stop_words=False):
    sw_text = "⚠️ Стоп-слова: ДА" if stop_words else "✅ Стоп-слова: НЕТ"
    buttons = [[InlineKeyboardButton(text=sw_text, callback_data="noop")]]
    if has_log:
        buttons.append([InlineKeyboardButton(text="📄 Показать переписку", callback_data=f"clog:show:{complaint_id}")])
    buttons += [
        [InlineKeyboardButton(text="🚫 Бан 3ч нарушителю", callback_data=f"cadm:ban3:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="🚫 Бан 24ч нарушителю", callback_data=f"cadm:ban24:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан нарушителю", callback_data=f"cadm:banperm:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение нарушителю", callback_data=f"cadm:warn:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="⚠️ Предупреждение жалобщику", callback_data=f"cadm:warnrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="🚫 Бан жалобщику", callback_data=f"cadm:banrep:{complaint_id}:{reporter_uid}")],
        [InlineKeyboardButton(text="👻 Shadow ban нарушителю", callback_data=f"cadm:shadow:{complaint_id}:{accused_uid}")],
        [InlineKeyboardButton(text="✅ Отклонить жалобу", callback_data=f"cadm:dismiss:{complaint_id}:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_user_actions(target_uid, is_shadow=False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Бан 3ч", callback_data=f"uadm:ban3:{target_uid}"),
         InlineKeyboardButton(text="🚫 Бан 24ч", callback_data=f"uadm:ban24:{target_uid}")],
        [InlineKeyboardButton(text="🚫 Перм бан", callback_data=f"uadm:banperm:{target_uid}"),
         InlineKeyboardButton(text="✅ Разбан", callback_data=f"uadm:unban:{target_uid}")],
        [InlineKeyboardButton(
            text="👻 Снять shadow ban" if is_shadow else "👻 Shadow ban",
            callback_data=f"uadm:shadowtoggle:{target_uid}",
        )],
        [InlineKeyboardButton(text="⚠️ Предупреждение", callback_data=f"uadm:warn:{target_uid}"),
         InlineKeyboardButton(text="❌ Кик", callback_data=f"uadm:kick:{target_uid}")],
        [InlineKeyboardButton(text="⭐ Дать Premium 30д", callback_data=f"uadm:premium:{target_uid}"),
         InlineKeyboardButton(text="⭐ Забрать Premium", callback_data=f"uadm:unpremium:{target_uid}")],
        [InlineKeyboardButton(text="🗑 Полное удаление", callback_data=f"uadm:fulldelete:{target_uid}")],
    ])


def kb_premium():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="── Premium ──", callback_data="noop")],
        [InlineKeyboardButton(text="⭐ 7 дней — 99 Stars", callback_data="buy:7d")],
        [InlineKeyboardButton(text="⭐ 1 месяц — 299 Stars", callback_data="buy:1m")],
        [InlineKeyboardButton(text="⭐ 3 месяца — 599 Stars", callback_data="buy:3m")],
        [InlineKeyboardButton(text="── Premium Plus (лучшее!) ──", callback_data="noop")],
        [InlineKeyboardButton(text="🚀 1 месяц — 499 Stars", callback_data="buy:plus_1m")],
        [InlineKeyboardButton(text="🚀 3 месяца — 999 Stars", callback_data="buy:plus_3m")],
        [InlineKeyboardButton(text="── AI Pro ──", callback_data="noop")],
        [InlineKeyboardButton(text="🧠 1 месяц — 399 Stars", callback_data="buy:ai_1m")],
        [InlineKeyboardButton(text="🧠 3 месяца — 799 Stars", callback_data="buy:ai_3m")],
        [InlineKeyboardButton(text="❓ Сравнить подписки", callback_data="buy:info")],
    ])
