"""
Admin Bot — генераторы контента для канала @MATCHMEHUB.
Персона канала: «ироничный друг» — дерзкий, самоироничный, свой.
"""

import random
import logging
import aiohttp

from admin_bot.config import (
    OPEN_ROUTER_KEY, OPEN_ROUTER_URL, CHANNEL_AI_MODEL,
    CHANNEL_STYLE_PROMPT, BOT_USERNAME,
    MODE_NAMES, MILESTONE_THRESHOLDS, POLL_BANK, ADMIN_ID,
)
import admin_bot.db as _db
from admin_bot.db import get_stat, set_stat

logger = logging.getLogger("admin-bot")

# Состояние milestone (восстанавливается из БД в scheduler)
last_milestone_threshold = 0


# ====================== OPENROUTER API ======================

async def ask_claude_channel(system_prompt: str, user_prompt: str) -> str:
    """Отправляет запрос к OpenRouter (Gemini Flash) для генерации контента канала."""
    if not OPEN_ROUTER_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPEN_ROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPEN_ROUTER_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://t.me/MatchMeBot",
                },
                json={
                    "model": CHANNEL_AI_MODEL,
                    "max_tokens": 300,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.warning(f"OpenRouter channel error: status={resp.status}")
                    if resp.status in (401, 402, 429):
                        try:
                            from admin_bot.main import admin_bot
                            await admin_bot.send_message(
                                ADMIN_ID,
                                f"⚠\ufe0f OpenRouter channel ошибка {resp.status}!\n"
                                f"AI-контент канала временно недоступен."
                            )
                        except Exception:
                            pass
    except Exception as e:
        logger.error(f"OpenRouter channel error: {e}")
    return None


# ====================== КАТЕГОРИИ ДЛЯ РАНДОМИЗАЦИИ ======================

TIP_CATEGORIES = [
    "первое сообщение и как зацепить",
    "как поддержать разговор когда он затухает",
    "как флиртовать в текстовом чате",
    "как понять что человеку интересно",
    "как красиво завершить разговор если не зашло",
    "как быть интересным собеседником",
    "ошибки которые все делают в анонимных чатах",
    "как перейти от small talk к чему-то глубокому",
    "как реагировать на неловкие моменты",
    "как не быть кринжовым",
]

JOKE_STYLES = [
    "ироничное наблюдение про анонимные чаты — как пост в твиттере, 1-2 строки",
    "мини-диалог из анонимного чата который пошёл не так (2-4 реплики), смешной и узнаваемый",
    "сравнение: 'анонимный чат — это как...' — неожиданное и точное, одно предложение",
    "внутренний монолог человека в анонимном чате — 2-3 строки, с самоиронией",
]

STORY_ANGLES = [
    "история где оба стеснялись, но потом разговорились и не могли остановиться",
    "история где первое сообщение было странным, но разговор оказался лучшим за неделю",
    "история где человек зашёл на 5 минут — а проговорил 3 часа",
    "история про неловкий момент который наоборот сблизил",
    "история где люди нашли неожиданное совпадение",
    "история где кто-то решился на флирт впервые — и получилось",
]

HOT_TAKE_TOPICS = [
    "'привет как дела' — это не плохое начало. Плохое начало — молчать потому что боишься показаться банальным",
    "флиртовать в текстовом чате сложнее чем вживую. Нет интонации, нет глаз. Только слова. И это делает это честнее",
    "самые интересные разговоры в анонимных чатах — между 23:00 и 3:00. Ночью люди перестают строить из себя",
    "анонимность не делает людей хуже. Она просто снимает маски. И иногда под маской — кто-то очень классный",
    "лучший комплимент в чате — не про внешность. А когда говорят 'с тобой прикольно общаться'",
    "не надо бояться молчания в чате. Иногда пауза — это не 'ему неинтересно', а 'он думает что написать чтобы было идеально'",
    "режим kink — не про пошлость. Это про доверие. Про то чтобы сказать вслух то что обычно стесняешься",
    "люди которые пишут длинные сообщения — недооценены. Это значит им реально не всё равно",
]

NIGHT_VIBES = [
    "ночной вайб — когда не можешь уснуть и хочется поговорить с кем-то незнакомым. Без масок, без ожиданий",
    "3 ночи. Город спит. А ты лежишь с телефоном и думаешь: может написать кому-нибудь? Может стоит",
    "ночью разговоры другие. Честнее. Глубже. Может потому что темнота даёт смелость",
    "если не спится — не листай ленту. Лучше поговори с живым человеком. Даже анонимно — это теплее",
    "знаешь это чувство когда в 2 ночи находишь человека и болтаешь до рассвета? Вот за этим сюда и заходят",
    "ночь — единственное время когда люди перестают притворяться. В анонимном чате это особенно заметно",
]


# ====================== ГЕНЕРАТОРЫ КОНТЕНТА ======================

async def generate_dating_tip():
    category = random.choice(TIP_CATEGORIES)
    style = random.choice([
        f"Тема: {category}. Короткий конкретный совет + пример как НЕ надо и как надо. "
        f"Максимум 350 символов.",
        f"Тема: {category}. Одна мысль-инсайт про общение, как будто только что осенило. "
        f"Без нумерации. Максимум 300 символов.",
        f"Тема: {category}. Антисовет: начни с 'плохого совета' (ироничного), потом дай настоящий. "
        f"Максимум 350 символов.",
    ])
    text = await ask_claude_channel(CHANNEL_STYLE_PROMPT, style)
    if text:
        return text
    tips = [
        f"Не начинай с «привет, как дела». Задай вопрос, на который интересно ответить.\n\n@{BOT_USERNAME}",
        f"Первое впечатление — это первые 3 сообщения. Не трать их на «м/ж?»\n\n@{BOT_USERNAME}",
        f"Юмор работает лучше комплиментов. Рассмеши — и разговор пойдёт сам.\n\n@{BOT_USERNAME}",
    ]
    return random.choice(tips)


async def generate_joke():
    style = random.choice(JOKE_STYLES)
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        f"Формат: {style}. Тема: анонимные чаты и онлайн-знакомства. "
        f"Пиши как будто это твой личный пост, а не 'шутка для канала'. Максимум 250 символов."
    )
    if text:
        return text
    jokes = [
        f"Анонимный чат — единственное место, где «расскажи о себе» звучит как квест 🎮\n\n@{BOT_USERNAME}",
        f"Когда написал «привет» и ждёшь ответ как результат экзамена 😅\n\n@{BOT_USERNAME}",
        f"В анонимном чате каждый разговор — как первое свидание. Только без кофе ☕\n\n@{BOT_USERNAME}",
    ]
    return random.choice(jokes)


