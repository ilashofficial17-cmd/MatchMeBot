"""
Admin Bot — Reply-клавиатуры для навигации.
Каждый раздел — своя клавиатура. Inline только для действий внутри результата.
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from locales import t


def kb_main_menu():
    """Главное меню админа — 4 раздела."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛡 Админка"), KeyboardButton(text="📢 Канал")],
        [KeyboardButton(text="📊 Аналитика"), KeyboardButton(text="🎯 Маркетинг")],
    ], resize_keyboard=True)


def kb_admin():
    """Раздел Админка."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти юзера"), KeyboardButton(text="🚩 Жалобы")],
        [KeyboardButton(text="📋 Аудит"), KeyboardButton(text="📩 Саппорт")],
        [KeyboardButton(text="🖼 Медиа"), KeyboardButton(text="🔧 Уведомление")],
        [KeyboardButton(text="🚫 Стоп-слова")],
        [KeyboardButton(text="⬅️ Назад")],
    ], resize_keyboard=True)


def kb_channel():
    """Раздел Канал."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Создать пост"), KeyboardButton(text="⚡ Авто-постинг")],
        [KeyboardButton(text="📅 Расписание"), KeyboardButton(text="🔌 Статус API")],
        [KeyboardButton(text="🔔 Режимы рубрик"), KeyboardButton(text="📋 Очередь")],
        [KeyboardButton(text="⬅️ Назад")],
    ], resize_keyboard=True)


def kb_analytics():
    """Раздел Аналитика."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 Общая"), KeyboardButton(text="📈 Retention")],
        [KeyboardButton(text="👁 Онлайн"), KeyboardButton(text="🤖 AI чаты")],
        [KeyboardButton(text="⭐ Оценки"), KeyboardButton(text="📢 Канал стат")],
        [KeyboardButton(text="🔄 Воронка")],
        [KeyboardButton(text="⬅️ Назад")],
    ], resize_keyboard=True)


def kb_marketing():
    """Раздел Маркетинг."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💰 Доходы"), KeyboardButton(text="🎨 Креативы")],
        [KeyboardButton(text="📊 Реклама"), KeyboardButton(text="🧪 A/B тесты")],
        [KeyboardButton(text="📅 Когорты"), KeyboardButton(text="📨 Рассылка")],
        [KeyboardButton(text="⬅️ Назад")],
    ], resize_keyboard=True)


def kb_support_user(lang="ru"):
    """Саппорт-меню для обычных юзеров."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang, "support_bug_btn"))],
        [KeyboardButton(text=t(lang, "support_appeal_btn"))],
        [KeyboardButton(text=t(lang, "support_my_tickets_btn"))],
    ], resize_keyboard=True)
