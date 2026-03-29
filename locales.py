"""
MatchMe Bot — локализация.
Пока только начальный флоу: выбор языка, политика, правила, бан-сообщения.
"""

TEXTS = {
    "ru": {
        "welcome": (
            "👋 Привет! Я MatchMe — анонимный чат для общения, флирта и знакомств.\n\n"
            "Выбери язык / Choose language / Elige idioma 👇"
        ),
        "privacy": (
            "🔒 Политика конфиденциальности MatchMe\n\n"
            "Что собираем: Telegram ID, имя, возраст, пол — для подбора собеседников.\n"
            "Данные НЕ передаются третьим лицам. Переписка НЕ хранится постоянно.\n\n"
            "🛡 Конфиденциальность чатов:\n"
            "Все чаты в боте полностью конфиденциальны и защищены.\n"
            "Мы не предоставляем доступ к вашим перепискам третьим лицам.\n"
            "Модерация чатов осуществляется исключительно ИИ-модератором.\n"
            "Ни администраторы, ни владелец бота не просматривают личные чаты пользователей.\n\n"
            "Возраст: минимум 16 лет. 16-17 — Общение и Флирт. 18+ — все режимы.\n"
            "Удаление данных: /reset или написать администратору.\n\n"
            "Принимая условия ты соглашаешься с политикой конфиденциальности."
        ),
        "privacy_accepted": "✅ Политика конфиденциальности принята!",
        "privacy_declined": (
            "❌ Без принятия политики конфиденциальности использование бота невозможно.\n\n"
            "Нажми /start чтобы попробовать снова."
        ),
        "channel_bonus": (
            "🎁 Подпишись на наш канал и получи 3 дня Premium бесплатно!\n\n"
            "В канале: обновления, новости бота и полезный контент 😄"
        ),
        "channel_not_subscribed": "Ты ещё не подписан на канал!",
        "channel_bonus_used": "Бонус уже был получен ранее!",
        "channel_already_premium": "У тебя уже есть Premium!",
        "channel_bonus_activated": "🎉 Спасибо за подписку!\n\n⭐ Premium активирован на 3 дня!\nДо {until}",
        "channel_skip": "Окей! Можешь подписаться позже через /premium 😊",
        "rules": (
            "📜 Правила MatchMe\n\n"
            "Разрешено: общение, флирт, ролевые игры (18+), лайки собеседникам.\n"
            "Возраст: 16-17 — Общение и Флирт. 18+ — все режимы. Ложный возраст = перм бан.\n\n"
            "❌ Запрещено:\n"
            "• Реклама, спам, мошенничество — бан\n"
            "• Интим-услуги, контент с несовершеннолетними — перм бан\n"
            "• Пошлые темы без согласия в «Общении» — бан\n"
            "• Угрозы, оскорбления, ложные жалобы — бан\n\n"
            "Нарушения: предупреждение → бан 3ч → бан 24ч → перм бан.\n\n"
            "Нажми ✅ Принять правила для продолжения."
        ),
        "rules_accepted": "✅ Правила приняты! Добро пожаловать в MatchMe! 🎉",
        "rules_choose_lang": "👆 Выбери язык чтобы продолжить.",
        "welcome_back": "👋 С возвращением в MatchMe!{badge}",
        "welcome_new": "👋 Добро пожаловать в MatchMe!{badge}",
        "banned_permanent": "🚫 Ты заблокирован навсегда.",
        "banned_until": "🚫 Ты заблокирован до {until}",
        # Кнопки
        "btn_accept_privacy": "✅ Принять и продолжить",
        "btn_decline_privacy": "❌ Отказаться",
        "btn_accept_rules": "✅ Принять правила",
        "btn_check_channel": "✅ Проверить подписку",
        "btn_skip_channel": "⏭ Пропустить",
    },

    "en": {
        "welcome": (
            "👋 Hi! I'm MatchMe — anonymous chat for socializing, flirting and meeting new people.\n\n"
            "Choose your language / Выбери язык / Elige idioma 👇"
        ),
        "privacy": (
            "🔒 MatchMe Privacy Policy\n\n"
            "What we collect: Telegram ID, name, age, gender — for matching.\n"
            "Data is NOT shared with third parties. Messages are NOT stored permanently.\n\n"
            "🛡 Chat confidentiality:\n"
            "All chats are fully confidential and protected.\n"
            "We do not grant access to your conversations to third parties.\n"
            "Chat moderation is performed exclusively by an AI moderator.\n"
            "Neither admins nor the bot owner read private chats.\n\n"
            "Age: minimum 16. Ages 16-17 — Chat and Flirt only. 18+ — all modes.\n"
            "Data deletion: /reset or contact the admin.\n\n"
            "By accepting, you agree to the privacy policy."
        ),
        "privacy_accepted": "✅ Privacy policy accepted!",
        "privacy_declined": (
            "❌ You cannot use the bot without accepting the privacy policy.\n\n"
            "Press /start to try again."
        ),
        "channel_bonus": (
            "🎁 Subscribe to our channel and get 3 days of Premium for free!\n\n"
            "Updates, news and useful content inside 😄"
        ),
        "channel_not_subscribed": "You haven't subscribed to the channel yet!",
        "channel_bonus_used": "You've already received the bonus!",
        "channel_already_premium": "You already have Premium!",
        "channel_bonus_activated": "🎉 Thanks for subscribing!\n\n⭐ Premium activated for 3 days!\nUntil {until}",
        "channel_skip": "Okay! You can subscribe later via /premium 😊",
        "rules": (
            "📜 MatchMe Rules\n\n"
            "Allowed: chatting, flirting, role-play (18+), liking people.\n"
            "Age: 16-17 — Chat & Flirt. 18+ — all modes. Fake age = permanent ban.\n\n"
            "❌ Prohibited:\n"
            "• Advertising, spam, fraud — ban\n"
            "• Adult services, content with minors — permanent ban\n"
            "• Sexual topics without consent in Chat mode — ban\n"
            "• Threats, insults, false reports — ban\n\n"
            "Violations: warning → 3h ban → 24h ban → permanent ban.\n\n"
            "Press ✅ Accept rules to continue."
        ),
        "rules_accepted": "✅ Rules accepted! Welcome to MatchMe! 🎉",
        "rules_choose_lang": "👆 Choose a language to continue.",
        "welcome_back": "👋 Welcome back to MatchMe!{badge}",
        "welcome_new": "👋 Welcome to MatchMe!{badge}",
        "banned_permanent": "🚫 You are permanently banned.",
        "banned_until": "🚫 You are banned until {until}",
        # Buttons
        "btn_accept_privacy": "✅ Accept and continue",
        "btn_decline_privacy": "❌ Decline",
        "btn_accept_rules": "✅ Accept rules",
        "btn_check_channel": "✅ Check subscription",
        "btn_skip_channel": "⏭ Skip",
    },

    "es": {
        "welcome": (
            "👋 ¡Hola! Soy MatchMe — chat anónimo para socializar, coquetear y conocer gente.\n\n"
            "Elige tu idioma / Choose language / Выбери язык 👇"
        ),
        "privacy": (
            "🔒 Política de privacidad de MatchMe\n\n"
            "Qué recopilamos: ID de Telegram, nombre, edad, género — para emparejar.\n"
            "Los datos NO se comparten con terceros. Los mensajes NO se almacenan permanentemente.\n\n"
            "🛡 Confidencialidad del chat:\n"
            "Todos los chats son completamente confidenciales y están protegidos.\n"
            "No otorgamos acceso a tus conversaciones a terceros.\n"
            "La moderación del chat la realiza exclusivamente un moderador de IA.\n"
            "Ni los administradores ni el propietario del bot leen los chats privados.\n\n"
            "Edad: mínimo 16 años. 16-17 — Chat y Coqueteo. 18+ — todos los modos.\n"
            "Eliminación de datos: /reset o contacta al administrador.\n\n"
            "Al aceptar, aceptas la política de privacidad."
        ),
        "privacy_accepted": "✅ ¡Política de privacidad aceptada!",
        "privacy_declined": (
            "❌ No puedes usar el bot sin aceptar la política de privacidad.\n\n"
            "Presiona /start para intentar de nuevo."
        ),
        "channel_bonus": (
            "🎁 ¡Suscríbete a nuestro canal y obtén 3 días de Premium gratis!\n\n"
            "Actualizaciones, noticias y contenido útil 😄"
        ),
        "channel_not_subscribed": "¡Aún no te has suscrito al canal!",
        "channel_bonus_used": "¡Ya recibiste el bono!",
        "channel_already_premium": "¡Ya tienes Premium!",
        "channel_bonus_activated": "🎉 ¡Gracias por suscribirte!\n\n⭐ ¡Premium activado por 3 días!\nHasta {until}",
        "channel_skip": "¡Está bien! Puedes suscribirte después vía /premium 😊",
        "rules": (
            "📜 Reglas de MatchMe\n\n"
            "Permitido: chatear, coquetear, juegos de rol (18+), dar likes.\n"
            "Edad: 16-17 — Chat y Coqueteo. 18+ — todos los modos. Edad falsa = ban permanente.\n\n"
            "❌ Prohibido:\n"
            "• Publicidad, spam, fraude — ban\n"
            "• Servicios para adultos, contenido con menores — ban permanente\n"
            "• Temas sexuales sin consentimiento en modo Chat — ban\n"
            "• Amenazas, insultos, denuncias falsas — ban\n\n"
            "Violaciones: advertencia → ban 3h → ban 24h → ban permanente.\n\n"
            "Presiona ✅ Aceptar reglas para continuar."
        ),
        "rules_accepted": "✅ ¡Reglas aceptadas! ¡Bienvenido a MatchMe! 🎉",
        "rules_choose_lang": "👆 Elige un idioma para continuar.",
        "welcome_back": "👋 ¡Bienvenido de vuelta a MatchMe!{badge}",
        "welcome_new": "👋 ¡Bienvenido a MatchMe!{badge}",
        "banned_permanent": "🚫 Estás baneado permanentemente.",
        "banned_until": "🚫 Estás baneado hasta {until}",
        # Botones
        "btn_accept_privacy": "✅ Aceptar y continuar",
        "btn_decline_privacy": "❌ Rechazar",
        "btn_accept_rules": "✅ Aceptar reglas",
        "btn_check_channel": "✅ Verificar suscripción",
        "btn_skip_channel": "⏭ Omitir",
    },
}

# Языки и их кнопки/коды
LANG_BUTTONS = {
    "🇷🇺 Русский": "ru",
    "🇬🇧 English": "en",
    "🇪🇸 Español": "es",
}
LANG_CODES = list(LANG_BUTTONS.values())
LANG_BUTTON_TEXTS = list(LANG_BUTTONS.keys())


def t(lang: str, key: str, **kwargs) -> str:
    """Получить перевод. Fallback на русский."""
    text = TEXTS.get(lang, TEXTS["ru"]).get(key, TEXTS["ru"].get(key, key))
    if kwargs:
        text = text.format(**kwargs)
    return text