async def generate_chat_story():
    angle = random.choice(STORY_ANGLES)
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        f"Напиши мини-историю из анонимного чата MatchMe (выдуманную но реалистичную). "
        f"Угол: {angle}. "
        f"Формат: 3-5 строк нарратива, как короткий пост в соцсети. "
        f"Без диалогов в кавычках, без имён. Как будто рассказываешь другу случай. "
        f"Максимум 400 символов."
    )
    if text:
        return text
    return (
        f"Вчера один зашёл на 5 минут перед сном. "
        f"Проговорил 3 часа. Забыл поставить будильник. "
        f"Говорит — стоило того 😄\n\n@{BOT_USERNAME}"
    )


async def generate_would_you():
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        "Придумай ситуацию из анонимного чата и спроси 'а что бы ты ответил/сделал?'. "
        "Формат: описание ситуации в 2-3 строки + вопрос к читателю. "
        "Ситуация должна быть узнаваемой, немного неловкой или провокационной. "
        "Максимум 350 символов."
    )
    if text:
        return text
    return (
        f"Собеседник молчит уже 5 минут после твоего сообщения. "
        f"Ты: а) напишешь ещё раз б) будешь ждать в) уйдёшь "
        f"г) отправишь мем?\n\n@{BOT_USERNAME}"
    )


async def generate_hot_take():
    topic = random.choice(HOT_TAKE_TOPICS)
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        f"Напиши короткий пост-мнение на тему: {topic}. "
        f"Формат: 2-4 строки, уверенно и с характером. Не как совет — как мысль вслух. "
        f"Можно спорно — пусть хочется согласиться или поспорить. Максимум 350 символов."
    )
    if text:
        return text
    return (
        f"Анонимность не делает людей хуже. "
        f"Она просто снимает маски. И иногда под маской — кто-то очень классный\n\n"
        f"@{BOT_USERNAME}"
    )


async def generate_night_vibe():
    vibe = random.choice(NIGHT_VIBES)
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        f"Напиши короткий атмосферный ночной пост для канала. "
        f"Настроение: {vibe}. "
        f"Тон: тёплый, немного интимный, без кринжа. Как мысль перед сном. "
        f"2-3 строки. Максимум 250 символов."
    )
    if text:
        return text
    return (
        f"Не спится? Ты не один такой. "
        f"Иногда лучший разговор — тот что случился в 3 ночи с незнакомцем\n\n"
        f"@{BOT_USERNAME}"
    )


async def generate_daily_stats():
    try:
        async with _db.db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_today = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '24 hours'")
            active = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            genders = await conn.fetch(
                "SELECT gender, COUNT(*) as cnt FROM users WHERE gender IS NOT NULL GROUP BY gender")
            modes = await conn.fetch(
                "SELECT mode, COUNT(*) as cnt FROM users WHERE mode IS NOT NULL "
                "GROUP BY mode ORDER BY cnt DESC")
            premiums = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
        g_map = {"male": "парней", "female": "девушек", "other": "other"}
        g_parts = [f"{r['cnt']} {g_map.get(r['gender'], r['gender'])}" for r in genders]
        m_parts = [f"{MODE_NAMES.get(r['mode'], r['mode'])}: {r['cnt']}" for r in modes]
        online = await get_stat("online_pairs", 0)
        searching = await get_stat("searching_count", 0)
        raw_data = (
            f"Всего юзеров: {total}, новых за 24ч: {new_today}, активных: {active}, "
            f"сейчас в чатах: {online} пар, ищут: {searching}, premium: {premiums}, "
            f"пол: {', '.join(g_parts)}, режимы: {', '.join(m_parts)}"
        )
        angle = random.choice([
            "Подай через один неожиданный факт из данных + ироничный комментарий.",
            "Сравни с чем-нибудь из жизни (кинотеатр, вечеринка, метро в час пик).",
            "Выдели один показатель и обыграй его с юмором, остальные фоном.",
        ])
        styled = await ask_claude_channel(
            CHANNEL_STYLE_PROMPT,
            f"Пост со статистикой MatchMe за день. Данные: {raw_data}. "
            f"{angle} Максимум 400 символов."
        )
        if styled:
            return styled
        return (
            f"Нас уже {total} 👥\n"
            f"+{new_today} новых за сегодня, {active} активных\n"
            f"Прямо сейчас: {online} пар в чатах, {searching} ищут\n\n"
            f"@{BOT_USERNAME}"
        )
    except Exception as e:
        logger.error(f"generate_daily_stats error: {e}")
        return None


