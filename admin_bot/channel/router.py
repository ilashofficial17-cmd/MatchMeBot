"""
Admin Bot — хэндлеры канала + главное меню навигации.
Reply keyboard навигация: главное меню → разделы → действия.
"""

import logging
import aiohttp
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from admin_bot.config import (
    ADMIN_ID, ANTHROPIC_API_KEY, VENICE_API_KEY, CHANNEL_ID, BOT_USERNAME,
    OPEN_ROUTER_KEY, OPEN_ROUTER_URL, CHANNEL_AI_MODEL,
)
import admin_bot.db as _db
from admin_bot.db import get_stat, set_stat
from admin_bot.channel.content import CHANNEL_GENERATORS, generate_poll
from admin_bot.channel.scheduler import last_channel_post
from admin_bot.keyboards import kb_main_menu, kb_admin, kb_channel, kb_analytics, kb_marketing, kb_support_user
from locales import t

logger = logging.getLogger("admin-bot")

router = Router()

# Кэш превью постов: msg_id -> (rubric, text, poll_data)
channel_preview_cache = {}


def kb_post_types():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика дня", callback_data="chpost:daily_stats")],
        [InlineKeyboardButton(text="🔥 Пик активности", callback_data="chpost:peak_hour")],
        [InlineKeyboardButton(text="💡 Совет по общению", callback_data="chpost:dating_tip")],
        [InlineKeyboardButton(text="😂 Шутка / мем", callback_data="chpost:joke")],
        [InlineKeyboardButton(text="📋 Опрос", callback_data="chpost:poll")],
        [InlineKeyboardButton(text="📈 Итоги недели", callback_data="chpost:weekly_recap")],
    ])


# ====================== /start ======================
@router.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state=None):
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            t("ru", "admin_main_menu"),
            reply_markup=kb_main_menu()
        )
    else:
        # Саппорт-меню для обычных юзеров
        from admin_bot.support.router import _get_user_lang
        lang = await _get_user_lang(message.from_user.id)
        await message.answer(
            t(lang, "support_welcome"),
            reply_markup=kb_support_user(lang)
        )


# ====================== ГЛАВНОЕ МЕНЮ (reply buttons) ======================
@router.message(F.text == "🛡 Админка")
async def nav_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(t("ru", "admin_section_admin"), reply_markup=kb_admin())


@router.message(F.text == "📢 Канал")
async def nav_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(t("ru", "admin_section_channel"), reply_markup=kb_channel())


