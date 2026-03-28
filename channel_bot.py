"""
MatchMe Channel Manager Bot
Управление каналом @MATCHMEHUB: авто-постинг, контент через Claude AI, админка.
Работает как отдельный сервис, подключён к общей PostgreSQL базе.
"""

import asyncio
import os
import aiohttp
import random
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
)
import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("matchme-channel")

# ====================== КОНФИГ ======================
CHANNEL_BOT_TOKEN = os.environ.get("CHANNEL_BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "590443268"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
VENICE_API_KEY = os.environ.get("VENICE_API_KEY")
CHANNEL_ID = "@MATCHMEHUB"
BOT_USERNAME = "MyMatchMeBot"  # username основного бота для CTA-ссылок

bot = Bot(token=CHANNEL_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db_pool = None

# Состояние
channel_poster_enabled = True  # переопределяется из bot_stats при старте
last_channel_post = {}
last_milestone_threshold = 0
channel_preview_cache = {}  # msg_id -> (rubric, text, poll_data)

# ====================== КОНСТАНТЫ ======================
MODE_NAMES = {"simple": "Просто общение 💬", "flirt": "Флирт 💋", "kink": "Kink 🔥"}

CHANNEL_STYLE_PROMPT = (
    "Ты SMM-менеджер телеграм-канала MatchMe — анонимного чат-бота для знакомств. "
    "Пишешь как живой человек, НЕ как бот. ТОЛЬКО на русском.\n\n"
    "СТИЛЬ:\n"
    "- Короткие предложения. Максимум 3-4 строки основного текста\n"
    "- Один пост = одна мысль. Не перегружай информацией\n"
    "- Эмодзи уместно, но не больше 3-4 на весь пост\n"
    "- Пиши так, будто рассказываешь другу — живо, без канцелярита\n"
    "- НЕ используй: разделители (──, ✦, ┌, └), хештеги, длинные списки\n"
    "- В конце одна строка с ботом: @MyMatchMeBot\n\n"
    "ЗАПРЕЩЕНО:\n"
    "- Посты длиннее 500 символов\n"
    "- Шаблонные фразы: 'а ты знал что', 'лайфхак', 'топ-5'\n"
    "- Перечисления больше 3 пунктов\n"
    "- Восклицательные знаки подряд (!!!)"
)

CHANNEL_SCHEDULE = {
    12: ["dating_tip"],
    13: ["peak_hour"],
    15: ["joke"],
    18: ["poll"],
    19: ["weekly_recap"],
    20: ["peak_hour"],
    21: ["daily_stats"],
}

MILESTONE_THRESHOLDS = [50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]

POLL_BANK = [
    ("Что главное в первом сообщении?", ["Юмор 😄", "Комплимент 💐", "Вопрос ❓", "Просто 'Привет' 👋"]),
    ("Идеальное первое свидание?", ["Кофейня ☕", "Кино 🎬", "Прогулка 🚶", "Онлайн 💻"]),
    ("Сколько сообщений нужно чтобы понять — твой человек или нет?", ["1-5", "5-15", "15-50", "50+"]),
    ("Что бесит в анонимных чатах?", ["Молчание 🤐", "Грубость 😤", "Спам 📢", "Скука 😴"]),
    ("В какое время ты заходишь?", ["Утром ☀️", "Днём 🌤", "Вечером 🌙", "Ночью 🌚"]),
    ("Ты больше слушатель или рассказчик?", ["Слушатель 👂", "Рассказчик 🗣", "50/50 ⚖️"]),
    ("Что привлекает в собеседнике?", ["Юмор 😂", "Ум 🧠", "Голос 🎙", "Дерзость 😈"]),
    ("Какой режим тебе ближе?", ["Просто общение 💬", "Флирт 💋", "Kink 🔥", "Все по настроению 🎲"]),
]

# ====================== БАЗА ДАННЫХ ======================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Инициализация значений
        for k, v in [("online_pairs", 0), ("searching_count", 0),
                      ("channel_poster_enabled", 1), ("last_milestone_threshold", 0)]:
            await conn.execute(
                "INSERT INTO bot_stats (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", k, v
            )

async def get_stat(key, default=0):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM bot_stats WHERE key=$1", key)
        return row["value"] if row else default

async def set_stat(key, value):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bot_stats (key, value, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value=$2, updated_at=NOW()", key, value
        )

# ====================== CLAUDE API ======================
async def ask_claude_channel(system_prompt: str, user_prompt: str) -> str:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 300,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"]
                else:
                    logger.warning(f"Claude API error: status={resp.status}")
                    if resp.status in (401, 402, 429):
                        try:
                            await bot.send_message(ADMIN_ID,
                                f"⚠️ Claude API ошибка {resp.status}!\n"
                                f"{'Нет денег на балансе' if resp.status == 402 else 'Проблема с ключом' if resp.status == 401 else 'Превышен лимит запросов'}\n"
                                f"AI-контент канала временно недоступен.")
                        except Exception:
                            pass
    except Exception as e:
        logger.error(f"Claude API error: {e}")
    return None

# ====================== ГЕНЕРАТОРЫ КОНТЕНТА ======================
async def generate_daily_stats():
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '24 hours'")
            active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            genders = await conn.fetch("SELECT gender, COUNT(*) as cnt FROM users WHERE gender IS NOT NULL GROUP BY gender")
            modes = await conn.fetch("SELECT mode, COUNT(*) as cnt FROM users WHERE mode IS NOT NULL GROUP BY mode ORDER BY cnt DESC")
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
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
        styled = await ask_claude_channel(
            CHANNEL_STYLE_PROMPT,
            f"Напиши короткий пост со статистикой MatchMe за день. "
            f"Данные: {raw_data}. "
            f"Выдели 2-3 самых интересных факта. Максимум 400 символов."
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
        f"Сейчас в MatchMe {online} пар общаются, {searching} ищут собеседника. "
        f"Напиши 2-3 строки — зацепи, чтобы захотелось зайти. Максимум 200 символов."
    )
    if styled:
        return styled
    return (
        f"{online} пар сейчас болтают, {searching} ждут собеседника\n"
        f"Самое время зайти 👉 @{BOT_USERNAME}"
    )

async def generate_dating_tip():
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        "Один короткий совет про общение в анонимных чатах. "
        "Конкретный, полезный, без воды. Максимум 3 строки текста + пример. Максимум 350 символов."
    )
    return text

async def generate_joke():
    text = await ask_claude_channel(
        CHANNEL_STYLE_PROMPT,
        "Короткая шутка или ироничное наблюдение про онлайн-знакомства и анонимные чаты. "
        "Формат: 1-3 строки, как пост друга в соцсети. Без натужного юмора. Максимум 250 символов."
    )
    return text

async def generate_poll():
    return random.choice(POLL_BANK)

async def generate_milestone():
    global last_milestone_threshold
    try:
        async with db_pool.acquire() as conn:
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
                f"Напиши короткий искренний пост-благодарность. 2-3 строки, без пафоса. Максимум 250 символов."
            )
            if styled:
                return styled
            return (
                f"Нас уже {current}+ ❤️\n"
                f"Спасибо, что вы с нами\n\n"
                f"@{BOT_USERNAME}"
            )
        last_milestone_threshold = current
    except Exception as e:
        logger.error(f"generate_milestone error: {e}")
    return None