async def generate_peak_hour():
    online = await get_stat("online_pairs", 0)
    searching = await get_stat("searching_count", 0)
    if online + searching < 1:
        return None
    styled = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        f"Сейчас в MatchMe {online} пар общаются, {searching} ищут. "
        f"Напиши 2-3 строки — зацепи, но без 'скорее заходи'. "
        f"Как будто между делом упоминаешь что сейчас движ. Максимум 200 символов."
    )
    if styled:
        return styled
    return (
        f"{online} пар сейчас болтают, {searching} ждут собеседника\n"
        f"Самое время зайти 👉 @{BOT_USERNAME}"
    )


async def generate_milestone():
    global last_milestone_threshold
    try:
        async with _db.db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
        current = 0
        for t in MILESTONE_THRESHOLDS:
            if total >= t:
                current = t
        if current > last_milestone_threshold and last_milestone_threshold > 0:
            last_milestone_threshold = current
            await set_stat("last_milestone_threshold", current)
            styled = await ask_claude_channel(
                CHANNEL_STYLE_PROMPT,
                f"MatchMe достиг {current} пользователей (сейчас {total}). "
                f"Короткий искренний пост. Не 'спасибо что вы с нами' — "
                f"а как будто сам удивлён и рад. 2-3 строки. Максимум 250 символов."
            )
            if styled:
                return styled
            return (
                f"Нас уже {current}+ \u2764\ufe0f\n"
                f"Спасибо, что вы с нами\n\n"
                f"@{BOT_USERNAME}"
            )
        last_milestone_threshold = current
    except Exception as e:
        logger.error(f"generate_milestone error: {e}")
    return None


async def generate_weekly_recap():
    try:
        async with _db.db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_week = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'")
            active_week = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '7 days'")
            ages = await conn.fetch("""
                SELECT CASE WHEN age BETWEEN 16 AND 19 THEN '16-19'
                            WHEN age BETWEEN 20 AND 25 THEN '20-25'
                            WHEN age BETWEEN 26 AND 35 THEN '26-35'
                            ELSE '36+' END as bracket, COUNT(*) as cnt
                FROM users WHERE age IS NOT NULL GROUP BY bracket ORDER BY bracket
            """)
            top_mode = await conn.fetchrow(
                "SELECT mode, COUNT(*) as cnt FROM users WHERE mode IS NOT NULL "
                "GROUP BY mode ORDER BY cnt DESC LIMIT 1")
        age_parts = [f"{r['bracket']}: {r['cnt']}" for r in ages]
        mode_text = MODE_NAMES.get(top_mode['mode'], '?') if top_mode else "\u2014"
        raw_data = (
            f"Всего: {total}, новых за неделю: {new_week}, активных за неделю: {active_week}, "
            f"топ режим: {mode_text}, возрасты: {', '.join(age_parts)}"
        )
        angle = random.choice([
            "Как итоги матча: кто выиграл эту неделю, какой рекорд побит.",
            "Выдели один интересный тренд из данных и обыграй с иронией.",
            "Коротко и с характером, как сторис после выходных.",
        ])
        styled = await ask_claude_channel(
            CHANNEL_STYLE_PROMPT,
            f"Итоги недели MatchMe. Данные: {raw_data}. "
            f"{angle} Максимум 400 символов."
        )
        if styled:
            return styled
        return (
            f"Итоги недели\n\n"
            f"Всего: {total}, новых: +{new_week}\n"
            f"Активных: {active_week}, топ режим: {mode_text}\n\n"
            f"@{BOT_USERNAME}"
        )
    except Exception as e:
        logger.error(f"generate_weekly_recap error: {e}")
        return None


async def generate_poll():
    return random.choice(POLL_BANK)


# ====================== РЕЕСТР ГЕНЕРАТОРОВ ======================

CHANNEL_GENERATORS = {
    "daily_stats": generate_daily_stats,
    "peak_hour": generate_peak_hour,
    "dating_tip": generate_dating_tip,
    "joke": generate_joke,
    "chat_story": generate_chat_story,
    "would_you": generate_would_you,
    "hot_take": generate_hot_take,
    "night_vibe": generate_night_vibe,
    "weekly_recap": generate_weekly_recap,
}
