"""
Admin Bot — медиа AI персонажей: charmedia:*, cmview:*, cmdel:*.
Перенесено из admin.py.
"""

import logging

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.config import ADMIN_ID
import admin_bot.db as _db
from admin_bot.admin.router import AdminState

logger = logging.getLogger("admin-bot")

router = Router()

# Загружаем AI_CHARACTERS из ai_characters.py
try:
    from ai_characters import AI_CHARACTERS
except ImportError:
    AI_CHARACTERS = {}

_FIELD_LABELS = {
    "gif_file_id": "GIF",
    "photo_file_id": "Фото",
    "hot_photo_file_id": "Hot фото",
    "hot_gif_file_id": "Hot GIF",
}


async def show_char_media_list(callback: types.CallbackQuery):
    """Показать список персонажей для загрузки медиа."""
    chars = AI_CHARACTERS
    buttons = []
    row = []
    for cid, cdata in chars.items():
        label = f"{cdata['emoji']} {cid}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"charmedia:{cid}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    has_media = set()
    async with _db.db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT character_id FROM ai_character_media WHERE gif_file_id IS NOT NULL")
        has_media = {r["character_id"] for r in rows}
    info = f"🖼 Медиа персонажей\n\nЗагружено: {len(has_media)}/{len(chars)}\n\nВыбери персонажа:"
    await callback.message.answer(info, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


async def show_char_media_list_msg(message: types.Message):
    """Показать список персонажей (вызывается из reply-кнопки)."""
    chars = AI_CHARACTERS
    buttons = []
    row = []
    for cid, cdata in chars.items():
        label = f"{cdata['emoji']} {cid}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"charmedia:{cid}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    has_media = set()
    async with _db.db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT character_id FROM ai_character_media WHERE gif_file_id IS NOT NULL")
        has_media = {r["character_id"] for r in rows}
    info = f"🖼 Медиа персонажей\n\nЗагружено: {len(has_media)}/{len(chars)}\n\nВыбери персонажа:"
    await message.answer(info, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("charmedia:"), StateFilter("*"))
async def char_media_select(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    char_id = callback.data.split(":", 1)[1]
    chars = AI_CHARACTERS
    if char_id not in chars:
        await callback.answer("Персонаж не найден", show_alert=True)
        return
    char = chars[char_id]
    async with _db.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT gif_file_id, photo_file_id, blurred_file_id, hot_photo_file_id, hot_gif_file_id "
            "FROM ai_character_media WHERE character_id=$1",
            char_id
        )
    gif_status = "✅" if (row and row["gif_file_id"]) else "❌"
    photo_status = "✅" if (row and row["photo_file_id"]) else "❌"
    hot_status = "✅" if (row and row.get("hot_photo_file_id")) else "❌"
    hot_gif_status = "✅" if (row and row.get("hot_gif_file_id")) else "❌"
    text = (
        f"{char['emoji']} <b>{char_id}</b>\n\n"
        f"{gif_status} GIF (превью)\n"
        f"{photo_status} Фото — 15 ⭐\n"
        f"{hot_status} 🔥 Hot фото — 50 ⭐\n"
        f"{hot_gif_status} 🔥 Hot GIF — 100 ⭐\n\n"
        f"Загрузка: GIF → превью, GIF+hot → hot GIF\n"
        f"Фото → платное, Фото+hot → горячее"
    )
    media_buttons = []
    slots = [
        ("gif_file_id", "👁 GIF", "🗑 GIF"),
        ("photo_file_id", "👁 Фото", "🗑 Фото"),
        ("hot_photo_file_id", "👁 Hot фото", "🗑 Hot фото"),
        ("hot_gif_file_id", "👁 Hot GIF", "🗑 Hot GIF"),
    ]
    for field, view_label, del_label in slots:
        if row and row.get(field):
            media_buttons.append([
                InlineKeyboardButton(text=view_label, callback_data=f"cmview:{char_id}:{field}"),
                InlineKeyboardButton(text=del_label, callback_data=f"cmdel:{char_id}:{field}"),
            ])
    kb = InlineKeyboardMarkup(inline_keyboard=media_buttons) if media_buttons else None
    await state.set_state(AdminState.waiting_char_gif)
    await state.update_data(media_char_id=char_id)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.message(StateFilter(AdminState.waiting_char_gif))
async def char_media_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    char_id = data.get("media_char_id")
    if not char_id:
        await state.clear()
        await message.answer("Ошибка — попробуй заново через /admin")
        return
    chars = AI_CHARACTERS
    char = chars.get(char_id)
    emoji = char["emoji"] if char else ""
    caption = (message.caption or "").strip().lower()

    if message.animation:
        file_id = message.animation.file_id
        if caption == "hot":
            async with _db.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ai_character_media (character_id, hot_gif_file_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET hot_gif_file_id=$2, updated_at=NOW()
                """, char_id, file_id)
            await message.answer(
                f"🔥 Hot GIF для {emoji} <b>{char_id}</b> сохранён!\n\n"
                f"Отправь ещё медиа или нажми /admin для выхода.",
                parse_mode="HTML"
            )
        else:
            async with _db.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ai_character_media (character_id, gif_file_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET gif_file_id=$2, updated_at=NOW()
                """, char_id, file_id)
            await message.answer(
                f"✅ GIF для {emoji} <b>{char_id}</b> сохранён!\n\n"
                f"Отправь ещё медиа или нажми /admin для выхода.",
                parse_mode="HTML"
            )
    elif message.photo:
        file_id = message.photo[-1].file_id
        if caption == "hot":
            async with _db.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ai_character_media (character_id, hot_photo_file_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET hot_photo_file_id=$2, updated_at=NOW()
                """, char_id, file_id)
            await message.answer(
                f"🔥 Hot фото для {emoji} <b>{char_id}</b> сохранено!\n\n"
                f"Отправь ещё медиа или нажми /admin для выхода.",
                parse_mode="HTML"
            )
        else:
            async with _db.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ai_character_media (character_id, photo_file_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET photo_file_id=$2, updated_at=NOW()
                """, char_id, file_id)
            await message.answer(
                f"✅ Фото для {emoji} <b>{char_id}</b> сохранено!\n\n"
                f"Отправь фото с подписью hot для горячего фото.\n"
                f"Или отправь ещё медиа / /admin для выхода.",
                parse_mode="HTML"
            )
    elif message.text and message.text.startswith("/"):
        await state.clear()
        return
    else:
        await message.answer(
            "⚠️ Отправь GIF, фото, или с подписью hot.\n"
            "Или /admin для выхода."
        )


@router.callback_query(F.data.startswith("cmview:"), StateFilter("*"))
async def char_media_view(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    _, char_id, field = callback.data.split(":", 2)
    if field not in _FIELD_LABELS:
        await callback.answer("Неизвестный слот", show_alert=True)
        return
    async with _db.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {field} FROM ai_character_media WHERE character_id=$1",
            char_id
        )
    if not row or not row[field]:
        await callback.answer("Файл не найден", show_alert=True)
        return
    file_id = row[field]
    label = _FIELD_LABELS.get(field, field)
    from admin_bot.main import admin_bot
    try:
        if "gif" in field:
            await admin_bot.send_animation(callback.from_user.id, file_id, caption=f"{label} — {char_id}")
        else:
            await admin_bot.send_photo(callback.from_user.id, file_id, caption=f"{label} — {char_id}")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("cmdel:"), StateFilter("*"))
async def char_media_delete(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    _, char_id, field = callback.data.split(":", 2)
    if field not in _FIELD_LABELS:
        await callback.answer("Неизвестный слот", show_alert=True)
        return
    async with _db.db_pool.acquire() as conn:
        await conn.execute(
            f"UPDATE ai_character_media SET {field}=NULL, updated_at=NOW() WHERE character_id=$1",
            char_id
        )
    label = _FIELD_LABELS[field]
    await callback.answer(f"🗑 {label} удалён для {char_id}", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass
    callback.data = f"charmedia:{char_id}"
    await char_media_select(callback, state)
