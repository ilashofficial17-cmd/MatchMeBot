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
        # Кнопки — privacy/rules/channel
        "btn_accept_privacy": "✅ Принять и продолжить",
        "btn_decline_privacy": "❌ Отказаться",
        "btn_accept_rules": "✅ Принять правила",
        "btn_check_channel": "✅ Проверить подписку",
        "btn_skip_channel": "⏭ Пропустить",
        # Кнопки — главное меню
        "btn_search": "⚡ Поиск",
        "btn_find": "🔍 По анкете",
        "btn_ai_chat": "🤖 ИИ чат",
        "btn_profile": "👤 Профиль",
        "btn_settings": "⚙️ Настройки",
        "btn_help": "❓ Помощь",
        # Кнопки — чат
        "btn_next": "⏭ Следующий",
        "btn_stop": "❌ Стоп",
        "btn_like": "👍 Лайк",
        "btn_complaint": "🚩 Жалоба",
        "btn_topic": "🎲 Дай тему",
        "btn_home": "🏠 Главное меню",
        # Кнопки — анкета/поиск
        "btn_cancel_reg": "❌ Отменить анкету",
        "btn_start_form": "✅ Понятно, начать анкету",
        "btn_cancel_search": "❌ Отменить поиск",
        # Кнопки — пол
        "btn_male": "👨 Парень",
        "btn_female": "👩 Девушка",
        "btn_other": "⚧ Другое",
        "btn_find_male": "👨 Парня",
        "btn_find_female": "👩 Девушку",
        "btn_find_other": "⚧ Другое",
        "btn_find_any": "🔀 Не важно",
        "btn_back": "◀️ Назад",
        # Кнопки — режим
        "btn_mode_simple": "💬 Просто общение",
        "btn_mode_flirt": "💋 Флирт",
        "btn_mode_kink": "🔥 Kink / ролевые (18+)",
        # Кнопки — AI чат
        "btn_change_char": "🔄 Сменить персонажа",
        "btn_end_ai_chat": "❌ Завершить чат",
        "btn_find_live": "🔍 Найти живого собеседника",
        # Названия режимов и пола (для отображения)
        "mode_simple": "Просто общение 💬",
        "mode_flirt": "Флирт 💋",
        "mode_kink": "Kink 🔥",
        "gender_male": "Парень 👨",
        "gender_female": "Девушка 👩",
        "gender_other": "Другое ⚧",
        # Тексты — поиск
        "searching_anon": "⚡ Ищем анонимного собеседника...",
        "connected": "👤 Соединено! Удачи! 🎉",
        "queue_info": "👥 В режиме {mode}: {count} чел.\n{status}",
        "queue_searching": "🔍 Ищем...",
        "queue_priority": "🚀 Приоритетный поиск ⭐",
        "search_cancelled": "❌ Поиск отменён.",
        "not_searching": "Ты не в поиске.",
        # Тексты — чат
        "chat_ended": "💔 Чат завершён.",
        "partner_left": "😔 Собеседник покинул чат.",
        "not_in_chat": "Ты не в чате.",
        "spam_warning": "⚠️ Не спамь!",
        "like_sent": "👍 Лайк отправлен!",
        "like_received": "👍 Собеседник поставил тебе лайк! ⭐",
        "like_already": "👍 Ты уже ставил лайк этому собеседнику!",
        "topic_sent": "🎲 Тема для разговора:\n\n{topic}",
        "topic_received": "🎲 Собеседник предлагает тему:\n\n{topic}",
        "mutual_match": "🎉 Взаимный интерес! Приватный анонимный чат открыт.\nВы по-прежнему анонимны друг для друга.",
        "mutual_request_sent": "❤️ Запрос отправлен!\nЕсли собеседник тоже захочет — вас соединят в течение 10 минут.",
        "mutual_request_received": "💌 Твой собеседник хочет продолжить общение!\nОтветь на предложение если тоже хочешь:",
        "mutual_no_response": "😔 Собеседник не ответил на запрос продолжения.",
        "mutual_decline_ok": "Окей, не проблема!",
        "mutual_already_in_chat": "😔 Кто-то из вас уже в чате.",
        "partner_busy": "😔 Собеседник уже общается с кем-то другим.",
        "after_chat_propose": "Понравился собеседник?\nПредложи продолжить общение анонимно — если он тоже захочет, вас соединят 😊",
        "inactivity_end": "⏰ Чат завершён — 7 мин неактивности.",
        "inactivity_ai_end": "⏰ AI чат завершён — 10 мин неактивности.",
        # Тексты — жалоба
        "complaint_prompt": "🚩 Укажи причину жалобы:",
        "complaint_cancelled": "↩️ Жалоба отменена.",
        "complaint_sent": "🚩 Жалоба #{id} отправлена. AI анализирует...",
        "complaint_not_in_chat": "Ты не в чате.",
        "partner_complained": "⚠️ На тебя подана жалоба.",
        # Тексты — регистрация
        "reg_rules_profile": (
            "📜 Правила общения:\n\n"
            "• Уважай собеседника\n"
            "• 👍 Лайк — если понравилось\n"
            "• 🚩 Жалоба — только при реальных нарушениях!\n"
            "• Реклама = бан\n"
            "• Ложная жалоба = санкции\n\n"
            "Нажми ✅ Понятно, начать анкету для продолжения."
        ),
        "reg_name_prompt": "📝 Как тебя зовут?",
        "reg_age_prompt": "🎂 Сколько тебе лет?",
        "reg_gender_prompt": "⚧ Выбери свой пол:",
        "reg_mode_prompt": "💬 Выбери режим общения:",
        "reg_interests_prompt": "🎯 Выбери 1–3 интереса:",
        "reg_cancelled": "❌ Анкета отменена.",
        "reg_age_invalid": "❗ Введи число.",
        "reg_age_too_young": "{joke}\n\nВведи правильный возраст (минимум 16):",
        "reg_age_too_old": "{joke}\n\nВведи реальный возраст (16–99).",
        "reg_gender_invalid": "Выбери пол из кнопок 👇",
        "reg_mode_invalid": "Выбери режим из кнопок 👇",
        "reg_kink_age": "🔞 Kink / ролевые игры доступны только с 18 лет.\nВыбери другой режим:",
        "reg_interests_min": "Выбери хотя бы один!",
        "reg_interests_max": "Максимум 3!",
        "reg_interests_invalid": "👆 Нажми на кнопки выше, чтобы выбрать интересы.",
        "reg_done": "✅ Анкета заполнена!",
        "reg_interest_added": "Добавлено: {val}",
        "reg_interest_removed": "Убрано: {val}",
        # Тексты — профиль
        "profile_not_filled": "Анкета не заполнена. Нажми '🔍 По анкете'",
        "profile_text": (
            "👤 Профиль{badge}:\n"
            "Имя: {name}\n"
            "Возраст: {age}\n"
            "Пол: {gender}\n"
            "Режим: {mode}\n"
            "Интересы: {interests}\n"
            "⭐ Рейтинг: {rating}\n"
            "👍 Лайков: {likes}\n"
            "💬 Чатов: {chats}\n"
            "⚠️ Предупреждений: {warns}\n"
            "💎 Статус: {premium}"
        ),
        "profile_upgrade": "\n\n⭐ Upgrade до Premium — приоритет, больше AI, без рекламы!",
        "premium_eternal": "{tier} (вечный)",
        "premium_until_date": "{tier} до {until}",
        "premium_none": "Нет",
        # Тексты — редактирование профиля
        "edit_name_prompt": "✏️ Новое имя:",
        "edit_age_prompt": "🎂 Новый возраст:",
        "edit_gender_prompt": "⚧ Выбери пол:",
        "edit_mode_prompt": "💬 Выбери режим:",
        "edit_interests_prompt": "🎯 Выбери интересы:",
        "edit_back": "↩️ Возврат.",
        "edit_name_done": "✅ Имя обновлено!",
        "edit_age_done": "{joke}\n\n✅ Возраст обновлён!",
        "edit_age_invalid": "❗ Введи число от 16 до 99",
        "edit_gender_done": "✅ Пол обновлён!",
        "edit_interests_done": "✅ Интересы обновлены!",
        "edit_done": "Готово!",
        # Тексты — настройки
        "settings_title": "⚙️ Настройки поиска:",
        "settings_gender_prompt": "👤 Кого хочешь искать?",
        "settings_gender_locked": "🔒 Фильтр пола в Флирте и Kink — только Premium!",
        "settings_premium_only": "🔒 Только для Premium! Купи через /premium",
        "settings_cross_unavailable": "В режиме «Общение» кросс-режим недоступен",
        "settings_changed": "✅ Изменено",
        "settings_age_any": "✅ Возраст: Любой",
        "settings_age_range": "✅ Возраст: {min}–{max}",
        "settings_gender_saved": "✅ Фильтр по полу сохранён!",
        # Тексты — статистика
        "stats_text": (
            "📊 Твоя статистика:\n\n"
            "💬 Всего чатов: {total_chats}\n"
            "👍 Получено лайков: {likes}\n"
            "⭐ Рейтинг: {rating}\n"
            "⚠️ Предупреждений: {warns}\n"
            "📅 Дней в боте: {days}\n"
            "{premium}"
        ),
        "stats_premium_eternal": "⭐ Premium: Вечный",
        "stats_premium_until": "⭐ Premium до {until}",
        "stats_premium_active": "⭐ Premium активен",
        "stats_no_premium": "💎 Premium: Нет",
        "not_registered": "Сначала зарегистрируйся через /start!",
        # Тексты — premium
        "premium_title": "⭐ MatchMe Подписки\n\n{status}📊 Что входит:\n⭐ Premium: безлимит basic ИИ, 50 сообщений premium ИИ, приоритет, без рекламы\n🚀 Premium Plus: безлимит на ВСЕ ИИ, приоритет, без рекламы\n🧠 AI Pro: безлимит на все ИИ модели\n\nВыбери тариф:",
        "premium_status_eternal": "✅ Сейчас: {tier} (вечный)\n\n",
        "premium_status_until": "✅ Сейчас: {tier} до {until}\n\n",
        "premium_info": (
            "📊 Сравнение подписок:\n\n"
            "⭐ Premium (от 99 Stars):\n"
            "• Безлимит на basic ИИ (Данил, Полина, Макс)\n"
            "• 50 сообщений/день на premium ИИ + бонус 10\n"
            "• Приоритет в поиске, без рекламы\n\n"
            "🚀 Premium Plus (от 499 Stars):\n"
            "• Всё из Premium\n"
            "• Безлимит на ВСЕ ИИ модели\n"
            "• Лучшая цена!\n\n"
            "🧠 AI Pro (от 399 Stars):\n"
            "• Безлимит на все ИИ модели\n"
            "• Разблокирует всё как Plus\n\n"
            "💡 Совет: Premium Plus — самый выгодный вариант!"
        ),
        "premium_activated": "🎉 {tier} активирован!\n\n📦 Тариф: {label}\n📅 До {until}\n\n{benefits}",
        "premium_unknown_plan": "Неизвестный тариф",
        "benefit_premium": "Безлимит basic ИИ, 50 сообщений/день premium ИИ, приоритет, без рекламы!",
        "benefit_plus": "Безлимит на ВСЕ ИИ модели, приоритет, без рекламы!",
        "benefit_ai_pro": "Безлимит на ВСЕ ИИ модели!",
        # Тексты — сброс профиля
        "reset_confirm": (
            "⚠️ Полный сброс профиля!\n\n"
            "Удалятся: имя, возраст, пол, режим, интересы, рейтинг\n"
            "❗ Бан, предупреждения и Premium сохранятся.\n\nТы уверен?"
        ),
        "reset_done": "✅ Профиль сброшен!",
        "reset_refill": "👋 Нажми '🔍 По анкете' чтобы заполнить анкету заново.",
        "reset_cancelled": "❌ Сброс отменён.",
        "reset_back": "Возврат в меню.",
        # Тексты — помощь
        "help_text": (
            "🆘 Помощь MatchMe:\n\n"
            "⚡ Поиск — быстрый анонимный поиск\n"
            "🔍 По анкете — по режиму и интересам\n"
            "🤖 ИИ чат — поговори с ИИ\n"
            "📊 /stats — твоя статистика\n"
            "⭐ /premium — Premium подписка\n\n"
            "В чате:\n"
            "⏭ Следующий — другой собеседник\n"
            "❌ Стоп — завершить чат\n"
            "🎲 Дай тему — случайная тема\n"
            "👍 Лайк — поднять рейтинг\n"
            "🚩 Жалоба — при нарушениях\n\n"
            "/reset — сбросить профиль\n"
            "Если что-то сломалось — /start"
        ),
        "unavailable": "⚠️ Сейчас недоступно — {reason}.",
        "no_partner_wait": (
            "⏳ Поиск идёт дольше обычного...\n\n"
            "💡 Пока ждёшь — пообщайся с {name}!\n"
            "AI собеседник ответит моментально 🤖"
        ),
        "upsell": "⭐ Тебе нравится MatchMe?\nPremium = приоритет в поиске + больше AI + без рекламы!",
        "ad_message": "📢 Здесь могла быть ваша реклама\n\n⭐ Купи Premium и убери рекламу навсегда!",
        "hardban": "🚫 Перманентный бан за нарушение правил.",
        # AI чат
        "ai_menu": (
            "🤖 ИИ чат\n\n"
            "Все персонажи доступны бесплатно!\n"
            "💬 Basic: 20 сообщений/день\n"
            "🔥 Premium: 10 сообщений/день\n"
            "⭐ Подписка снимает лимиты\n\n"
            "Выбери с кем хочешь поговорить:"
        ),
        "ai_select_char": "Выбери персонажа:",
        "ai_char_not_found": "Персонаж не найден.",
        "ai_power_soon": "🔧 В разработке! Следи за обновлениями.",
        "ai_chat_active": "💬 Чат с ИИ активен",
        "ai_unlimited": "♾ Безлимит",
        "ai_limit_info": "💬 Лимит: {limit} сообщений/день",
        "ai_ended": "✅ Чат с ИИ завершён.",
        "ai_select_from_buttons": "👆 Выбери персонажа из кнопок выше.",
        "ai_limit_plus": "⏰ Лимит исчерпан ({limit} сообщений/день).\n\n🚀 Upgrade до Premium Plus — безлимит на все ИИ!",
        "ai_limit_basic": "⏰ Лимит исчерпан ({limit} сообщений/день).\n\n⭐ Купи Premium — больше сообщений и безлимит basic ИИ!",
        "ai_remaining": "_💬 Осталось {left} сообщений_",
        "ai_unavailable": "😔 ИИ временно недоступен.",
        "ai_no_funds": "💳 ИИ временно недоступен — нет средств на балансе.",
        "ai_error": "😔 ИИ временно недоступен. Попробуй позже.",
        "ai_connection_error": "😔 Ошибка соединения с ИИ.",
        "ai_profile_required": "Сначала заполни анкету!",
        "ai_session_lost": "Сессия потеряна. Начни заново.",
        "ai_in_live_chat": "⚠️ Сейчас недоступно — ты в чате с живым собеседником.",
        "ai_complete_profile": "⚠️ Сейчас недоступно — сначала заверши анкету.",
        "ai_waiting_continue": "⏳ Продолжаем ждать...",
        "ai_quick_start": "✅ Ты общаешься с {name}\n{description}\n\n{limit_text}",
        "ai_greeting": "Поприветствуй собеседника и начни разговор. Коротко, 1-2 предложения на русском.",
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
        # Buttons — privacy/rules/channel
        "btn_accept_privacy": "✅ Accept and continue",
        "btn_decline_privacy": "❌ Decline",
        "btn_accept_rules": "✅ Accept rules",
        "btn_check_channel": "✅ Check subscription",
        "btn_skip_channel": "⏭ Skip",
        # Buttons — main menu
        "btn_search": "⚡ Search",
        "btn_find": "🔍 By profile",
        "btn_ai_chat": "🤖 AI Chat",
        "btn_profile": "👤 Profile",
        "btn_settings": "⚙️ Settings",
        "btn_help": "❓ Help",
        # Buttons — chat
        "btn_next": "⏭ Next",
        "btn_stop": "❌ Stop",
        "btn_like": "👍 Like",
        "btn_complaint": "🚩 Report",
        "btn_topic": "🎲 Give topic",
        "btn_home": "🏠 Main menu",
        # Buttons — form/search
        "btn_cancel_reg": "❌ Cancel form",
        "btn_start_form": "✅ Got it, start form",
        "btn_cancel_search": "❌ Cancel search",
        # Buttons — gender
        "btn_male": "👨 Guy",
        "btn_female": "👩 Girl",
        "btn_other": "⚧ Other",
        "btn_find_male": "👨 A guy",
        "btn_find_female": "👩 A girl",
        "btn_find_other": "⚧ Other",
        "btn_find_any": "🔀 Anyone",
        "btn_back": "◀️ Back",
        # Buttons — mode
        "btn_mode_simple": "💬 Just chatting",
        "btn_mode_flirt": "💋 Flirt",
        "btn_mode_kink": "🔥 Kink / roleplay (18+)",
        # Buttons — AI chat
        "btn_change_char": "🔄 Change character",
        "btn_end_ai_chat": "❌ End chat",
        "btn_find_live": "🔍 Find a real person",
        # Mode and gender display names
        "mode_simple": "Just chatting 💬",
        "mode_flirt": "Flirt 💋",
        "mode_kink": "Kink 🔥",
        "gender_male": "Guy 👨",
        "gender_female": "Girl 👩",
        "gender_other": "Other ⚧",
        # Search
        "searching_anon": "⚡ Looking for an anonymous partner...",
        "connected": "👤 Connected! Good luck! 🎉",
        "queue_info": "👥 In {mode} mode: {count} people.\n{status}",
        "queue_searching": "🔍 Searching...",
        "queue_priority": "🚀 Priority search ⭐",
        "search_cancelled": "❌ Search cancelled.",
        "not_searching": "You are not searching.",
        # Chat
        "chat_ended": "💔 Chat ended.",
        "partner_left": "😔 Your partner left the chat.",
        "not_in_chat": "You are not in a chat.",
        "spam_warning": "⚠️ Don't spam!",
        "like_sent": "👍 Like sent!",
        "like_received": "👍 Your partner liked you! ⭐",
        "like_already": "👍 You already liked this partner!",
        "topic_sent": "🎲 Conversation topic:\n\n{topic}",
        "topic_received": "🎲 Your partner suggests a topic:\n\n{topic}",
        "mutual_match": "🎉 Mutual interest! Private anonymous chat opened.\nYou are still anonymous to each other.",
        "mutual_request_sent": "❤️ Request sent!\nIf your partner wants too — you'll be connected within 10 minutes.",
        "mutual_request_received": "💌 Your partner wants to continue chatting!\nReply if you want to too:",
        "mutual_no_response": "😔 Your partner didn't respond to the continuation request.",
        "mutual_decline_ok": "Okay, no problem!",
        "mutual_already_in_chat": "😔 One of you is already in a chat.",
        "partner_busy": "😔 Your partner is already chatting with someone else.",
        "after_chat_propose": "Did you like your partner?\nSuggest continuing anonymously — if they agree, you'll be connected 😊",
        "inactivity_end": "⏰ Chat ended — 7 min of inactivity.",
        "inactivity_ai_end": "⏰ AI chat ended — 10 min of inactivity.",
        # Complaint
        "complaint_prompt": "🚩 Choose the reason for your report:",
        "complaint_cancelled": "↩️ Report cancelled.",
        "complaint_sent": "🚩 Report #{id} sent. AI is analyzing...",
        "complaint_not_in_chat": "You are not in a chat.",
        "partner_complained": "⚠️ Someone filed a report against you.",
        # Registration
        "reg_rules_profile": (
            "📜 Chat rules:\n\n"
            "• Respect your partner\n"
            "• 👍 Like — if you enjoyed it\n"
            "• 🚩 Report — only for real violations!\n"
            "• Advertising = ban\n"
            "• False report = sanctions\n\n"
            "Press ✅ Got it, start form to continue."
        ),
        "reg_name_prompt": "📝 What's your name?",
        "reg_age_prompt": "🎂 How old are you?",
        "reg_gender_prompt": "⚧ Choose your gender:",
        "reg_mode_prompt": "💬 Choose a communication mode:",
        "reg_interests_prompt": "🎯 Choose 1–3 interests:",
        "reg_cancelled": "❌ Form cancelled.",
        "reg_age_invalid": "❗ Enter a number.",
        "reg_age_too_young": "{joke}\n\nEnter a valid age (minimum 16):",
        "reg_age_too_old": "{joke}\n\nEnter a real age (16–99).",
        "reg_gender_invalid": "Choose gender from buttons 👇",
        "reg_mode_invalid": "Choose mode from buttons 👇",
        "reg_kink_age": "🔞 Kink / roleplay is only available from age 18.\nChoose another mode:",
        "reg_interests_min": "Choose at least one!",
        "reg_interests_max": "Maximum 3!",
        "reg_interests_invalid": "👆 Press the buttons above to choose interests.",
        "reg_done": "✅ Profile completed!",
        "reg_interest_added": "Added: {val}",
        "reg_interest_removed": "Removed: {val}",
        # Profile
        "profile_not_filled": "Profile not filled. Press '🔍 By profile'",
        "profile_text": (
            "👤 Profile{badge}:\n"
            "Name: {name}\n"
            "Age: {age}\n"
            "Gender: {gender}\n"
            "Mode: {mode}\n"
            "Interests: {interests}\n"
            "⭐ Rating: {rating}\n"
            "👍 Likes: {likes}\n"
            "💬 Chats: {chats}\n"
            "⚠️ Warnings: {warns}\n"
            "💎 Status: {premium}"
        ),
        "profile_upgrade": "\n\n⭐ Upgrade to Premium — priority, more AI, no ads!",
        "premium_eternal": "{tier} (lifetime)",
        "premium_until_date": "{tier} until {until}",
        "premium_none": "None",
        # Edit profile
        "edit_name_prompt": "✏️ New name:",
        "edit_age_prompt": "🎂 New age:",
        "edit_gender_prompt": "⚧ Choose gender:",
        "edit_mode_prompt": "💬 Choose mode:",
        "edit_interests_prompt": "🎯 Choose interests:",
        "edit_back": "↩️ Back.",
        "edit_name_done": "✅ Name updated!",
        "edit_age_done": "{joke}\n\n✅ Age updated!",
        "edit_age_invalid": "❗ Enter a number from 16 to 99",
        "edit_gender_done": "✅ Gender updated!",
        "edit_interests_done": "✅ Interests updated!",
        "edit_done": "Done!",
        # Settings
        "settings_title": "⚙️ Search settings:",
        "settings_gender_prompt": "👤 Who do you want to find?",
        "settings_gender_locked": "🔒 Gender filter in Flirt and Kink — Premium only!",
        "settings_premium_only": "🔒 Premium only! Buy via /premium",
        "settings_cross_unavailable": "Cross-mode is not available in Chat mode",
        "settings_changed": "✅ Changed",
        "settings_age_any": "✅ Age: Any",
        "settings_age_range": "✅ Age: {min}–{max}",
        "settings_gender_saved": "✅ Gender filter saved!",
        # Stats
        "stats_text": (
            "📊 Your stats:\n\n"
            "💬 Total chats: {total_chats}\n"
            "👍 Likes received: {likes}\n"
            "⭐ Rating: {rating}\n"
            "⚠️ Warnings: {warns}\n"
            "📅 Days in bot: {days}\n"
            "{premium}"
        ),
        "stats_premium_eternal": "⭐ Premium: Lifetime",
        "stats_premium_until": "⭐ Premium until {until}",
        "stats_premium_active": "⭐ Premium active",
        "stats_no_premium": "💎 Premium: None",
        "not_registered": "Register first via /start!",
        # Premium
        "premium_title": "⭐ MatchMe Subscriptions\n\n{status}📊 What's included:\n⭐ Premium: unlimited basic AI, 50 premium AI msgs/day, priority, no ads\n🚀 Premium Plus: unlimited ALL AI, priority, no ads\n🧠 AI Pro: unlimited all AI models\n\nChoose a plan:",
        "premium_status_eternal": "✅ Current: {tier} (lifetime)\n\n",
        "premium_status_until": "✅ Current: {tier} until {until}\n\n",
        "premium_info": (
            "📊 Subscription comparison:\n\n"
            "⭐ Premium (from 99 Stars):\n"
            "• Unlimited basic AI (Danil, Polina, Max)\n"
            "• 50 msgs/day premium AI + 10 bonus\n"
            "• Priority search, no ads\n\n"
            "🚀 Premium Plus (from 499 Stars):\n"
            "• Everything in Premium\n"
            "• Unlimited ALL AI models\n"
            "• Best value!\n\n"
            "🧠 AI Pro (from 399 Stars):\n"
            "• Unlimited all AI models\n"
            "• Unlocks everything like Plus\n\n"
            "💡 Tip: Premium Plus is the best deal!"
        ),
        "premium_activated": "🎉 {tier} activated!\n\n📦 Plan: {label}\n📅 Until {until}\n\n{benefits}",
        "premium_unknown_plan": "Unknown plan",
        "benefit_premium": "Unlimited basic AI, 50 premium AI msgs/day, priority, no ads!",
        "benefit_plus": "Unlimited ALL AI models, priority, no ads!",
        "benefit_ai_pro": "Unlimited ALL AI models!",
        # Reset
        "reset_confirm": (
            "⚠️ Full profile reset!\n\n"
            "Will be deleted: name, age, gender, mode, interests, rating\n"
            "❗ Ban, warnings and Premium will be kept.\n\nAre you sure?"
        ),
        "reset_done": "✅ Profile reset!",
        "reset_refill": "👋 Press '🔍 By profile' to fill out the form again.",
        "reset_cancelled": "❌ Reset cancelled.",
        "reset_back": "Back to menu.",
        # Help
        "help_text": (
            "🆘 MatchMe Help:\n\n"
            "⚡ Search — quick anonymous search\n"
            "🔍 By profile — by mode and interests\n"
            "🤖 AI Chat — chat with AI\n"
            "📊 /stats — your stats\n"
            "⭐ /premium — Premium subscription\n\n"
            "In chat:\n"
            "⏭ Next — find another partner\n"
            "❌ Stop — end chat\n"
            "🎲 Topic — random conversation topic\n"
            "👍 Like — boost rating\n"
            "🚩 Report — for violations\n\n"
            "/reset — reset profile\n"
            "If something broke — /start"
        ),
        "unavailable": "⚠️ Not available right now — {reason}.",
        "no_partner_wait": (
            "⏳ Search is taking longer than usual...\n\n"
            "💡 While you wait — chat with {name}!\n"
            "AI partner replies instantly 🤖"
        ),
        "upsell": "⭐ Enjoying MatchMe?\nPremium = priority search + more AI + no ads!",
        "ad_message": "📢 Your ad could be here\n\n⭐ Buy Premium and remove ads forever!",
        "hardban": "🚫 Permanent ban for violating the rules.",
        # AI chat
        "ai_menu": (
            "🤖 AI Chat\n\n"
            "All characters are free!\n"
            "💬 Basic: 20 messages/day\n"
            "🔥 Premium: 10 messages/day\n"
            "⭐ Subscription removes limits\n\n"
            "Choose who you want to talk to:"
        ),
        "ai_select_char": "Choose a character:",
        "ai_char_not_found": "Character not found.",
        "ai_power_soon": "🔧 Coming soon! Stay tuned.",
        "ai_chat_active": "💬 AI chat active",
        "ai_unlimited": "♾ Unlimited",
        "ai_limit_info": "💬 Limit: {limit} messages/day",
        "ai_ended": "✅ AI chat ended.",
        "ai_select_from_buttons": "👆 Choose a character from the buttons above.",
        "ai_limit_plus": "⏰ Limit reached ({limit} messages/day).\n\n🚀 Upgrade to Premium Plus — unlimited all AI!",
        "ai_limit_basic": "⏰ Limit reached ({limit} messages/day).\n\n⭐ Buy Premium — more messages and unlimited basic AI!",
        "ai_remaining": "_💬 {left} messages left_",
        "ai_unavailable": "😔 AI is temporarily unavailable.",
        "ai_no_funds": "💳 AI temporarily unavailable — no balance.",
        "ai_error": "😔 AI temporarily unavailable. Try again later.",
        "ai_connection_error": "😔 AI connection error.",
        "ai_profile_required": "Fill out your profile first!",
        "ai_session_lost": "Session lost. Start again.",
        "ai_in_live_chat": "⚠️ Not available — you are in a live chat.",
        "ai_complete_profile": "⚠️ Not available — complete your profile first.",
        "ai_waiting_continue": "⏳ Continuing to wait...",
        "ai_quick_start": "✅ You are chatting with {name}\n{description}\n\n{limit_text}",
        "ai_greeting": "Greet the user and start a conversation. Short, 1-2 sentences in English.",
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
        # Botones — privacy/rules/channel
        "btn_accept_privacy": "✅ Aceptar y continuar",
        "btn_decline_privacy": "❌ Rechazar",
        "btn_accept_rules": "✅ Aceptar reglas",
        "btn_check_channel": "✅ Verificar suscripción",
        "btn_skip_channel": "⏭ Omitir",
        # Botones — menú principal
        "btn_search": "⚡ Buscar",
        "btn_find": "🔍 Por perfil",
        "btn_ai_chat": "🤖 Chat IA",
        "btn_profile": "👤 Perfil",
        "btn_settings": "⚙️ Ajustes",
        "btn_help": "❓ Ayuda",
        # Botones — chat
        "btn_next": "⏭ Siguiente",
        "btn_stop": "❌ Parar",
        "btn_like": "👍 Me gusta",
        "btn_complaint": "🚩 Reportar",
        "btn_topic": "🎲 Dar tema",
        "btn_home": "🏠 Menú principal",
        # Botones — formulario/búsqueda
        "btn_cancel_reg": "❌ Cancelar formulario",
        "btn_start_form": "✅ Entendido, iniciar formulario",
        "btn_cancel_search": "❌ Cancelar búsqueda",
        # Botones — género
        "btn_male": "👨 Chico",
        "btn_female": "👩 Chica",
        "btn_other": "⚧ Otro",
        "btn_find_male": "👨 Un chico",
        "btn_find_female": "👩 Una chica",
        "btn_find_other": "⚧ Otro",
        "btn_find_any": "🔀 Cualquiera",
        "btn_back": "◀️ Volver",
        # Botones — modo
        "btn_mode_simple": "💬 Solo charlar",
        "btn_mode_flirt": "💋 Coqueteo",
        "btn_mode_kink": "🔥 Kink / juego de rol (18+)",
        # Botones — chat IA
        "btn_change_char": "🔄 Cambiar personaje",
        "btn_end_ai_chat": "❌ Terminar chat",
        "btn_find_live": "🔍 Buscar persona real",
        # Nombres de modos y géneros (para mostrar)
        "mode_simple": "Solo charlar 💬",
        "mode_flirt": "Coqueteo 💋",
        "mode_kink": "Kink 🔥",
        "gender_male": "Chico 👨",
        "gender_female": "Chica 👩",
        "gender_other": "Otro ⚧",
        # Búsqueda
        "searching_anon": "⚡ Buscando un compañero anónimo...",
        "connected": "👤 ¡Conectado! ¡Buena suerte! 🎉",
        "queue_info": "👥 En modo {mode}: {count} personas.\n{status}",
        "queue_searching": "🔍 Buscando...",
        "queue_priority": "🚀 Búsqueda prioritaria ⭐",
        "search_cancelled": "❌ Búsqueda cancelada.",
        "not_searching": "No estás buscando.",
        # Chat
        "chat_ended": "💔 Chat terminado.",
        "partner_left": "😔 Tu compañero abandonó el chat.",
        "not_in_chat": "No estás en un chat.",
        "spam_warning": "⚠️ ¡No hagas spam!",
        "like_sent": "👍 ¡Me gusta enviado!",
        "like_received": "👍 ¡A tu compañero le gustaste! ⭐",
        "like_already": "👍 ¡Ya le diste me gusta a este compañero!",
        "topic_sent": "🎲 Tema de conversación:\n\n{topic}",
        "topic_received": "🎲 Tu compañero sugiere un tema:\n\n{topic}",
        "mutual_match": "🎉 ¡Interés mutuo! Chat privado anónimo abierto.\nSiguen siendo anónimos el uno para el otro.",
        "mutual_request_sent": "❤️ ¡Solicitud enviada!\nSi tu compañero también quiere — los conectarán en 10 minutos.",
        "mutual_request_received": "💌 ¡Tu compañero quiere seguir chateando!\nResponde si tú también quieres:",
        "mutual_no_response": "😔 Tu compañero no respondió a la solicitud.",
        "mutual_decline_ok": "¡Está bien, sin problema!",
        "mutual_already_in_chat": "😔 Uno de ustedes ya está en un chat.",
        "partner_busy": "😔 Tu compañero ya está chateando con alguien más.",
        "after_chat_propose": "¿Te gustó tu compañero?\nSugiere continuar de forma anónima — si acepta, los conectarán 😊",
        "inactivity_end": "⏰ Chat terminado — 7 min de inactividad.",
        "inactivity_ai_end": "⏰ Chat IA terminado — 10 min de inactividad.",
        # Reporte
        "complaint_prompt": "🚩 Elige el motivo del reporte:",
        "complaint_cancelled": "↩️ Reporte cancelado.",
        "complaint_sent": "🚩 Reporte #{id} enviado. La IA está analizando...",
        "complaint_not_in_chat": "No estás en un chat.",
        "partner_complained": "⚠️ Alguien presentó un reporte contra ti.",
        # Registro
        "reg_rules_profile": (
            "📜 Reglas del chat:\n\n"
            "• Respeta a tu compañero\n"
            "• 👍 Me gusta — si te gustó\n"
            "• 🚩 Reportar — solo por violaciones reales!\n"
            "• Publicidad = ban\n"
            "• Reporte falso = sanciones\n\n"
            "Presiona ✅ Entendido, iniciar formulario para continuar."
        ),
        "reg_name_prompt": "📝 ¿Cómo te llamas?",
        "reg_age_prompt": "🎂 ¿Cuántos años tienes?",
        "reg_gender_prompt": "⚧ Elige tu género:",
        "reg_mode_prompt": "💬 Elige un modo de comunicación:",
        "reg_interests_prompt": "🎯 Elige 1–3 intereses:",
        "reg_cancelled": "❌ Formulario cancelado.",
        "reg_age_invalid": "❗ Ingresa un número.",
        "reg_age_too_young": "{joke}\n\nIngresa una edad válida (mínimo 16):",
        "reg_age_too_old": "{joke}\n\nIngresa una edad real (16–99).",
        "reg_gender_invalid": "Elige género con los botones 👇",
        "reg_mode_invalid": "Elige modo con los botones 👇",
        "reg_kink_age": "🔞 Kink / juego de rol solo está disponible desde los 18 años.\nElige otro modo:",
        "reg_interests_min": "¡Elige al menos uno!",
        "reg_interests_max": "¡Máximo 3!",
        "reg_interests_invalid": "👆 Presiona los botones de arriba para elegir intereses.",
        "reg_done": "✅ ¡Perfil completado!",
        "reg_interest_added": "Añadido: {val}",
        "reg_interest_removed": "Eliminado: {val}",
        # Perfil
        "profile_not_filled": "Perfil no completado. Presiona '🔍 Por perfil'",
        "profile_text": (
            "👤 Perfil{badge}:\n"
            "Nombre: {name}\n"
            "Edad: {age}\n"
            "Género: {gender}\n"
            "Modo: {mode}\n"
            "Intereses: {interests}\n"
            "⭐ Puntuación: {rating}\n"
            "👍 Me gustas: {likes}\n"
            "💬 Chats: {chats}\n"
            "⚠️ Advertencias: {warns}\n"
            "💎 Estado: {premium}"
        ),
        "profile_upgrade": "\n\n⭐ ¡Hazte Premium — prioridad, más IA, sin anuncios!",
        "premium_eternal": "{tier} (de por vida)",
        "premium_until_date": "{tier} hasta {until}",
        "premium_none": "Ninguno",
        # Editar perfil
        "edit_name_prompt": "✏️ Nuevo nombre:",
        "edit_age_prompt": "🎂 Nueva edad:",
        "edit_gender_prompt": "⚧ Elige género:",
        "edit_mode_prompt": "💬 Elige modo:",
        "edit_interests_prompt": "🎯 Elige intereses:",
        "edit_back": "↩️ Volver.",
        "edit_name_done": "✅ ¡Nombre actualizado!",
        "edit_age_done": "{joke}\n\n✅ ¡Edad actualizada!",
        "edit_age_invalid": "❗ Ingresa un número del 16 al 99",
        "edit_gender_done": "✅ ¡Género actualizado!",
        "edit_interests_done": "✅ ¡Intereses actualizados!",
        "edit_done": "¡Listo!",
        # Ajustes
        "settings_title": "⚙️ Ajustes de búsqueda:",
        "settings_gender_prompt": "👤 ¿A quién quieres encontrar?",
        "settings_gender_locked": "🔒 Filtro de género en Coqueteo y Kink — ¡solo Premium!",
        "settings_premium_only": "🔒 ¡Solo Premium! Compra via /premium",
        "settings_cross_unavailable": "El modo cruzado no está disponible en modo Chat",
        "settings_changed": "✅ Cambiado",
        "settings_age_any": "✅ Edad: Cualquiera",
        "settings_age_range": "✅ Edad: {min}–{max}",
        "settings_gender_saved": "✅ ¡Filtro de género guardado!",
        # Estadísticas
        "stats_text": (
            "📊 Tus estadísticas:\n\n"
            "💬 Chats totales: {total_chats}\n"
            "👍 Me gustas recibidos: {likes}\n"
            "⭐ Puntuación: {rating}\n"
            "⚠️ Advertencias: {warns}\n"
            "📅 Días en el bot: {days}\n"
            "{premium}"
        ),
        "stats_premium_eternal": "⭐ Premium: De por vida",
        "stats_premium_until": "⭐ Premium hasta {until}",
        "stats_premium_active": "⭐ Premium activo",
        "stats_no_premium": "💎 Premium: Ninguno",
        "not_registered": "¡Regístrate primero via /start!",
        # Premium
        "premium_title": "⭐ Suscripciones MatchMe\n\n{status}📊 Qué incluye:\n⭐ Premium: IA básica ilimitada, 50 msgs IA premium/día, prioridad, sin anuncios\n🚀 Premium Plus: TODA IA ilimitada, prioridad, sin anuncios\n🧠 AI Pro: todos los modelos IA ilimitados\n\nElige un plan:",
        "premium_status_eternal": "✅ Actual: {tier} (de por vida)\n\n",
        "premium_status_until": "✅ Actual: {tier} hasta {until}\n\n",
        "premium_info": (
            "📊 Comparación de suscripciones:\n\n"
            "⭐ Premium (desde 99 Stars):\n"
            "• IA básica ilimitada\n"
            "• 50 msgs/día IA premium + 10 bonus\n"
            "• Búsqueda prioritaria, sin anuncios\n\n"
            "🚀 Premium Plus (desde 499 Stars):\n"
            "• Todo de Premium\n"
            "• TODOS los modelos IA ilimitados\n"
            "• ¡Mejor precio!\n\n"
            "🧠 AI Pro (desde 399 Stars):\n"
            "• Todos los modelos IA ilimitados\n"
            "• Desbloquea todo como Plus\n\n"
            "💡 Consejo: ¡Premium Plus es la mejor opción!"
        ),
        "premium_activated": "🎉 ¡{tier} activado!\n\n📦 Plan: {label}\n📅 Hasta {until}\n\n{benefits}",
        "premium_unknown_plan": "Plan desconocido",
        "benefit_premium": "IA básica ilimitada, 50 msgs IA premium/día, prioridad, ¡sin anuncios!",
        "benefit_plus": "¡TODOS los modelos IA ilimitados, prioridad, sin anuncios!",
        "benefit_ai_pro": "¡Todos los modelos IA ilimitados!",
        # Restablecer perfil
        "reset_confirm": (
            "⚠️ ¡Restablecimiento completo del perfil!\n\n"
            "Se eliminará: nombre, edad, género, modo, intereses, puntuación\n"
            "❗ El ban, advertencias y Premium se conservarán.\n\n¿Estás seguro?"
        ),
        "reset_done": "✅ ¡Perfil restablecido!",
        "reset_refill": "👋 Presiona '🔍 Por perfil' para llenar el formulario de nuevo.",
        "reset_cancelled": "❌ Restablecimiento cancelado.",
        "reset_back": "Volver al menú.",
        # Ayuda
        "help_text": (
            "🆘 Ayuda de MatchMe:\n\n"
            "⚡ Buscar — búsqueda anónima rápida\n"
            "🔍 Por perfil — por modo e intereses\n"
            "🤖 Chat IA — chatea con IA\n"
            "📊 /stats — tus estadísticas\n"
            "⭐ /premium — suscripción Premium\n\n"
            "En el chat:\n"
            "⏭ Siguiente — buscar otro compañero\n"
            "❌ Parar — terminar chat\n"
            "🎲 Tema — tema de conversación aleatorio\n"
            "👍 Me gusta — subir puntuación\n"
            "🚩 Reportar — por violaciones\n\n"
            "/reset — restablecer perfil\n"
            "Si algo falló — /start"
        ),
        "unavailable": "⚠️ No disponible ahora — {reason}.",
        "no_partner_wait": (
            "⏳ La búsqueda está tardando más de lo usual...\n\n"
            "💡 Mientras esperas — ¡chatea con {name}!\n"
            "El compañero IA responde al instante 🤖"
        ),
        "upsell": "⭐ ¿Disfrutas MatchMe?\n¡Premium = búsqueda prioritaria + más IA + sin anuncios!",
        "ad_message": "📢 Tu anuncio podría estar aquí\n\n⭐ ¡Compra Premium y elimina los anuncios para siempre!",
        "hardban": "🚫 Ban permanente por violar las reglas.",
        # Chat IA
        "ai_menu": (
            "🤖 Chat IA\n\n"
            "¡Todos los personajes son gratis!\n"
            "💬 Básico: 20 mensajes/día\n"
            "🔥 Premium: 10 mensajes/día\n"
            "⭐ La suscripción elimina los límites\n\n"
            "Elige con quién quieres hablar:"
        ),
        "ai_select_char": "Elige un personaje:",
        "ai_char_not_found": "Personaje no encontrado.",
        "ai_power_soon": "🔧 ¡Próximamente! Mantente al tanto.",
        "ai_chat_active": "💬 Chat IA activo",
        "ai_unlimited": "♾ Ilimitado",
        "ai_limit_info": "💬 Límite: {limit} mensajes/día",
        "ai_ended": "✅ Chat IA terminado.",
        "ai_select_from_buttons": "👆 Elige un personaje con los botones de arriba.",
        "ai_limit_plus": "⏰ Límite alcanzado ({limit} mensajes/día).\n\n🚀 ¡Hazte Premium Plus — IA ilimitada!",
        "ai_limit_basic": "⏰ Límite alcanzado ({limit} mensajes/día).\n\n⭐ ¡Compra Premium — más mensajes e IA básica ilimitada!",
        "ai_remaining": "_💬 Te quedan {left} mensajes_",
        "ai_unavailable": "😔 La IA no está disponible temporalmente.",
        "ai_no_funds": "💳 IA no disponible temporalmente — sin saldo.",
        "ai_error": "😔 IA no disponible. Inténtalo más tarde.",
        "ai_connection_error": "😔 Error de conexión con la IA.",
        "ai_profile_required": "¡Completa tu perfil primero!",
        "ai_session_lost": "Sesión perdida. Comienza de nuevo.",
        "ai_in_live_chat": "⚠️ No disponible — estás en un chat en vivo.",
        "ai_complete_profile": "⚠️ No disponible — completa tu perfil primero.",
        "ai_waiting_continue": "⏳ Siguiendo a la espera...",
        "ai_quick_start": "✅ Estás chateando con {name}\n{description}\n\n{limit_text}",
        "ai_greeting": "Saluda al usuario e inicia una conversación. Breve, 1-2 frases en español.",
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
