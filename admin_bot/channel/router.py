"""
Admin Bot — хэндлеры канала + главное меню навигации.
Reply keyboard навигация: главное меню → разделы → действия.
Модерация постов: approve / regen / edit / dismiss.
"""

import logging
import aiohttp
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from admin_bot.config import (
    ADMIN_ID, ANTHROPIC_API_KEY, VENICE_API_KEY, CHANNEL_ID, BOT_USERNAME,
    OPEN_ROUTER_KEY, OPEN_ROUTER_URL, CHANNEL_AI_MODEL, RUBRIC_MODE,
)
import admin_bot.db as _db
from admin_bot.db import get_stat, set_stat, get_rubric_mode, set_rubric_mode
from admin_bot.channel.content import CHANNEL_GENERATORS, generate_poll, generate_image
from admin_bot.channel.scheduler import (
    last_channel_post, pending_posts, create_pending_post,
    RUBRIC_EMOJI, MAX_REGEN_ATTEMPTS, _moderation_kb,
)
from admin_bot.keyboards import kb_main_menu, kb_admin, kb_channel, kb_analytics, kb_marketing, kb_support_user
from locales import t

logger = logging.getLogger("admin-bot")

router = Router()

# Кэш превью постов (ручной постинг): msg_id -> (rubric, text, poll_data)
channel_preview_cache = {}


# ====================== FSM ======================
class ChannelPostEdit(StatesGroup):
    waiting_text = State()


def kb_post_types():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика дня", callback_data="chpost:daily_stats")],
        [InlineKeyboardButton(text="💬 Истории чатов", callback_data="chpost:chat_story")],
        [InlineKeyboardButton(text="🤔 А ты бы?", callback_data="chpost:would_you")],
        [InlineKeyboardButton(text="💡 Совет по общению", callback_data="chpost:dating_tip")],
        [InlineKeyboardButton(text="😂 Шутка / мем", callback_data="chpost:joke")],
        [InlineKeyboardButton(text="📋 Опрос", callback_data="chpost:poll")],
        [InlineKeyboardButton(text="📈 Итоги недели", callback_data="chpost:weekly_recap")],
        [InlineKeyboardButton(text="🔥 Hot take", callback_data="chpost:hot_take")],
        [InlineKeyboardButton(text="🌙 Ночной вайб", callback_data="chpost:night_vibe")],
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
        f"14:00 — 💬 История из чатов\n"
        f"16:00 — 🤔 А ты бы?\n"
        f"18:00 — 📋 Опрос (через день)\n"
        f"19:00 — 📈 Итоги недели (воскресенье)\n"
        f"20:00 — 🔥 Hot take\n"
        f"21:00 — 📊 Статистика дня\n"
        f"23:00 — 🌙 Ночной вайб\n\n"
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