async def generate_weekly_recap():
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'")
            active_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '7 days'")
            ages = await conn.fetch("""
                SELECT CASE WHEN age BETWEEN 16 AND 19 THEN '16-19'
                            WHEN age BETWEEN 20 AND 25 THEN '20-25'
                            WHEN age BETWEEN 26 AND 35 THEN '26-35'
                            ELSE '36+' END as bracket, COUNT(*) as cnt
                FROM users WHERE age IS NOT NULL GROUP BY bracket ORDER BY bracket
            """)
            top_mode = await conn.fetchrow("SELECT mode, COUNT(*) as cnt FROM users WHERE mode IS NOT NULL GROUP BY mode ORDER BY cnt DESC LIMIT 1")
        age_parts = [f"{r['bracket']}: {r['cnt']}" for r in ages]
        mode_text = MODE_NAMES.get(top_mode['mode'], '?') if top_mode else "—"
        raw_data = (
            f"Всего: {total}, новых за неделю: {new_week}, активных за неделю: {active_week}, "
            f"топ режим: {mode_text}, возрасты: {', '.join(age_parts)}"
        )
        styled = await ask_claude_channel(
            CHANNEL_STYLE_PROMPT,
            f"Итоги недели MatchMe. Данные: {raw_data}. "
            f"Выдели 2-3 ключевых момента, добавь короткий вывод. Максимум 400 символов."
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

CHANNEL_GENERATORS = {
    "daily_stats": generate_daily_stats,
    "peak_hour": generate_peak_hour,
    "dating_tip": generate_dating_tip,
    "joke": generate_joke,
    "weekly_recap": generate_weekly_recap,
}

# ====================== АВТО-ПОСТИНГ ======================
async def channel_poster():
    global last_milestone_threshold
    await asyncio.sleep(30)
    # Восстанавливаем состояние из БД
    try:
        last_milestone_threshold = await get_stat("last_milestone_threshold", 0)
        if last_milestone_threshold == 0:
            async with db_pool.acquire() as conn:
                total = await conn.fetchval("SELECT COUNT(*) FROM users")
            for t in MILESTONE_THRESHOLDS:
                if total >= t:
                    last_milestone_threshold = t
            await set_stat("last_milestone_threshold", last_milestone_threshold)
    except Exception:
        pass
    logger.info("Channel poster запущен")

    while True:
        await asyncio.sleep(600)

        # Проверяем включён ли постинг (из БД — персистентно)
        enabled = await get_stat("channel_poster_enabled", 1)
        if not enabled:
            continue

        now = datetime.now()
        hour = now.hour

        rubrics = CHANNEL_SCHEDULE.get(hour, [])
        for rubric in rubrics:
            last = last_channel_post.get(rubric)
            if last and (now - last).total_seconds() < 3600:
                continue
            if rubric == "poll" and now.day % 2 != 0:
                continue
            if rubric == "weekly_recap" and now.weekday() != 6:
                continue
            try:
                if rubric == "poll":
                    question, options = await generate_poll()
                    await bot.send_poll(CHANNEL_ID, question=question, options=options, is_anonymous=True)
                    last_channel_post[rubric] = now
                    logger.info(f"Channel poll posted: {question}")
                elif rubric in CHANNEL_GENERATORS:
                    text = await CHANNEL_GENERATORS[rubric]()
                    if text:
                        await bot.send_message(CHANNEL_ID, text)
                        last_channel_post[rubric] = now
                        logger.info(f"Channel post [{rubric}] sent")
            except Exception as e:
                logger.error(f"Channel poster error [{rubric}]: {e}")

        # Milestone
        try:
            milestone_text = await generate_milestone()
            if milestone_text:
                await bot.send_message(CHANNEL_ID, milestone_text)
                logger.info("Channel milestone posted")
        except Exception as e:
            logger.error(f"Channel milestone error: {e}")

# ====================== КОМАНДЫ БОТА ======================
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="post", description="Создать пост"),
        BotCommand(command="toggle", description="ВКЛ/ВЫКЛ авто-постинг"),
        BotCommand(command="status", description="Статус API"),
        BotCommand(command="stats", description="Статистика канала"),
        BotCommand(command="schedule", description="Расписание постов"),
    ])

