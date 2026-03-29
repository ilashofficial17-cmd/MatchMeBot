from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from datetime import datetime
from locales import t

CHANNEL_ID = "@MATCHMEHUB"

MODE_NAMES = {"simple": "Просто общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}
INTERESTS_MAP = {
    "simple": ["Разговор по душам 🗣", "Юмор и мемы 😂", "Советы по жизни 💡", "Музыка 🎵", "Игры 🎮"],
    "flirt":  ["Лёгкий флирт 😏", "Комплименты 💌", "Секстинг 🔥", "Виртуальные свидания 💑", "Флирт и игры 🎭"],
    "kink":   ["BDSM 🖤", "Bondage 🔗", "Roleplay 🎭", "Dom/Sub ⛓", "Pet play 🐾", "Другой фетиш ✨"],
}

WELCOME_TEXT = (
    "👋 Привет! Я MatchMe — анонимный чат для общения, флирта и знакомств.\n\n"
    "🇷🇺 Нажми кнопку для продолжения\n"
    "🇬🇧 Click button to continue"
)

PRIVACY_TEXT = """🔒 Политика конфиденциальности MatchMe

Что собираем: Telegram ID, имя, возраст, пол — для подбора собеседников.
Данные НЕ передаются третьим лицам. Переписка НЕ хранится постоянно.

🛡 Конфиденциальность чатов:
Все чаты в боте полностью конфиденциальны и защищены.
Мы не предоставляем доступ к вашим перепискам третьим лицам.
Модерация чатов осуществляется исключительно ИИ-модератором.
Ни администраторы, ни владелец бота не просматривают личные чаты пользователей.

Возраст: минимум 16 лет. 16-17 — Общение и Флирт. 18+ — все режимы.
Удаление данных: /reset или написать администратору.

Принимая условия ты соглашаешься с политикой конфиденциальности."""

RULES_RU = """📜 Правила MatchMe

Разрешено: общение, флирт, ролевые игры (18+), лайки собеседникам.
Возраст: 16-17 — Общение и Флирт. 18+ — все режимы. Ложный возраст = перм бан.

❌ Запрещено:
• Реклама, спам, мошенничество — бан
• Интим-услуги, контент с несовершеннолетними — перм бан
• Пошлые темы без согласия в «Общении» — бан
• Угрозы, оскорбления, ложные жалобы — бан

Нарушения: предупреждение → бан 3ч → бан 24ч → перм бан.

Нажми ✅ Принять правила для продолжения."""

RULES_PROFILE = """📜 Правила общения:

• Уважай собеседника
• 👍 Лайк — если понравилось
• 🚩 Жалоба — только при реальных нарушениях!
• Реклама = бан
• Ложная жалоба = санкции

Нажми ✅ Понятно для продолжения."""


# ====================== КЛАВИАТУРЫ ======================

def kb_main():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡ Поиск"), KeyboardButton(text="🔍 По анкете")],
        [KeyboardButton(text="🤖 ИИ чат"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❓ Помощь")]
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
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t(lang, "btn_accept_rules"))]], resize_keyboard=True)


def kb_rules_profile():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Понятно, начать анкету")]], resize_keyboard=True)


def kb_cancel_reg():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить анкету")]], resize_keyboard=True)


def kb_gender():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨 Парень"), KeyboardButton(text="👩 Девушка")],
        [KeyboardButton(text="⚧ Другое")],
        [KeyboardButton(text="❌ Отменить анкету")]
    ], resize_keyboard=True)


def kb_mode():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💬 Просто общение")],
        [KeyboardButton(text="💋 Флирт")],
        [KeyboardButton(text="🔥 Kink / ролевые (18+)")],
        [KeyboardButton(text="❌ Отменить анкету")]
    ], resize_keyboard=True)


def kb_cancel_search():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отменить поиск")]], resize_keyboard=True)


def kb_chat():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ Следующий"), KeyboardButton(text="❌ Стоп")],
        [KeyboardButton(text="👍 Лайк"), KeyboardButton(text="🚩 Жалоба")],
        [KeyboardButton(text="🎲 Дай тему"), KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)


def kb_search_gender():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨 Парня"), KeyboardButton(text="👩 Девушку")],
        [KeyboardButton(text="⚧ Другое"), KeyboardButton(text="🔀 Не важно")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)


def kb_after_chat(partner_uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ Хочу продолжить общение", callback_data=f"mutual:{partner_uid}")],
        [InlineKeyboardButton(text="🔍 Найти нового", callback_data="goto:find")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="goto:menu")],
    ])


def kb_channel_bonus(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📢 {CHANNEL_ID}", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
        [InlineKeyboardButton(text=t(lang, "btn_check_channel"), callback_data="channel:check")],
        [InlineKeyboardButton(text=t(lang, "btn_skip_channel"), callback_data="channel:skip")],
    ])


def kb_ai_characters(user_tier=None, mode="simple"):
    buttons = []
    if mode in ["simple", "any"]:
        buttons.append([
            InlineKeyboardButton(text="👨 Данил", callback_data="aichar:danil"),
            InlineKeyboardButton(text="👩 Полина", callback_data="aichar:polina")
        ])
    if mode in ["flirt", "any"]:
        buttons.append([
            InlineKeyboardButton(text="😏 Макс", callback_data="aichar:max"),
            InlineKeyboardButton(text="💋 Виолетта", callback_data="aichar:violetta")
        ])
    if mode in ["kink", "any"]:
        buttons.append([
            InlineKeyboardButton(text="🐾 Алиса", callback_data="aichar:alisa"),
            InlineKeyboardButton(text="😈 Дмитри", callback_data="aichar:dmitri")
        ])
        buttons.append([InlineKeyboardButton(text="🎭 Ролевой мастер", callback_data="aichar:rolemaster")])
    buttons.append([InlineKeyboardButton(text="🧠 Мощная нейронка (скоро)", callback_data="aichar:power_soon")])
    if mode != "any":
        buttons.append([InlineKeyboardButton(text="🔀 Все персонажи", callback_data="aichar:all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="aichar:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_ai_chat():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Сменить персонажа"), KeyboardButton(text="❌ Завершить чат")],
        [KeyboardButton(text="🔍 Найти живого собеседника")],
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)


def kb_interests(mode, selected):
    interests = INTERESTS_MAP.get(mode, [])
    buttons = []
    for interest in interests:
        mark = "✅ " if interest in selected else ""
        buttons.append([InlineKeyboardButton(text=f"{mark}{interest}", callback_data=f"int:{interest}")])
    buttons.append([InlineKeyboardButton(text="✅ Готово — сохранить", callback_data="int:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_complaint():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔞 Несовершеннолетние", callback_data="rep:minor")],
        [InlineKeyboardButton(text="💰 Спам / Реклама", callback_data="rep:spam")],
        [InlineKeyboardButton(text="😡 Угрозы / Оскорбления", callback_data="rep:abuse")],
        [InlineKeyboardButton(text="🔞 Пошлятина без согласия", callback_data="rep:nsfw")],
        [InlineKeyboardButton(text="🔄 Другое", callback_data="rep:other")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="rep:cancel")],
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
            callback_data=f"uadm:shadowtoggle:{target_uid}"
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