# ====================== МОДЕРАЦИЯ: reply buttons ======================
@router.message(F.text == "🔔 Режимы рубрик")
async def btn_rubric_modes(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    buttons = []
    for rubric in RUBRIC_MODE:
        mode = await get_rubric_mode(rubric)
        emoji = RUBRIC_EMOJI.get(rubric, "📝")
        mode_label = "🤖 АВТО" if mode == "auto" else "👁 МОДЕР"
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {rubric} — {mode_label}",
            callback_data=f"chmod:mode:{rubric}",
        )])
    await message.answer(
        "🔔 Режимы публикации\n\nНажми на рубрику чтобы переключить режим:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(F.text == "📋 Очередь")
async def btn_queue(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not pending_posts:
        await message.answer("Очередь пуста — все посты опубликованы ✅")
        return
    now = datetime.now()
    lines = [f"📋 На модерации: {len(pending_posts)} пост(ов)\n"]
    buttons = []
    for i, (pid, post) in enumerate(pending_posts.items(), 1):
        emoji = RUBRIC_EMOJI.get(post["rubric"], "📝")
        age = int((now - post["created_at"]).total_seconds() / 60)
        time_str = post["created_at"].strftime("%H:%M")
        lines.append(f"{i}. {emoji} {post['rubric']} — {time_str} ({age} мин назад)")
        buttons.append([InlineKeyboardButton(
            text=f"Открыть #{i} ({post['rubric']})",
            callback_data=f"chmod:open:{pid}",
        )])
    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None,
    )


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


# ====================== КОМАНДЫ (legacy) ======================
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


# ====================== INLINE CALLBACKS: ручной постинг ======================
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


# ====================== INLINE CALLBACKS: модерация ======================
@router.callback_query(F.data.startswith("chmod:approve:"))
async def chmod_approve(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    post_id = int(callback.data.split(":")[2])
    post = pending_posts.pop(post_id, None)
    if not post:
        await callback.answer("Пост не найден или уже обработан.", show_alert=True)
        return

    from admin_bot.main import admin_bot
    rubric = post["rubric"]
    try:
        if post["poll_data"]:
            question, options = post["poll_data"]
            await admin_bot.send_poll(CHANNEL_ID, question=question, options=options, is_anonymous=True)
        else:
            image_bytes = await generate_image(rubric, post["text"])
            if image_bytes:
                from aiogram.types import BufferedInputFile
                photo = BufferedInputFile(image_bytes, filename=f"{rubric}.png")
                await admin_bot.send_photo(CHANNEL_ID, photo=photo, caption=post["text"])
            else:
                await admin_bot.send_message(CHANNEL_ID, post["text"])
        last_channel_post[rubric] = datetime.now()
        try:
            await callback.message.edit_text(f"✅ Опубликовано в {CHANNEL_ID}! [{rubric}]")
        except Exception:
            pass
        logger.info(f"Moderated post #{post_id} [{rubric}] approved and published")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка отправки: {e}")
        # Вернуть пост обратно в очередь
        pending_posts[post_id] = post
    await callback.answer()


@router.callback_query(F.data.startswith("chmod:regen:"))
async def chmod_regen(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    post_id = int(callback.data.split(":")[2])
    post = pending_posts.get(post_id)
    if not post:
        await callback.answer("Пост не найден.", show_alert=True)
        return
    if post["attempts"] >= MAX_REGEN_ATTEMPTS:
        await callback.answer(
            f"Лимит перегенераций ({MAX_REGEN_ATTEMPTS}). Отредактируй вручную или отклони.",
            show_alert=True,
        )
        return

    rubric = post["rubric"]
    await callback.answer("⏳ Генерирую новый вариант...")
    try:
        if rubric == "poll":
            poll_data = await generate_poll()
            question, options = poll_data
            new_text = f"📋 Опрос: {question}\n" + "\n".join(f"  • {o}" for o in options)
            post["poll_data"] = poll_data
        elif rubric in CHANNEL_GENERATORS:
            new_text = await CHANNEL_GENERATORS[rubric]()
        else:
            await callback.message.answer("❌ Генератор не найден.")
            return

        if not new_text:
            await callback.message.answer("❌ Не удалось сгенерировать.")
            return

        post["text"] = new_text
        post["attempts"] += 1
        emoji = RUBRIC_EMOJI.get(rubric, "📝")
        time_str = post["created_at"].strftime("%H:%M")

        preview_text = (
            f"📋 Пост на модерации (вариант #{post['attempts']})\n\n"
            f"Рубрика: {emoji} {rubric}\n"
            f"Время: {time_str}\n\n"
            f"{'─' * 20}\n"
            f"{new_text}\n"
            f"{'─' * 20}"
        )
        try:
            await callback.message.edit_text(
                preview_text,
                reply_markup=_moderation_kb(post_id),
            )
        except Exception:
            pass
        logger.info(f"Moderated post #{post_id} [{rubric}] regenerated (attempt {post['attempts']})")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации: {e}")


@router.callback_query(F.data.startswith("chmod:edit:"))
async def chmod_edit(callback: types.CallbackQuery, state):
    if callback.from_user.id != ADMIN_ID:
        return
    post_id = int(callback.data.split(":")[2])
    post = pending_posts.get(post_id)
    if not post:
        await callback.answer("Пост не найден.", show_alert=True)
        return
    await state.update_data(editing_post_id=post_id)
    await state.set_state(ChannelPostEdit.waiting_text)
    await callback.message.answer(
        f"✏️ Отправь новый текст поста (или /cancel для отмены)\n\n"
        f"Текущий текст:\n{post['text']}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chmod:dismiss:"))
async def chmod_dismiss(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    post_id = int(callback.data.split(":")[2])
    post = pending_posts.pop(post_id, None)
    if not post:
        await callback.answer("Пост не найден.", show_alert=True)
        return
    try:
        await callback.message.edit_text(f"❌ Пост [{post['rubric']}] отклонён")
    except Exception:
        pass
    logger.info(f"Moderated post #{post_id} [{post['rubric']}] dismissed by admin")
    await callback.answer()


@router.callback_query(F.data.startswith("chmod:mode:"))
async def chmod_toggle_mode(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    rubric = callback.data.split(":", 2)[2]
    current = await get_rubric_mode(rubric)
    new_mode = "auto" if current == "moderated" else "moderated"
    await set_rubric_mode(rubric, new_mode)

    # Rebuild keyboard
    buttons = []
    for r in RUBRIC_MODE:
        mode = await get_rubric_mode(r)
        emoji = RUBRIC_EMOJI.get(r, "📝")
        mode_label = "🤖 АВТО" if mode == "auto" else "👁 МОДЕР"
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {r} — {mode_label}",
            callback_data=f"chmod:mode:{r}",
        )])
    try:
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    except Exception:
        pass
    new_label = "🤖 АВТО" if new_mode == "auto" else "👁 МОДЕР"
    await callback.answer(f"{rubric} → {new_label}")


@router.callback_query(F.data.startswith("chmod:open:"))
async def chmod_open_pending(callback: types.CallbackQuery):
    """Открывает конкретный pending post из очереди."""
    if callback.from_user.id != ADMIN_ID:
        return
    post_id = int(callback.data.split(":")[2])
    post = pending_posts.get(post_id)
    if not post:
        await callback.answer("Пост уже обработан.", show_alert=True)
        return
    emoji = RUBRIC_EMOJI.get(post["rubric"], "📝")
    time_str = post["created_at"].strftime("%H:%M")
    preview_text = (
        f"📋 Пост на модерации (вариант #{post['attempts']})\n\n"
        f"Рубрика: {emoji} {post['rubric']}\n"
        f"Время: {time_str}\n\n"
        f"{'─' * 20}\n"
        f"{post['text']}\n"
        f"{'─' * 20}"
    )
    new_msg = await callback.message.answer(
        preview_text,
        reply_markup=_moderation_kb(post_id),
    )
    # Update preview_msg_id to the new message
    post["preview_msg_id"] = new_msg.message_id
    await callback.answer()


# ====================== FSM: редактирование поста ======================
@router.message(Command("cancel"), StateFilter(ChannelPostEdit.waiting_text))
async def cancel_edit(message: types.Message, state):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("Редактирование отменено.")


@router.message(StateFilter(ChannelPostEdit.waiting_text))
async def receive_edited_text(message: types.Message, state):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    post = pending_posts.get(post_id) if post_id else None
    if not post:
        await state.clear()
        await message.answer("Пост не найден, редактирование отменено.")
        return

    new_text = message.text.strip()
    post["text"] = new_text
    post["poll_data"] = None  # При ручном редактировании poll_data сбрасывается

    emoji = RUBRIC_EMOJI.get(post["rubric"], "📝")
    time_str = post["created_at"].strftime("%H:%M")
    preview_text = (
        f"📋 Пост отредактирован\n\n"
        f"Рубрика: {emoji} {post['rubric']}\n"
        f"Время: {time_str}\n\n"
        f"{'─' * 20}\n"
        f"{new_text}\n"
        f"{'─' * 20}"
    )
    new_msg = await message.answer(
        preview_text,
        reply_markup=_moderation_kb(post_id),
    )
    post["preview_msg_id"] = new_msg.message_id
    await state.clear()
    logger.info(f"Moderated post #{post_id} [{post['rubric']}] edited by admin")
