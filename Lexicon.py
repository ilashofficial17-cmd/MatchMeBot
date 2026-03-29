# lexicon.py

LEXICON = {
    'ru': {
        # Меню и Старт
        'welcome': "Добро пожаловать в MatchMe! ❤️\nНайди свою идеальную пару или начни анонимный чат прямо сейчас.",
        'select_lang': "Пожалуйста, выбери язык общения:",
        'main_menu': "🏠 Главное меню",
        'btn_find_match': "🚀 Найти пару",
        'btn_anon_chat': "👤 Анонимный чат",
        'btn_profile': "📝 Мой профиль",
        'btn_settings': "⚙️ Настройки",
        'btn_premium': "💎 Premium",
        
        # Режимы поиска
        'mode_selection': "Выбери режим общения:",
        'mode_simple': "Обычный 🕊️ (Общение)",
        'mode_flirt': "Флирт 😏 (Легкий подкат)",
        'mode_kink': "Kink 🔥 (Без цензуры)",
        
        # Персонажи (AI)
        'ai_typing': "Печатает...",
        'ai_voice_msg': "🎤 Голосовое сообщение",
        'ai_photo_msg': "📸 Фотография",
        'error_no_stars': "❌ Недостаточно звезд (Stars) для этого действия.",
        
        # Админка и Модерация
        'admin_panel': "🛠 Панель администратора",
        'report_reason': "Выберите причину жалобы:",
        'report_scam': "Мошенничество",
        'report_spam': "Спам",
        'report_insult': "Оскорбление",
        'report_ad': "Реклама/Эскорт",
        'report_sent': "✅ Жалоба отправлена модераторам.",
        
        # Очередь и Поиск
        'searching': "🔍 Ищу подходящего собеседника...",
        'match_found': "✅ Пара найдена! Можете начинать общение.",
        'stop_chat': "❌ Собеседник покинул чат.",
        'chat_stopped': "Вы вышли из чата.",
        
        # Состояние системы
        'maintenance': "⚠️ Технические работы. Попробуйте позже.",
        'db_error': "Ошибка базы данных. Мы уже чиним!",
    },
    
    'en': {
        # Menu & Start
        'welcome': "Welcome to MatchMe! ❤️\nFind your perfect match or start an anonymous chat right now.",
        'select_lang': "Please, choose your language:",
        'main_menu': "🏠 Main Menu",
        'btn_find_match': "🚀 Find a Match",
        'btn_anon_chat': "👤 Anon Chat",
        'btn_profile': "📝 My Profile",
        'btn_settings': "⚙️ Settings",
        'btn_premium': "💎 Premium",
        
        # Search Modes
        'mode_selection': "Choose communication mode:",
        'mode_simple': "Simple 🕊️ (Chatting)",
        'mode_flirt': "Flirt 😏 (Light flirting)",
        'mode_kink': "Kink 🔥 (Uncensored)",
        
        # AI Characters
        'ai_typing': "Is typing...",
        'ai_voice_msg': "🎤 Voice message",
        'ai_photo_msg': "📸 Photo",
        'error_no_stars': "❌ Not enough Stars for this action.",
        
        # Admin & Moderation
        'admin_panel': "🛠 Admin Panel",
        'report_reason': "Select reason for report:",
        'report_scam': "Scam",
        'report_spam': "Spam",
        'report_insult': "Insult",
        'report_ad': "Ad/Escort",
        'report_sent': "✅ Report sent to moderators.",
        
        # Queue & Search
        'searching': "🔍 Looking for a match...",
        'match_found': "✅ Match found! You can start chatting.",
        'stop_chat': "❌ Partner left the chat.",
        'chat_stopped': "You left the chat.",
        
        # System status
        'maintenance': "⚠️ Maintenance in progress. Try again later.",
        'db_error': "Database error. We are fixing it!",
    },
    
    'es': {
        # Menú y Inicio
        'welcome': "¡Bienvenido a MatchMe! ❤️\nEncuentra tu pareja ideal o inicia un chat anónimo ahora mismo.",
        'select_lang': "Por favor, elige tu idioma:",
        'main_menu': "🏠 Menú principal",
        'btn_find_match': "🚀 Buscar pareja",
        'btn_anon_chat': "👤 Chat anónimo",
        'btn_profile': "📝 Mi perfil",
        'btn_settings': "⚙️ Ajustes",
        'btn_premium': "💎 Premium",
        
        # Modos de búsqueda
        'mode_selection': "Elige el modo de comunicación:",
        'mode_simple': "Simple 🕊️ (Conversación)",
        'mode_flirt': "Flirteo 😏 (Seducción ligera)",
        'mode_kink': "Kink 🔥 (Sin censura)",
        
        # Personajes AI
        'ai_typing': "Está escribiendo...",
        'ai_voice_msg': "🎤 Mensaje de voz",
        'ai_photo_msg': "📸 Foto",
        'error_no_stars': "❌ No hay suficientes Estrellas para esta acción.",
        
        # Administración y Moderación
        'admin_panel': "🛠 Panel de administración",
        'report_reason': "Seleccione el motivo del reporte:",
        'report_scam': "Fraude",
        'report_spam': "Spam",
        'report_insult': "Insulto",
        'report_ad': "Publicidad/Escort",
        'report_sent': "✅ Reporte enviado a los moderadores.",
        
        # Cola y Búsqueda
        'searching': "🔍 Buscando una pareja adecuada...",
        'match_found': "✅ ¡Pareja encontrada! Pueden empezar a chatear.",
        'stop_chat': "❌ El compañero abandonó el chat.",
        'chat_stopped': "Has salido del chat.",
        
        # Estado del sistema
        'maintenance': "⚠️ Mantenimiento técnico. Inténtelo más tarde.",
        'db_error': "Error de base de datos. ¡Lo estamos arreglando!",
    }
}

def get_text(key, lang='ru'):
    """Получить текст по ключу и языку"""
    # Если язык не передан или его нет в словаре, используем ru
    if lang not in LEXICON:
        lang = 'ru'
    return LEXICON[lang].get(key, LEXICON['ru'].get(key, f"Error: {key} not found"))
