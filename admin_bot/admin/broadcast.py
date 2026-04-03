"""
Admin Bot — рассылка: выбор сегмента, ввод текста, подтверждение, отправка.
Отправляет через main_bot (BOT_TOKEN), НЕ через admin_bot.
"""

import asyncio
import logging

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import ADMIN_ID
import admin_bot.db as _db

logger = logging.getLogger("admin-bot")

router = Router()

SEGMENTS = {
    "active": {
        "label": "👥 Все активные (7д)",
        "sql": "SELECT uid FROM users WHERE last_seen > NOW() - INTERVAL '7 days' AND ban_until IS NULL",
    },
    "inactive": {
        "label": "😴 Неактивные (7-30д)",
        "sql": (
            "SELECT uid FROM users WHERE last_seen < NOW() - INTERVAL '7 days' "
            "AND last_seen > NOW() - INTERVAL '30 days' AND ban_until IS NULL"
        ),
    },
    "premium": {
        "label": "⭐ Premium",
        "sql": "SELECT uid FROM users WHERE premium_until IS NOT NULL AND ban_until IS NULL",
    },
    "new": {
        "label": "🆕 Новые (24ч)",
        "sql": "SELECT uid FROM users WHERE created_at > NOW() - INTERVAL '24 hours' AND ban_until IS NULL",
    },
}


class BroadcastState(StatesGroup):
    waiting_text = State()


def kb_segments():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s["label"], callback_data=f"bcast:seg:{key}")]
        for key, s in SEGMENTS.items()
    ])


def kb_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="bcast:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="bcast:cancel"),
        ]
    ])


async def show_broadcast_menu(message: types.Message):
    """Показать выбор сегмента для рассылки."""
    await message.answer("📨 Рассылка — выбери сегмент:", reply_markup=kb_segments())


@router.callback_query(F.data.startswith("bcast:"), StateFilter("*"))
async def broadcast_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    action = parts[1]

    if action == "seg":
        segment_key = parts[2]
        if segment_key not in SEGMENTS:
            await callback.answer("Неизвестный сегмент", show_alert=True)
            return
        seg = SEGMENTS[segment_key]
        async with _db.db_pool.acquire() as conn:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM ({seg['sql']}) sub")
        await state.set_state(BroadcastState.waiting_text)
        await state.update_data(broadcast_segment=segment_key, broadcast_count=count)
        await callback.message.answer(
            f"📨 Сегмент: {seg['label']}\n"
            f"👥 Получателей: {count}\n\n"
            f"Напиши текст рассылки:"
        )

    elif action == "confirm":
        data = await state.get_data()
        segment_key = data.get("broadcast_segment")
        text = data.get("broadcast_text")
        if not segment_key or not text:
            await callback.message.answer("❌ Нет данных для рассылки.")
            await state.clear()
            await callback.answer()
            return

        seg = SEGMENTS[segment_key]
        await state.clear()

        # Отправляем через main_bot
        from admin_bot.main import main_bot
        if not main_bot:
            await callback.message.answer("❌ main_bot не настроен (нет BOT_TOKEN).")
            await callback.answer()
            return

        async with _db.db_pool.acquire() as conn:
            rows = await conn.fetch(seg["sql"])

        total = len(rows)
        sent = 0
        errors = 0
        progress_msg = await callback.message.answer(f"⏳ Отправка... 0/{total}")

        for i, row in enumerate(rows):
            try:
                await main_bot.send_message(row["uid"], text)
                sent += 1
            except Exception:
                errors += 1
            await asyncio.sleep(0.05)
            # Обновляем прогресс каждые 50 сообщений
            if (i + 1) % 50 == 0:
                try:
                    await progress_msg.edit_text(f"⏳ Отправка... {sent + errors}/{total}")
                except Exception:
                    pass

        try:
            await progress_msg.edit_text(
                f"✅ Рассылка завершена!\n\n"
                f"📨 Отправлено: {sent}/{total}\n"
                f"❌ Ошибок: {errors}"
            )
        except Exception:
            await callback.message.answer(
                f"✅ Рассылка завершена!\n\n"
                f"📨 Отправлено: {sent}/{total}\n"
                f"❌ Ошибок: {errors}"
            )

    elif action == "cancel":
        await state.clear()
        await callback.message.answer("❌ Рассылка отменена.")

    await callback.answer()


@router.message(StateFilter(BroadcastState.waiting_text))
async def receive_broadcast_text(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустой текст, попробуй ещё раз.")
        return
    data = await state.get_data()
    count = data.get("broadcast_count", 0)
    segment_key = data.get("broadcast_segment", "?")
    seg_label = SEGMENTS.get(segment_key, {}).get("label", segment_key)

    await state.update_data(broadcast_text=text)
    await message.answer(
        f"📨 Превью рассылки\n\n"
        f"Сегмент: {seg_label}\n"
        f"Получателей: {count}\n\n"
        f"— — —\n{text}\n— — —\n\n"
        f"Отправить?",
        reply_markup=kb_confirm()
    )