# ====================== КЛАВИАТУРА АДМИНА ======================
def kb_admin():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Создать пост"), KeyboardButton(text="📢 Авто-постинг")],
        [KeyboardButton(text="🔌 Статус API"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📅 Расписание")],
    ], resize_keyboard=True)

def kb_post_types():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика дня", callback_data="chpost:daily_stats")],
        [InlineKeyboardButton(text="🔥 Пик активности", callback_data="chpost:peak_hour")],
        [InlineKeyboardButton(text="💡 Совет по общению", callback_data="chpost:dating_tip")],
        [InlineKeyboardButton(text="😂 Шутка / мем", callback_data="chpost:joke")],
        [InlineKeyboardButton(text="📋 Опрос", callback_data="chpost:poll")],
        [InlineKeyboardButton(text="📈 Итоги недели", callback_data="chpost:weekly_recap")],
    ])

# ====================== ОБРАБОТЧИКИ КОМАНД ======================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        enabled = await get_stat("channel_poster_enabled", 1)
        status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
        await message.answer(
            f"📢 MatchMe Channel Manager\n\n"
            f"Канал: {CHANNEL_ID}\n"
            f"Авто-постинг: {status}\n\n"
            f"Используй кнопки ниже или команды из меню.",
            reply_markup=kb_admin()
        )
    else:
        await message.answer(
            f"Этот бот управляет каналом {CHANNEL_ID}.\n"
            f"Для знакомств: @{BOT_USERNAME}",
            reply_markup=ReplyKeyboardRemove()
        )

