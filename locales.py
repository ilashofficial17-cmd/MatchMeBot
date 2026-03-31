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
        "btn_erase_memory": "🧹 Стереть память",
        "memory_erased": "🧹 Память стёрта. Персонаж забыл всё о вас. Начинаем заново!",
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
        # Модерация — уведомления пользователю
        "mod_warn": "⚠️ Предупреждение: {reason}\nСледующее нарушение приведёт к бану.",
        "mod_ban3h": "🚫 Бан на 3 часа: {reason}",
        "mod_ban24h": "🚫 Бан на 24 часа: {reason}",
        "mod_banperm": "🚫 Перманентный бан: {reason}",
        # Административные действия — уведомления пользователю
        "adm_warn_user": "⚠️ Предупреждение от администратора.",
        "adm_warn_next_ban": "⚠️ Предупреждение. Следующее нарушение — бан.",
        "adm_kick_user": "❌ Кик от администратора.",
        "adm_ban3h": "🚫 Бан на 3 часа.",
        "adm_ban3h_complaint": "🚫 Бан на 3 часа по жалобе.",
        "adm_ban24h": "🚫 Бан на 24 часа.",
        "adm_ban24h_complaint": "🚫 Бан на 24 часа по жалобе.",
        "adm_banperm_user": "🚫 Перманентный бан.",
        "adm_unban": "✅ Ты разблокирован! Добро пожаловать обратно.",
        "adm_false_complaint": "⚠️ Жалоба признана необоснованной.",
        "adm_ban_abuse": "🚫 Бан за злоупотребление жалобами.",
        "adm_premium_granted": "⭐ Тебе выдан Premium на 30 дней!",
        "adm_premium_removed": "❌ Premium отменён администратором.",
        "adm_update_now": "🔧 Бот обновляется прямо сейчас!",
        "adm_update_soon": "🔧 Через {minutes} мин. обновление!",
        "reminder_ai_bonus": "🎁 Мы скучали! +5 бесплатных AI сообщений специально для тебя!\nЗаходи общаться 💬",
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
        "premium_title": "⭐ MatchMe Premium\n\n{status}📊 Что входит:\n• Безлимит на всех ИИ персонажей\n• VIP персонажи открыты\n• Приоритет в поиске\n• Без рекламы\n\nВыбери тариф:",
        "premium_status_eternal": "✅ Сейчас: {tier} (вечный)\n\n",
        "premium_status_until": "✅ Сейчас: {tier} до {until}\n\n",
        "premium_info": (
            "📊 Premium подписка:\n\n"
            "⭐ Что входит:\n"
            "• Безлимит на всех ИИ персонажей\n"
            "• VIP персонажи (Флирт, Kink) открыты\n"
            "• Приоритет в поиске\n"
            "• Без рекламы\n\n"
            "💡 Совет: годовая подписка — самый выгодный вариант!"
        ),
        "premium_activated": "🎉 {tier} активирован!\n\n📦 Тариф: {label}\n📅 До {until}\n\n{benefits}",
        "premium_unknown_plan": "Неизвестный тариф",
        "benefit_premium": "Безлимит ИИ, VIP персонажи, приоритет, без рекламы!",
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
            "💬 Basic: 20 сообщений/день\n"
            "🔥 VIP: 10 сообщений/день\n"
            "🔥 VIP+: только по подписке\n"
            "⭐ Подписка снимает все лимиты\n\n"
            "Выбери с кем хочешь поговорить:"
        ),
        "ai_select_char": "Выбери персонажа:",
        "ai_char_not_found": "Персонаж не найден.",
        "ai_power_soon": "🔧 В разработке! Следи за обновлениями.",
        "ai_vip_required": "🔒 Этот персонаж доступен только с VIP подпиской.",
        "ai_vip_plus_required": "🔒 Этот VIP+ персонаж доступен только с Premium подпиской.",
        "ai_chat_active": "💬 Чат с ИИ активен",
        "ai_char_entered": "👤 {name} вошёл в чат\n\n{bio}",
        "ai_unlimited": "♾ Безлимит",
        "ai_limit_info": "💬 Лимит: {limit} сообщений/день",
        "ai_ended": "✅ Чат с ИИ завершён.",
        "ai_select_from_buttons": "👆 Выбери персонажа из кнопок выше.",
        "ai_limit_plus": "⏰ Лимит исчерпан ({limit} сообщений/день).\n\nСброс через 24 часа. Пока можешь пообщаться с живым собеседником!",
        "ai_limit_basic": "⏰ Лимит исчерпан ({limit} сообщений/день).\n\n⭐ Купи Premium — безлимит на ИИ и VIP персонажи!",
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
        "ai_chatting_with": "✅ Ты общаешься с {name}\n{description}\n\n{limit_text}\n\nНапиши что-нибудь!",
        "ai_greeting": "Поприветствуй собеседника и начни разговор. Коротко, 1-2 предложения на русском.",
        "ai_buy_sub": "⭐ Купить подписку",
        "searching": "🔍 Ищем...",
        # Описания персонажей
        "char_danil_desc": "Общительный парень, поговорит на любые темы",
        "char_polina_desc": "Живая девушка, ироничная и с юмором",
        "char_max_desc": "Уверенный парень, пришёл флиртовать",
        "char_violetta_desc": "Игривая девушка, дерзкая и кокетливая",
        "char_alisa_desc": "Послушная сабмиссив, покорная и нежная",
        "char_dmitri_desc": "Опытный Доминант, строгий и властный",
        "char_rolemaster_desc": "Придумывает сценарии и играет любую роль",
        # Кнопки жалоб
        "rep_minor": "🔞 Несовершеннолетние",
        "rep_spam": "💰 Спам / Реклама",
        "rep_abuse": "😡 Угрозы / Оскорбления",
        "rep_nsfw": "🔞 Пошлятина без согласия",
        "rep_other": "🔄 Другое",
        "rep_cancel": "◀️ Отмена",
        # Кнопки редактирования профиля
        "edit_btn_name": "✏️ Имя",
        "edit_btn_age": "🎂 Возраст",
        "edit_btn_gender": "⚧ Пол",
        "edit_btn_mode": "💬 Режим",
        "edit_btn_interests": "🎯 Интересы",
        # AI персонажи — Блок 1: Общение
        "char_luna": "🌙 Луна",
        "char_luna_desc": "Мечтательная девушка, художница — тепло и атмосфера",
        "char_max_simple": "🧢 Макс",
        "char_max_simple_desc": "Простой парень из IT — юмор и без понтов",
        "char_aurora": "✨ Аврора — VIP",
        "char_aurora_desc": "Директор по маркетингу, 18 стран — элегантность и сарказм",
        "char_alex": "🔥 Алекс — VIP",
        "char_alex_desc": "Фрилансер и искатель приключений — философия и вызов",
        "char_aurora_locked": "🔒 Аврора — VIP",
        "char_alex_locked": "🔒 Алекс — VIP",
        "char_coming_soon": "🔜 Kink — скоро",
        # AI персонажи — Блок 2: Флирт
        "char_mia": "🍭 Мия",
        "char_mia_desc": "Игривая студентка — сладко и кокетливо",
        "char_kai": "🎧 Кай",
        "char_kai_desc": "Диджей с харизмой — уверенный флирт",
        "char_diana": "🏛️ Диана — VIP",
        "char_diana_desc": "Куратор галереи — чувственно и загадочно",
        "char_leon": "⌚ Леон — VIP",
        "char_leon_desc": "Архитектор — сдержанный огонь и доминирование",
        "char_diana_locked": "🔒 Диана — VIP",
        "char_leon_locked": "🔒 Леон — VIP",
        # AI персонажи — Блок 3: Kink (все VIP)
        "char_lilit": "🖤 Лилит — VIP+",
        "char_lilit_desc": "Доминант-девушка — контроль и страсть",
        "char_eva": "🌸 Ева — VIP+",
        "char_eva_desc": "Сабмиссив-девушка — нежная и послушная",
        "char_damir": "🎯 Дамир — VIP+",
        "char_damir_desc": "Доминант-парень — уверенный и властный",
        "char_ars": "🐾 Арс — VIP+",
        "char_ars_desc": "Сабмиссив-парень — мягкий и покорный",
        "char_master": "🎭 Мастер историй — VIP+",
        "char_master_desc": "Генератор сценариев — любой сюжет по твоему желанию",
        "char_lilit_locked": "🔒 Лилит — VIP+",
        "char_eva_locked": "🔒 Ева — VIP+",
        "char_damir_locked": "🔒 Дамир — VIP+",
        "char_ars_locked": "🔒 Арс — VIP+",
        "char_master_locked": "🔒 Мастер историй — VIP+",
        "char_power_soon": "🧠 Мощная нейронка (скоро)",
        "char_vip_locked": "🔒 Только для VIP+",
        "btn_ai_info": "📋 Описание персонажей",
        # Заголовки блоков ИИ
        "ai_block_simple": "💬 Общение",
        "ai_block_flirt": "💋 Флирт",
        "ai_block_kink": "🔥 Kink",
        # Premium кнопки
        "prem_header": "── Premium ──",
        "prem_compare": "❓ Что входит",
        "prem_7d": "⭐ 7 дней — 99 Stars",
        "prem_1m": "⭐ 1 месяц — 299 Stars",
        "prem_3m": "⭐ 3 месяца — 599 Stars",
        "prem_1y": "⭐ 1 год — 1799 Stars",
        "btn_continue": "❤️ Хочу продолжить общение",
        "btn_find_new": "🔍 Найти нового",
        "btn_to_menu": "🏠 В меню",
        # Общие — восстановление, чат
        "bot_restarted": "🔄 Бот обновлён. Твой чат восстановлен!",
        "chat_start": "✅ Начинайте общение!",
        "partner_found": (
            "👤 Собеседник найден!{badge}\n"
            "Имя: {name}\nВозраст: {age}\nПол: {gender}\n"
            "Режим: {mode}\nИнтересы: {interests}\n⭐ Рейтинг: {rating}"
        ),
        # Настройки — инлайн кнопки
        "settings_mode_label": "📌 Режим: {mode}",
        "settings_cross_kink": "Также принимать из Kink 🔥",
        "settings_cross_flirt": "Также принимать из Флирта 💋",
        "settings_simple_only": "🔒 Поиск только среди «Общение»",
        "settings_find_gender": "👤 Искать: {gender}",
        "settings_find_gender_premium": "👤 Искать: {gender} 🔒 Premium",
        "settings_show_badge": "Значок ⭐ в профиле",
        "settings_buy_premium": "💎 Купить Premium",
        "premium_active": "⭐ Premium активен",
        "settings_gender_any": "🔀 Все",
        "settings_gender_male": "👨 Парни",
        "settings_gender_female": "👩 Девушки",
        "settings_gender_other": "⚧ Другое",
        # Причины «недоступно»
        "reason_finish_form": "сначала заверши заполнение анкеты",
        "reason_enter_name": "сначала введи имя",
        "reason_enter_age": "сначала введи возраст",
        "reason_choose_gender": "сначала выбери пол",
        "reason_choose_mode": "сначала выбери режим",
        "reason_in_chat": "ты уже в чате",
        "reason_in_chat_stop": "ты в чате — нажми ❌ Стоп",
        "reason_finish_chat": "сначала выйди из чата",
        "reason_finish_action": "сначала заверши текущее действие",
        "reason_finish_anketa": "сначала заверши анкету",
        # Админ — кнопки действий над жалобой
        "adm_stopwords_yes": "⚠️ Стоп-слова: ДА",
        "adm_stopwords_no": "✅ Стоп-слова: НЕТ",
        "adm_show_log": "📄 Показать переписку",
        "adm_ban3": "🚫 Бан 3ч нарушителю",
        "adm_ban24": "🚫 Бан 24ч нарушителю",
        "adm_banperm": "🚫 Перм бан нарушителю",
        "adm_warn": "⚠️ Предупреждение нарушителю",
        "adm_warn_rep": "⚠️ Предупреждение жалобщику",
        "adm_ban_rep": "🚫 Бан жалобщику",
        "adm_shadow": "👻 Shadow ban нарушителю",
        "adm_dismiss": "✅ Отклонить жалобу",
        # Админ — кнопки действий над пользователем
        "adm_uban3": "🚫 Бан 3ч",
        "adm_uban24": "🚫 Бан 24ч",
        "adm_ubanperm": "🚫 Перм бан",
        "adm_unban": "✅ Разбан",
        "adm_shadow_remove": "👻 Снять shadow ban",
        "adm_shadow_set": "👻 Shadow ban",
        "adm_uwarn": "⚠️ Предупреждение",
        "adm_kick": "❌ Кик",
        "adm_give_premium": "⭐ Дать Premium 30д",
        "adm_take_premium": "⭐ Забрать Premium",
        "adm_fulldelete": "🗑 Полное удаление",
        # Интересы (для отображения кнопок)
        "int_talk": "Разговор по душам 🗣",
        "int_humor": "Юмор и мемы 😂",
        "int_advice": "Советы по жизни 💡",
        "int_music": "Музыка 🎵",
        "int_games": "Игры 🎮",
        "int_flirt_light": "Лёгкий флирт 😏",
        "int_compliments": "Комплименты 💌",
        "int_sexting": "Секстинг 🔥",
        "int_virtual_date": "Виртуальные свидания 💑",
        "int_flirt_games": "Флирт и игры 🎭",
        "int_bdsm": "BDSM 🖤",
        "int_bondage": "Bondage 🔗",
        "int_roleplay": "Roleplay 🎭",
        "int_domsub": "Dom/Sub ⛓",
        "int_petplay": "Pet play 🐾",
        "int_other_fetish": "Другой фетиш ✨",
        # Шутки по возрасту
        "age_joke_baby":    "🐥 Цыплёнок, тебе ещё в садик рано!",
        "age_joke_child":   "🎮 Эй малой, тут не мультики! Подрасти сначала.",
        "age_joke_teen_young": "🙅 Стоп! Тебе нет 16. Возвращайся когда подрастёшь!",
        "age_joke_teen":    "😄 О, молодёжь! Добро пожаловать, только не балуйся.",
        "age_joke_young":   "🔥 Самый сок! Добро пожаловать в MatchMe!",
        "age_joke_adult":   "😎 Взрослый человек, солидно!",
        "age_joke_middle":  "🧐 Опытный пользователь! Уважаем.",
        "age_joke_senior":  "💪 Ого, ещё в деле! Молодость в душе — главное.",
        "age_joke_elder":   "👴 Дедуля/бабуля освоили интернет! Снимаем шляпу.",
        "age_joke_ancient": "😂 Серьёзно?! Тебе домой надо, не в анонимный чат!",
        # Темы для разговора
        "chat_topics": [
            "Если бы ты мог жить в любом городе мира — где бы это было? 🌍",
            "Какой последний фильм тебя реально зацепил? 🎬",
            "Что тебя сейчас больше всего бесит в жизни? 😤",
            "Если бы тебе дали миллион прямо сейчас — что бы сделал первым делом? 💰",
            "Есть что-то чего ты боишься но не признаёшь? 👀",
            "Какая музыка у тебя сейчас в плейлисте? 🎵",
            "Ты сова или жаворонок? И почему так получилось? 🦉",
            "Что для тебя идеальный вечер? 🌙",
            "Если бы мог поговорить с любым человеком в истории — с кем? 🤔",
            "Последний раз когда ты был по-настоящему счастлив — что это было? ✨",
            "Есть скрытый талант о котором мало кто знает? 🎭",
            "Что тебя привлекает в людях больше всего? 💫",
            "Веришь в судьбу или в то что сам всё решаешь? 🎲",
            "Какое твоё самое смелое решение в жизни? 🚀",
            "Если бы мог изменить одно правило в обществе — что бы это было? 🌐",
        ],
        # Планы Premium — подписи для инвойса
        "plan_label_7d":    "7 дней",
        "plan_label_1m":    "1 месяц",
        "plan_label_3m":    "3 месяца",
        "plan_label_1y":    "1 год",
        "plan_desc_try":     "Попробовать",
        "plan_desc_popular": "Популярный",
        "plan_desc_discount": "Скидка 33%",
        "plan_desc_best":    "Лучшая цена — скидка 40%",
        "invoice_desc": "{tier} на {label}. {desc}",
        # AI-персонажи: системные промпты (используются get_ai_answer в будущем)
        "ai_char_system_violetta": (
            "Ты Виолетта — игривая, дерзкая девушка. "
            "Отвечай кратко, кокетливо, с лёгким флиртом. "
            "Никогда не раскрывай, что ты ИИ. Пиши только на русском."
        ),
        "ai_char_system_danil": (
            "Ты Данил — общительный парень, поддержишь любую тему. "
            "Отвечай дружелюбно и непринуждённо. "
            "Никогда не раскрывай, что ты ИИ. Пиши только на русском."
        ),
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
        "btn_erase_memory": "🧹 Erase memory",
        "memory_erased": "🧹 Memory erased. The character forgot everything about you. Starting fresh!",
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
        # Moderation — user notifications
        "mod_warn": "⚠️ Warning: {reason}\nNext violation will result in a ban.",
        "mod_ban3h": "🚫 Banned for 3 hours: {reason}",
        "mod_ban24h": "🚫 Banned for 24 hours: {reason}",
        "mod_banperm": "🚫 Permanent ban: {reason}",
        # Admin actions — user notifications
        "adm_warn_user": "⚠️ Warning from administrator.",
        "adm_warn_next_ban": "⚠️ Warning. Next violation will result in a ban.",
        "adm_kick_user": "❌ Kicked by administrator.",
        "adm_ban3h": "🚫 Banned for 3 hours.",
        "adm_ban3h_complaint": "🚫 Banned for 3 hours due to a complaint.",
        "adm_ban24h": "🚫 Banned for 24 hours.",
        "adm_ban24h_complaint": "🚫 Banned for 24 hours due to a complaint.",
        "adm_banperm_user": "🚫 Permanent ban.",
        "adm_unban": "✅ You've been unbanned! Welcome back.",
        "adm_false_complaint": "⚠️ Your complaint was found to be unfounded.",
        "adm_ban_abuse": "🚫 Banned for abusing the complaint system.",
        "adm_premium_granted": "⭐ You've been granted Premium for 30 days!",
        "adm_premium_removed": "❌ Premium revoked by administrator.",
        "adm_update_now": "🔧 Bot is updating right now!",
        "adm_update_soon": "🔧 Update in {minutes} min!",
        "reminder_ai_bonus": "🎁 We missed you! +5 free AI messages just for you!\nCome chat 💬",
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
        "premium_title": "⭐ MatchMe Premium\n\n{status}📊 What's included:\n• Unlimited all AI characters\n• VIP characters unlocked\n• Priority search\n• No ads\n\nChoose a plan:",
        "premium_status_eternal": "✅ Current: {tier} (lifetime)\n\n",
        "premium_status_until": "✅ Current: {tier} until {until}\n\n",
        "premium_info": (
            "📊 Premium subscription:\n\n"
            "⭐ What's included:\n"
            "• Unlimited all AI characters\n"
            "• VIP characters (Flirt, Kink) unlocked\n"
            "• Priority search\n"
            "• No ads\n\n"
            "💡 Tip: yearly plan is the best deal!"
        ),
        "premium_activated": "🎉 {tier} activated!\n\n📦 Plan: {label}\n📅 Until {until}\n\n{benefits}",
        "premium_unknown_plan": "Unknown plan",
        "benefit_premium": "Unlimited AI, VIP characters, priority, no ads!",
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
            "💬 Basic: 20 messages/day\n"
            "🔥 VIP: 10 messages/day\n"
            "🔥 VIP+: subscription only\n"
            "⭐ Subscription removes all limits\n\n"
            "Choose who you want to talk to:"
        ),
        "ai_select_char": "Choose a character:",
        "ai_char_not_found": "Character not found.",
        "ai_power_soon": "🔧 Coming soon! Stay tuned.",
        "ai_vip_required": "🔒 This character is available with VIP subscription only.",
        "ai_vip_plus_required": "🔒 This VIP+ character is available with Premium subscription only.",
        "ai_chat_active": "💬 AI chat active",
        "ai_char_entered": "👤 {name} has entered the chat\n\n{bio}",
        "ai_unlimited": "♾ Unlimited",
        "ai_limit_info": "💬 Limit: {limit} messages/day",
        "ai_ended": "✅ AI chat ended.",
        "ai_select_from_buttons": "👆 Choose a character from the buttons above.",
        "ai_limit_plus": "⏰ Limit reached ({limit} messages/day).\n\nResets in 24 hours. Meanwhile, chat with a real person!",
        "ai_limit_basic": "⏰ Limit reached ({limit} messages/day).\n\n⭐ Buy Premium — unlimited AI and VIP characters!",
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
        "ai_chatting_with": "✅ You are chatting with {name}\n{description}\n\n{limit_text}\n\nSay something!",
        "ai_greeting": "Greet the user and start a conversation. Short, 1-2 sentences in English.",
        "ai_buy_sub": "⭐ Buy subscription",
        "searching": "🔍 Searching...",
        # Character descriptions
        "char_danil_desc": "Sociable guy, will chat on any topic",
        "char_polina_desc": "Lively girl, ironic with a sense of humor",
        "char_max_desc": "Confident guy, here to flirt",
        "char_violetta_desc": "Playful girl, bold and flirtatious",
        "char_alisa_desc": "Obedient submissive, gentle and devoted",
        "char_dmitri_desc": "Experienced Dominant, strict and commanding",
        "char_rolemaster_desc": "Creates scenarios and plays any role",
        # Complaint buttons
        "rep_minor": "🔞 Minors",
        "rep_spam": "💰 Spam / Ads",
        "rep_abuse": "😡 Threats / Insults",
        "rep_nsfw": "🔞 Sexual without consent",
        "rep_other": "🔄 Other",
        "rep_cancel": "◀️ Cancel",
        # Edit profile buttons
        "edit_btn_name": "✏️ Name",
        "edit_btn_age": "🎂 Age",
        "edit_btn_gender": "⚧ Gender",
        "edit_btn_mode": "💬 Mode",
        "edit_btn_interests": "🎯 Interests",
        # AI characters — Block 1: Chat
        "char_luna": "🌙 Luna",
        "char_luna_desc": "Dreamy artist girl — warm and atmospheric",
        "char_max_simple": "🧢 Max",
        "char_max_simple_desc": "Simple IT guy — humor and no pretense",
        "char_aurora": "✨ Aurora — VIP",
        "char_aurora_desc": "Marketing director, 18 countries — elegance and sarcasm",
        "char_alex": "🔥 Alex — VIP",
        "char_alex_desc": "Freelancer and adventurer — philosophy and challenge",
        "char_aurora_locked": "🔒 Aurora — VIP",
        "char_alex_locked": "🔒 Alex — VIP",
        "char_coming_soon": "🔜 Kink — coming soon",
        # AI characters — Block 2: Flirt
        "char_mia": "🍭 Mia",
        "char_mia_desc": "Playful student — sweet and flirty",
        "char_kai": "🎧 Kai",
        "char_kai_desc": "DJ with charisma — confident flirt",
        "char_diana": "🏛️ Diana — VIP",
        "char_diana_desc": "Gallery curator — sensual and mysterious",
        "char_leon": "⌚ Leon — VIP",
        "char_leon_desc": "Architect — restrained fire and dominance",
        "char_diana_locked": "🔒 Diana — VIP",
        "char_leon_locked": "🔒 Leon — VIP",
        # AI characters — Block 3: Kink (all VIP)
        "char_lilit": "🖤 Lilit — VIP+",
        "char_lilit_desc": "Dominant girl — control and passion",
        "char_eva": "🌸 Eva — VIP+",
        "char_eva_desc": "Submissive girl — tender and obedient",
        "char_damir": "🎯 Damir — VIP+",
        "char_damir_desc": "Dominant guy — confident and commanding",
        "char_ars": "🐾 Ars — VIP+",
        "char_ars_desc": "Submissive guy — soft and yielding",
        "char_master": "🎭 Story Master — VIP+",
        "char_master_desc": "Scenario generator — any story on your request",
        "char_lilit_locked": "🔒 Lilit — VIP+",
        "char_eva_locked": "🔒 Eva — VIP+",
        "char_damir_locked": "🔒 Damir — VIP+",
        "char_ars_locked": "🔒 Ars — VIP+",
        "char_master_locked": "🔒 Story Master — VIP+",
        "char_power_soon": "🧠 Powerful AI (soon)",
        "char_vip_locked": "🔒 VIP+ only",
        "btn_ai_info": "📋 Character descriptions",
        # AI block headers
        "ai_block_simple": "💬 Chat",
        "ai_block_flirt": "💋 Flirt",
        "ai_block_kink": "🔥 Kink",
        # Premium buttons
        "prem_header": "── Premium ──",
        "prem_compare": "❓ What's included",
        "prem_7d": "⭐ 7 days — 198 Stars",
        "prem_1m": "⭐ 1 month — 598 Stars",
        "prem_3m": "⭐ 3 months — 1198 Stars",
        "prem_1y": "⭐ 1 year — 3598 Stars",
        "btn_continue": "❤️ Want to keep chatting",
        "btn_find_new": "🔍 Find someone new",
        "btn_to_menu": "🏠 To menu",
        # General — restart, chat
        "bot_restarted": "🔄 Bot updated. Your chat has been restored!",
        "chat_start": "✅ Start chatting!",
        "partner_found": (
            "👤 Partner found!{badge}\n"
            "Name: {name}\nAge: {age}\nGender: {gender}\n"
            "Mode: {mode}\nInterests: {interests}\n⭐ Rating: {rating}"
        ),
        # Settings — inline buttons
        "settings_mode_label": "📌 Mode: {mode}",
        "settings_cross_kink": "Also accept from Kink 🔥",
        "settings_cross_flirt": "Also accept from Flirt 💋",
        "settings_simple_only": "🔒 Search only in Chat mode",
        "settings_find_gender": "👤 Search: {gender}",
        "settings_find_gender_premium": "👤 Search: {gender} 🔒 Premium",
        "settings_show_badge": "Show ⭐ badge in profile",
        "settings_buy_premium": "💎 Buy Premium",
        "premium_active": "⭐ Premium active",
        "settings_gender_any": "🔀 Anyone",
        "settings_gender_male": "👨 Guys",
        "settings_gender_female": "👩 Girls",
        "settings_gender_other": "⚧ Other",
        # Unavailable reasons
        "reason_finish_form": "complete your profile first",
        "reason_enter_name": "enter your name first",
        "reason_enter_age": "enter your age first",
        "reason_choose_gender": "choose your gender first",
        "reason_choose_mode": "choose your mode first",
        "reason_in_chat": "you are already in a chat",
        "reason_in_chat_stop": "you are in a chat — press ❌ Stop",
        "reason_finish_chat": "leave the chat first",
        "reason_finish_action": "complete your current action first",
        "reason_finish_anketa": "complete your profile first",
        # Admin — complaint action buttons
        "adm_stopwords_yes": "⚠️ Stop-words: YES",
        "adm_stopwords_no": "✅ Stop-words: NO",
        "adm_show_log": "📄 Show chat log",
        "adm_ban3": "🚫 Ban 3h offender",
        "adm_ban24": "🚫 Ban 24h offender",
        "adm_banperm": "🚫 Perm ban offender",
        "adm_warn": "⚠️ Warn offender",
        "adm_warn_rep": "⚠️ Warn reporter",
        "adm_ban_rep": "🚫 Ban reporter",
        "adm_shadow": "👻 Shadow ban offender",
        "adm_dismiss": "✅ Dismiss complaint",
        # Admin — user action buttons
        "adm_uban3": "🚫 Ban 3h",
        "adm_uban24": "🚫 Ban 24h",
        "adm_ubanperm": "🚫 Perm ban",
        "adm_unban": "✅ Unban",
        "adm_shadow_remove": "👻 Remove shadow ban",
        "adm_shadow_set": "👻 Shadow ban",
        "adm_uwarn": "⚠️ Warning",
        "adm_kick": "❌ Kick",
        "adm_give_premium": "⭐ Give Premium 30d",
        "adm_take_premium": "⭐ Remove Premium",
        "adm_fulldelete": "🗑 Full delete",
        # Interests (button display)
        "int_talk": "Deep talk 🗣",
        "int_humor": "Humor & memes 😂",
        "int_advice": "Life advice 💡",
        "int_music": "Music 🎵",
        "int_games": "Games 🎮",
        "int_flirt_light": "Light flirt 😏",
        "int_compliments": "Compliments 💌",
        "int_sexting": "Sexting 🔥",
        "int_virtual_date": "Virtual dates 💑",
        "int_flirt_games": "Flirt & games 🎭",
        "int_bdsm": "BDSM 🖤",
        "int_bondage": "Bondage 🔗",
        "int_roleplay": "Roleplay 🎭",
        "int_domsub": "Dom/Sub ⛓",
        "int_petplay": "Pet play 🐾",
        "int_other_fetish": "Other fetish ✨",
        # Age jokes
        "age_joke_baby":    "🐥 Little chick, you're too young even for kindergarten!",
        "age_joke_child":   "🎮 Hey kid, this isn't cartoons! Grow up first.",
        "age_joke_teen_young": "🙅 Stop! You're under 16. Come back when you're older!",
        "age_joke_teen":    "😄 Oh, the youth! Welcome, just behave.",
        "age_joke_young":   "🔥 Prime time! Welcome to MatchMe!",
        "age_joke_adult":   "😎 Mature person — respect!",
        "age_joke_middle":  "🧐 Experienced user! Much appreciated.",
        "age_joke_senior":  "💪 Wow, still going! Young at heart — that's what matters.",
        "age_joke_elder":   "👴 Grandma/Grandpa mastered the internet! Hats off.",
        "age_joke_ancient": "😂 Seriously?! You should be home, not in an anonymous chat!",
        # Chat topics
        "chat_topics": [
            "If you could live in any city in the world — where would it be? 🌍",
            "What's the last movie that really got to you? 🎬",
            "What's annoying you the most in life right now? 😤",
            "If someone gave you a million right now — what would you do first? 💰",
            "Is there something you're afraid of but won't admit? 👀",
            "What's in your playlist these days? 🎵",
            "Night owl or early bird? And how did that happen? 🦉",
            "What does a perfect evening look like to you? 🌙",
            "If you could talk to anyone in history — who would it be? 🤔",
            "The last time you were truly happy — what was it? ✨",
            "Do you have a hidden talent that few people know about? 🎭",
            "What attracts you most in people? 💫",
            "Do you believe in fate or that you decide everything yourself? 🎲",
            "What's the boldest decision you've ever made? 🚀",
            "If you could change one rule in society — what would it be? 🌐",
        ],
        # Premium plan labels for invoices
        "plan_label_7d":    "7 days",
        "plan_label_1m":    "1 month",
        "plan_label_3m":    "3 months",
        "plan_label_1y":    "1 year",
        "plan_desc_try":     "Try it",
        "plan_desc_popular": "Popular",
        "plan_desc_discount": "33% off",
        "plan_desc_best":    "Best value — 40% off",
        "invoice_desc": "{tier} for {label}. {desc}",
        # AI characters: system prompts (used by get_ai_answer in the future)
        "ai_char_system_violetta": (
            "You are Violetta — a playful, bold girl. "
            "Reply briefly, flirtatiously. "
            "Never reveal you are an AI. Write only in English."
        ),
        "ai_char_system_danil": (
            "You are Danil — a friendly, sociable guy who talks about anything. "
            "Reply casually and warmly. "
            "Never reveal you are an AI. Write only in English."
        ),
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
        "btn_erase_memory": "🧹 Borrar memoria",
        "memory_erased": "🧹 Memoria borrada. El personaje olvidó todo sobre ti. ¡Empezamos de nuevo!",
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
        # Moderación — notificaciones al usuario
        "mod_warn": "⚠️ Advertencia: {reason}\nLa próxima infracción resultará en un ban.",
        "mod_ban3h": "🚫 Baneado por 3 horas: {reason}",
        "mod_ban24h": "🚫 Baneado por 24 horas: {reason}",
        "mod_banperm": "🚫 Ban permanente: {reason}",
        # Acciones administrativas — notificaciones al usuario
        "adm_warn_user": "⚠️ Advertencia del administrador.",
        "adm_warn_next_ban": "⚠️ Advertencia. La próxima infracción resultará en un ban.",
        "adm_kick_user": "❌ Expulsado por el administrador.",
        "adm_ban3h": "🚫 Ban de 3 horas.",
        "adm_ban3h_complaint": "🚫 Ban de 3 horas por un reporte.",
        "adm_ban24h": "🚫 Ban de 24 horas.",
        "adm_ban24h_complaint": "🚫 Ban de 24 horas por un reporte.",
        "adm_banperm_user": "🚫 Ban permanente.",
        "adm_unban": "✅ ¡Has sido desbaneado! Bienvenido de vuelta.",
        "adm_false_complaint": "⚠️ Tu reporte fue considerado infundado.",
        "adm_ban_abuse": "🚫 Ban por abuso del sistema de reportes.",
        "adm_premium_granted": "⭐ ¡Se te ha otorgado Premium por 30 días!",
        "adm_premium_removed": "❌ Premium revocado por el administrador.",
        "adm_update_now": "🔧 ¡El bot se está actualizando ahora mismo!",
        "adm_update_soon": "🔧 ¡Actualización en {minutes} min!",
        "reminder_ai_bonus": "🎁 ¡Te extrañamos! +5 mensajes IA gratis solo para ti!\nVen a chatear 💬",
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
        "premium_title": "⭐ MatchMe Premium\n\n{status}📊 Qué incluye:\n• IA ilimitada en todos los personajes\n• Personajes VIP desbloqueados\n• Búsqueda prioritaria\n• Sin anuncios\n\nElige un plan:",
        "premium_status_eternal": "✅ Actual: {tier} (de por vida)\n\n",
        "premium_status_until": "✅ Actual: {tier} hasta {until}\n\n",
        "premium_info": (
            "📊 Suscripción Premium:\n\n"
            "⭐ Qué incluye:\n"
            "• IA ilimitada en todos los personajes\n"
            "• Personajes VIP (Coqueteo, Kink) desbloqueados\n"
            "• Búsqueda prioritaria\n"
            "• Sin anuncios\n\n"
            "💡 Consejo: ¡el plan anual es la mejor opción!"
        ),
        "premium_activated": "🎉 ¡{tier} activado!\n\n📦 Plan: {label}\n📅 Hasta {until}\n\n{benefits}",
        "premium_unknown_plan": "Plan desconocido",
        "benefit_premium": "IA ilimitada, personajes VIP, prioridad, ¡sin anuncios!",
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
            "💬 Básico: 20 mensajes/día\n"
            "🔥 VIP: 10 mensajes/día\n"
            "🔥 VIP+: solo con suscripción\n"
            "⭐ La suscripción elimina todos los límites\n\n"
            "Elige con quién quieres hablar:"
        ),
        "ai_select_char": "Elige un personaje:",
        "ai_char_not_found": "Personaje no encontrado.",
        "ai_power_soon": "🔧 ¡Próximamente! Mantente al tanto.",
        "ai_vip_required": "🔒 Este personaje está disponible solo con suscripción VIP.",
        "ai_vip_plus_required": "🔒 Este personaje VIP+ está disponible solo con suscripción Premium.",
        "ai_chat_active": "💬 Chat IA activo",
        "ai_char_entered": "👤 {name} ha entrado al chat\n\n{bio}",
        "ai_unlimited": "♾ Ilimitado",
        "ai_limit_info": "💬 Límite: {limit} mensajes/día",
        "ai_ended": "✅ Chat IA terminado.",
        "ai_select_from_buttons": "👆 Elige un personaje con los botones de arriba.",
        "ai_limit_plus": "⏰ Límite alcanzado ({limit} mensajes/día).\n\nSe reinicia en 24 horas. ¡Mientras tanto, chatea con una persona real!",
        "ai_limit_basic": "⏰ Límite alcanzado ({limit} mensajes/día).\n\n⭐ ¡Compra Premium — IA ilimitada y personajes VIP!",
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
        "ai_chatting_with": "✅ Estás chateando con {name}\n{description}\n\n{limit_text}\n\n¡Di algo!",
        "ai_buy_sub": "⭐ Comprar suscripción",
        "searching": "🔍 Buscando...",
        # Descripciones de personajes
        "char_danil_desc": "Chico sociable, charla sobre cualquier tema",
        "char_polina_desc": "Chica animada, irónica y con sentido del humor",
        "char_max_desc": "Chico seguro, aquí para coquetear",
        "char_violetta_desc": "Chica juguetona, atrevida y coqueta",
        "char_alisa_desc": "Sumisa obediente, suave y devota",
        "char_dmitri_desc": "Dominante experimentado, estricto y autoritario",
        "char_rolemaster_desc": "Crea escenarios y juega cualquier rol",
        # Botones de reporte
        "rep_minor": "🔞 Menores",
        "rep_spam": "💰 Spam / Publicidad",
        "rep_abuse": "😡 Amenazas / Insultos",
        "rep_nsfw": "🔞 Sexual sin consentimiento",
        "rep_other": "🔄 Otro",
        "rep_cancel": "◀️ Cancelar",
        # Botones de edición de perfil
        "edit_btn_name": "✏️ Nombre",
        "edit_btn_age": "🎂 Edad",
        "edit_btn_gender": "⚧ Género",
        "edit_btn_mode": "💬 Modo",
        "edit_btn_interests": "🎯 Intereses",
        # Personajes IA — Bloque 1: Chat
        "char_luna": "🌙 Luna",
        "char_luna_desc": "Chica artista soñadora — cálida y atmosférica",
        "char_max_simple": "🧢 Max",
        "char_max_simple_desc": "Chico de IT sin pretensiones — humor y sinceridad",
        "char_aurora": "✨ Aurora — VIP",
        "char_aurora_desc": "Directora de marketing, 18 países — elegancia y sarcasmo",
        "char_alex": "🔥 Alex — VIP",
        "char_alex_desc": "Freelancer aventurero — filosofía y desafío",
        "char_aurora_locked": "🔒 Aurora — VIP",
        "char_alex_locked": "🔒 Alex — VIP",
        "char_coming_soon": "🔜 Kink — pronto",
        # Personajes IA — Bloque 2: Flirt
        "char_mia": "🍭 Mia",
        "char_mia_desc": "Estudiante juguetona — dulce y coqueta",
        "char_kai": "🎧 Kai",
        "char_kai_desc": "DJ carismático — coqueteo seguro",
        "char_diana": "🏛️ Diana — VIP",
        "char_diana_desc": "Curadora de galería — sensual y misteriosa",
        "char_leon": "⌚ León — VIP",
        "char_leon_desc": "Arquitecto — fuego contenido y dominancia",
        "char_diana_locked": "🔒 Diana — VIP",
        "char_leon_locked": "🔒 León — VIP",
        # Personajes IA — Bloque 3: Kink (todos VIP)
        "char_lilit": "🖤 Lilit — VIP+",
        "char_lilit_desc": "Chica dominante — control y pasión",
        "char_eva": "🌸 Eva — VIP+",
        "char_eva_desc": "Chica sumisa — tierna y obediente",
        "char_damir": "🎯 Damir — VIP+",
        "char_damir_desc": "Chico dominante — seguro y poderoso",
        "char_ars": "🐾 Ars — VIP+",
        "char_ars_desc": "Chico sumiso — suave y dócil",
        "char_master": "🎭 Maestro de historias — VIP+",
        "char_master_desc": "Generador de escenarios — cualquier historia a tu petición",
        "char_lilit_locked": "🔒 Lilit — VIP+",
        "char_eva_locked": "🔒 Eva — VIP+",
        "char_damir_locked": "🔒 Damir — VIP+",
        "char_ars_locked": "🔒 Ars — VIP+",
        "char_master_locked": "🔒 Maestro de historias — VIP+",
        "char_power_soon": "🧠 IA potente (pronto)",
        "char_vip_locked": "🔒 Solo VIP+",
        "btn_ai_info": "📋 Descripción de personajes",
        # Encabezados de bloques IA
        "ai_block_simple": "💬 Charla",
        "ai_block_flirt": "💋 Coqueteo",
        "ai_block_kink": "🔥 Kink",
        # Botones Premium
        "prem_header": "── Premium ──",
        "prem_compare": "❓ Qué incluye",
        "prem_7d": "⭐ 7 días — 198 Stars",
        "prem_1m": "⭐ 1 mes — 598 Stars",
        "prem_3m": "⭐ 3 meses — 1198 Stars",
        "prem_1y": "⭐ 1 año — 3598 Stars",
        "btn_continue": "❤️ Quiero seguir chateando",
        "btn_find_new": "🔍 Buscar a alguien nuevo",
        "btn_to_menu": "🏠 Al menú",
        # General — reinicio, chat
        "bot_restarted": "🔄 Bot actualizado. ¡Tu chat ha sido restaurado!",
        "chat_start": "✅ ¡Empieza a chatear!",
        "partner_found": (
            "👤 ¡Compañero encontrado!{badge}\n"
            "Nombre: {name}\nEdad: {age}\nGénero: {gender}\n"
            "Modo: {mode}\nIntereses: {interests}\n⭐ Puntuación: {rating}"
        ),
        # Ajustes — botones inline
        "settings_mode_label": "📌 Modo: {mode}",
        "settings_cross_kink": "También aceptar de Kink 🔥",
        "settings_cross_flirt": "También aceptar de Coqueteo 💋",
        "settings_simple_only": "🔒 Buscar solo en modo Charla",
        "settings_find_gender": "👤 Buscar: {gender}",
        "settings_find_gender_premium": "👤 Buscar: {gender} 🔒 Premium",
        "settings_show_badge": "Mostrar insignia ⭐ en perfil",
        "settings_buy_premium": "💎 Comprar Premium",
        "premium_active": "⭐ Premium activo",
        "settings_gender_any": "🔀 Cualquiera",
        "settings_gender_male": "👨 Chicos",
        "settings_gender_female": "👩 Chicas",
        "settings_gender_other": "⚧ Otro",
        # Razones «no disponible»
        "reason_finish_form": "completa tu perfil primero",
        "reason_enter_name": "ingresa tu nombre primero",
        "reason_enter_age": "ingresa tu edad primero",
        "reason_choose_gender": "elige tu género primero",
        "reason_choose_mode": "elige tu modo primero",
        "reason_in_chat": "ya estás en un chat",
        "reason_in_chat_stop": "estás en un chat — presiona ❌ Stop",
        "reason_finish_chat": "sal del chat primero",
        "reason_finish_action": "completa tu acción actual primero",
        "reason_finish_anketa": "completa tu perfil primero",
        # Admin — botones de queja
        "adm_stopwords_yes": "⚠️ Stop-words: SÍ",
        "adm_stopwords_no": "✅ Stop-words: NO",
        "adm_show_log": "📄 Mostrar chat",
        "adm_ban3": "🚫 Ban 3h al infractor",
        "adm_ban24": "🚫 Ban 24h al infractor",
        "adm_banperm": "🚫 Ban permanente al infractor",
        "adm_warn": "⚠️ Advertencia al infractor",
        "adm_warn_rep": "⚠️ Advertencia al denunciante",
        "adm_ban_rep": "🚫 Ban al denunciante",
        "adm_shadow": "👻 Shadow ban al infractor",
        "adm_dismiss": "✅ Rechazar queja",
        # Admin — botones de acción de usuario
        "adm_uban3": "🚫 Ban 3h",
        "adm_uban24": "🚫 Ban 24h",
        "adm_ubanperm": "🚫 Ban permanente",
        "adm_unban": "✅ Desbanear",
        "adm_shadow_remove": "👻 Quitar shadow ban",
        "adm_shadow_set": "👻 Shadow ban",
        "adm_uwarn": "⚠️ Advertencia",
        "adm_kick": "❌ Expulsar",
        "adm_give_premium": "⭐ Dar Premium 30d",
        "adm_take_premium": "⭐ Quitar Premium",
        "adm_fulldelete": "🗑 Eliminar completamente",
        # Intereses (texto de botones)
        "int_talk": "Charla profunda 🗣",
        "int_humor": "Humor y memes 😂",
        "int_advice": "Consejos de vida 💡",
        "int_music": "Música 🎵",
        "int_games": "Juegos 🎮",
        "int_flirt_light": "Coqueteo suave 😏",
        "int_compliments": "Cumplidos 💌",
        "int_sexting": "Sexting 🔥",
        "int_virtual_date": "Citas virtuales 💑",
        "int_flirt_games": "Coqueteo y juegos 🎭",
        "int_bdsm": "BDSM 🖤",
        "int_bondage": "Bondage 🔗",
        "int_roleplay": "Roleplay 🎭",
        "int_domsub": "Dom/Sub ⛓",
        "int_petplay": "Pet play 🐾",
        "int_other_fetish": "Otro fetiche ✨",
        # Chistes por edad
        "age_joke_baby":    "🐥 Pollito, ¡todavía eres demasiado pequeño para el jardín!",
        "age_joke_child":   "🎮 Eh, chico, ¡esto no son dibujos animados! Crece primero.",
        "age_joke_teen_young": "🙅 ¡Para! Tienes menos de 16. ¡Vuelve cuando seas mayor!",
        "age_joke_teen":    "😄 ¡La juventud! Bienvenido, solo pórtate bien.",
        "age_joke_young":   "🔥 ¡En la flor de la vida! ¡Bienvenido a MatchMe!",
        "age_joke_adult":   "😎 ¡Persona madura — respeto!",
        "age_joke_middle":  "🧐 ¡Usuario experimentado! Muy apreciado.",
        "age_joke_senior":  "💪 ¡Wow, todavía activo! Joven de corazón — eso es lo que importa.",
        "age_joke_elder":   "👴 ¡Abuela/Abuelo domina internet! Chapeau.",
        "age_joke_ancient": "😂 ¿En serio?! Deberías estar en casa, ¡no en un chat anónimo!",
        # Temas de conversación
        "chat_topics": [
            "Si pudieras vivir en cualquier ciudad del mundo, ¿dónde sería? 🌍",
            "¿Cuál es la última película que de verdad te llegó? 🎬",
            "¿Qué es lo que más te molesta de la vida ahora mismo? 😤",
            "Si alguien te diera un millón ahora mismo, ¿qué harías primero? 💰",
            "¿Hay algo que te da miedo pero no admites? 👀",
            "¿Qué tienes en tu lista de reproducción últimamente? 🎵",
            "¿Eres noctámbulo o madrugador? ¿Y cómo pasó eso? 🦉",
            "¿Cómo es una tarde perfecta para ti? 🌙",
            "Si pudieras hablar con alguien de la historia, ¿quién sería? 🤔",
            "¿La última vez que fuiste verdaderamente feliz, qué fue? ✨",
            "¿Tienes un talento oculto que poca gente conoce? 🎭",
            "¿Qué te atrae más de las personas? 💫",
            "¿Crees en el destino o en que tú decides todo? 🎲",
            "¿Cuál es la decisión más audaz que has tomado? 🚀",
            "Si pudieras cambiar una regla de la sociedad, ¿cuál sería? 🌐",
        ],
        # Etiquetas de planes Premium para facturas
        "plan_label_7d":    "7 días",
        "plan_label_1m":    "1 mes",
        "plan_label_3m":    "3 meses",
        "plan_label_1y":    "1 año",
        "plan_desc_try":     "Pruébalo",
        "plan_desc_popular": "Popular",
        "plan_desc_discount": "33% de descuento",
        "plan_desc_best":    "Mejor precio — 40% de descuento",
        "invoice_desc": "{tier} por {label}. {desc}",
        # Personajes IA: prompts de sistema (usados por get_ai_answer en el futuro)
        "ai_char_system_violetta": (
            "Eres Violetta — una chica juguetona y atrevida. "
            "Responde brevemente y coquetamente. "
            "Nunca reveles que eres una IA. Escribe solo en español."
        ),
        "ai_char_system_danil": (
            "Eres Danil — un chico sociable que habla de cualquier tema. "
            "Responde de forma amigable y natural. "
            "Nunca reveles que eres una IA. Escribe solo en español."
        ),
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