@router.message(F.text == "📊 Аналитика")
async def nav_analytics(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(t("ru", "admin_section_analytics"), reply_markup=kb_analytics())


@router.message(F.text == "🎯 Маркетинг")
async def nav_marketing(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(t("ru", "admin_section_marketing"), reply_markup=kb_marketing())


@router.message(F.text == "⬅️ Назад")
async def nav_back(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(t("ru", "admin_main_menu"), reply_markup=kb_main_menu())


# ====================== КАНАЛ: reply buttons ======================
@router.message(F.text == "📝 Создать пост")
async def btn_post(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📢 Выбери тип поста:", reply_markup=kb_post_types())


@router.message(F.text == "⚡ Авто-постинг")
async def btn_toggle(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = await get_stat("channel_poster_enabled", 1)
    new_val = 0 if current else 1
    await set_stat("channel_poster_enabled", new_val)
    status = "✅ ВКЛ" if new_val else "❌ ВЫКЛ"
    await message.answer(f"📢 Авто-постинг: {status}")


@router.message(F.text == "📅 Расписание")
async def btn_schedule(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    enabled = await get_stat("channel_poster_enabled", 1)
    status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
    await message.answer(
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


@router.message(F.text == "🔌 Статус API")
async def btn_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await check_api_status(message)


@router.message(F.text == "📢 Канал стат")
async def btn_channel_stats(message: types.Message):
    """Кнопка аналитики канала из раздела Аналитика."""
    if message.from_user.id != ADMIN_ID:
        return
    await show_channel_stats(message)


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
async def _check_openrouter(model: str, label: str) -> str:
    """Check a single OpenRouter model."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPEN_ROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPEN_ROUTER_KEY or ''}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://t.me/MatchMeBot",
                },
                json={"model": model, "max_tokens": 10,
                      "messages": [{"role": "user", "content": "Hi"}]},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    return f"🟢 OpenRouter ({label}: {model}) — активен ✅"
                elif resp.status == 401:
                    return f"🔴 OpenRouter ({label}) — неверный ключ ❌"
                elif resp.status == 402:
                    return f"🔴 OpenRouter ({label}) — нет средств 💰"
                elif resp.status == 429:
                    return f"🟡 OpenRouter ({label}) — лимит (но работает)"
                else:
                    return f"🟡 OpenRouter ({label}) — ошибка {resp.status}"
    except Exception as e:
        return f"🔴 OpenRouter ({label}) — недоступен ({e})"


async def check_api_status(message: types.Message):
    await message.answer("⏳ Проверяю API...")
    results = []

    # 1. OpenRouter — channel model (Gemini Flash)
    results.append(await _check_openrouter(CHANNEL_AI_MODEL, "channel"))

    # 2. OpenRouter — chat model (gpt-4o-mini)
    results.append(await _check_openrouter("openai/gpt-4o-mini", "chat"))

    # 3. Venice API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.venice.ai/api/v1/models",
                headers={"Authorization": f"Bearer {VENICE_API_KEY or ''}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    balance_usd = resp.headers.get("x-venice-balance-usd", "?")
                    results.append(f"🟢 Venice API — активен ✅ (баланс: ${balance_usd})")
                elif resp.status == 401:
                    results.append("🔴 Venice API — неверный ключ ❌")
                else:
                    results.append(f"🟡 Venice API — ошибка {resp.status}")
    except Exception as e:
        results.append(f"🔴 Venice API — недоступен ({e})")

    # 4. Redis
    import os
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(redis_url, decode_responses=True)
            await r.ping()
            db_size = await r.dbsize()
            await r.aclose()
            results.append(f"🟢 Redis — подключён ✅ (ключей: {db_size})")
        except Exception as e:
            results.append(f"🔴 Redis — недоступен ({e})")
    else:
        results.append("⚪ Redis — REDIS_URL не задан")

    # 5. PostgreSQL
    try:
        async with _db.db_pool.acquire() as conn:
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        results.append(f"🟢 PostgreSQL — подключён ✅ (юзеров: {user_count})")
    except Exception:
        results.append("🔴 PostgreSQL — недоступна ❌")

    await message.answer("🔌 Статус сервисов\n\n" + "\n".join(results))


async def show_channel_stats(message: types.Message):
    try:
        async with _db.db_pool.acquire() as conn:
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


# ====================== КОМАНДЫ (legacy, чтобы /post /toggle /status /stats /schedule продолжали работать) ======================
@router.message(Command("post"))
async def cmd_post(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📢 Выбери тип поста:", reply_markup=kb_post_types())


@router.message(Command("toggle"))
async def cmd_toggle(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = await get_stat("channel_poster_enabled", 1)
    new_val = 0 if current else 1
    await set_stat("channel_poster_enabled", new_val)
    status = "✅ ВКЛ" if new_val else "❌ ВЫКЛ"
    await message.answer(f"📢 Авто-постинг: {status}")


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await check_api_status(message)


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await show_channel_stats(message)


@router.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await btn_schedule(message)


# ====================== INLINE CALLBACKS ======================
@router.callback_query(F.data.startswith("chpost:"))
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


@router.callback_query(F.data.startswith("chsend:"))
async def admin_channel_send(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    cached = channel_preview_cache.pop(callback.message.message_id, None)
    if not cached:
        await callback.answer("Контент устарел, сгенерируй заново.", show_alert=True)
        return
    rubric, text, poll_data = cached
    try:
        from admin_bot.main import admin_bot
        if poll_data:
            question, options = poll_data
            await admin_bot.send_poll(CHANNEL_ID, question=question, options=options, is_anonymous=True)
        else:
            await admin_bot.send_message(CHANNEL_ID, text)
        last_channel_post[rubric] = datetime.now()
        try:
            await callback.message.edit_text(f"✅ Опубликовано в {CHANNEL_ID}!")
        except Exception:
            pass
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка отправки: {e}")
    await callback.answer()


@router.callback_query(F.data == "chdismiss")
async def admin_channel_dismiss(callback: types.CallbackQuery):
    channel_preview_cache.pop(callback.message.message_id, None)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()