@dp.message(Command("post"))
async def cmd_post(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📢 Выбери тип поста:", reply_markup=kb_post_types())

@dp.message(Command("toggle"))
async def cmd_toggle(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = await get_stat("channel_poster_enabled", 1)
    new_val = 0 if current else 1
    await set_stat("channel_poster_enabled", new_val)
    status = "✅ ВКЛ" if new_val else "❌ ВЫКЛ"
    await message.answer(f"📢 Авто-постинг: {status}")

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await check_api_status(message)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await show_channel_stats(message)

@dp.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    enabled = await get_stat("channel_poster_enabled", 1)
    status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
    schedule_text = (
        f"📅 Расписание авто-постинга ({status})\n\n"
        f"12:00 — 💡 Совет по общению\n"
        f"13:00 — 🔥 Пик активности\n"
        f"15:00 — 😂 Шутка / мем\n"
        f"18:00 — 📋 Опрос (через день)\n"
        f"19:00 — 📈 Итоги недели (воскресенье)\n"
        f"20:00 — 🔥 Пик активности\n"
        f"21:00 — 📊 Статистика дня\n\n"
        f"Milestone — при достижении порогов юзеров"
    )
    await message.answer(schedule_text)

# ====================== КНОПКИ REPLY ======================
@dp.message(F.text == "📝 Создать пост")
async def btn_post(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📢 Выбери тип поста:", reply_markup=kb_post_types())

@dp.message(F.text == "📢 Авто-постинг")
async def btn_toggle(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = await get_stat("channel_poster_enabled", 1)
    new_val = 0 if current else 1
    await set_stat("channel_poster_enabled", new_val)
    status = "✅ ВКЛ" if new_val else "❌ ВЫКЛ"
    await message.answer(f"📢 Авто-постинг: {status}")

@dp.message(F.text == "🔌 Статус API")
async def btn_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await check_api_status(message)

@dp.message(F.text == "📊 Статистика")
async def btn_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await show_channel_stats(message)

@dp.message(F.text == "📅 Расписание")
async def btn_schedule(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await cmd_schedule(message)

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
async def check_api_status(message: types.Message):
    await message.answer("⏳ Проверяю API...")
    results = []
    # Claude API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY or "",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 10,
                      "messages": [{"role": "user", "content": "Hi"}]},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    results.append("🟢 Claude API — активен ✅")
                elif resp.status == 401:
                    results.append("🔴 Claude API — неверный ключ ❌")
                elif resp.status == 402:
                    results.append("🔴 Claude API — нет средств 💰")
                elif resp.status == 429:
                    results.append("🟡 Claude API — лимит (но работает)")
                else:
                    results.append(f"🟡 Claude API — ошибка {resp.status}")
    except Exception as e:
        results.append(f"🔴 Claude API — недоступен ({e})")
    # Venice API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.venice.ai/api/v1/models",
                headers={"Authorization": f"Bearer {VENICE_API_KEY or ''}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    balance_usd = resp.headers.get("x-venice-balance-usd", "?")
                    results.append(f"🟢 Venice API — активен ✅\n   💰 Баланс: ${balance_usd}")
                elif resp.status == 401:
                    results.append("🔴 Venice API — неверный ключ ❌")
                else:
                    results.append(f"🟡 Venice API — ошибка {resp.status}")
    except Exception as e:
        results.append(f"🔴 Venice API — недоступен ({e})")
    # PostgreSQL
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        results.append("🟢 PostgreSQL — активна ✅")
    except Exception:
        results.append("🔴 PostgreSQL — недоступна ❌")
    await message.answer("🔌 Статус сервисов\n\n" + "\n".join(results))

async def show_channel_stats(message: types.Message):
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '24 hours'")
            active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen > NOW() - INTERVAL '24 hours'")
            premiums = await conn.fetchval("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL")
        online = await get_stat("online_pairs", 0)
        searching = await get_stat("searching_count", 0)
        enabled = await get_stat("channel_poster_enabled", 1)
        poster_status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
        await message.answer(
            f"📊 Статистика MatchMe\n\n"
            f"👥 Всего: {total}\n"
            f"🆕 Новых за 24ч: +{new_today}\n"
            f"🟢 Активных: {active}\n"
            f"💬 В чатах: {online} пар\n"
            f"🔍 Ищут: {searching}\n"
            f"⭐ Premium: {premiums}\n\n"
            f"📢 Авто-постинг: {poster_status}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ====================== INLINE CALLBACK ======================
@dp.callback_query(F.data.startswith("chpost:"))
async def admin_channel_post(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rubric = callback.data.split(":", 1)[1]
    await callback.message.answer("⏳ Генерирую...")
    try:
        text = None
        poll_data = None
        if rubric == "poll":
            poll_data = await generate_poll()
            question, options = poll_data
            text = f"📋 Опрос: {question}\n" + "\n".join(f"  • {o}" for o in options)
        elif rubric in CHANNEL_GENERATORS:
            text = await CHANNEL_GENERATORS[rubric]()
        if not text:
            await callback.message.answer("❌ Не удалось сгенерировать контент.")
            await callback.answer()
            return
        preview_msg = await callback.message.answer(
            f"👁 Предпросмотр:\n\n{text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Отправить в канал", callback_data=f"chsend:{rubric}")],
                [InlineKeyboardButton(text="🔄 Другой вариант", callback_data=f"chpost:{rubric}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="chdismiss")],
            ])
        )
        channel_preview_cache[preview_msg.message_id] = (rubric, text, poll_data)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")
    await callback.answer()

@dp.callback_query(F.data.startswith("chsend:"))
async def admin_channel_send(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    cached = channel_preview_cache.pop(callback.message.message_id, None)
    if not cached:
        await callback.answer("Контент устарел, сгенерируй заново.", show_alert=True)
        return
    rubric, text, poll_data = cached
    try:
        if poll_data:
            question, options = poll_data
            await bot.send_poll(CHANNEL_ID, question=question, options=options, is_anonymous=True)
        else:
            await bot.send_message(CHANNEL_ID, text)
        last_channel_post[rubric] = datetime.now()
        try:
            await callback.message.edit_text(f"✅ Опубликовано в {CHANNEL_ID}!")
        except Exception:
            pass
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка отправки: {e}")
    await callback.answer()

@dp.callback_query(F.data == "chdismiss")
async def admin_channel_dismiss(callback: types.CallbackQuery):
    channel_preview_cache.pop(callback.message.message_id, None)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# ====================== ЗАПУСК ======================
async def main():
    await init_db()
    await set_commands()
    asyncio.create_task(channel_poster())
    logger.info("MatchMe Channel Manager запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
