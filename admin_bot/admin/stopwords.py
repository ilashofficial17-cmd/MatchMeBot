"""
Admin Bot — управление стоп-словами через reply-кнопку.
Показ списков, добавление/удаление через FSM + inline.
"""

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


class StopWordsState(StatesGroup):
    waiting_hard_word = State()
    waiting_suspect_word = State()
    waiting_delete_word = State()


def kb_stopwords_actions():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить жёсткий", callback_data="sw:add_hard"),
            InlineKeyboardButton(text="➕ Добавить подозрительный", callback_data="sw:add_suspect"),
        ],
        [InlineKeyboardButton(text="➖ Удалить слово", callback_data="sw:delete")],
    ])


async def show_stopwords(message: types.Message):
    """Показать текущие списки стоп-слов."""
    async with _db.db_pool.acquire() as conn:
        hard = await conn.fetch(
            "SELECT word FROM stop_words WHERE type='hard_ban' ORDER BY added_at"
        )
        suspect = await conn.fetch(
            "SELECT word FROM stop_words WHERE type='suspect' ORDER BY added_at"
        )
    hard_list = "\n".join(f"• {r['word']}" for r in hard) if hard else "— пусто —"
    suspect_list = "\n".join(f"• {r['word']}" for r in suspect) if suspect else "— пусто —"
    text = (
        f"🚫 Стоп-слова\n\n"
        f"🔴 Жёсткий бан (авто) [{len(hard)}]:\n{hard_list}\n\n"
        f"🟡 Подозрительные (AI проверка) [{len(suspect)}]:\n{suspect_list}"
    )
    await message.answer(text, reply_markup=kb_stopwords_actions())


@router.callback_query(F.data.startswith("sw:"), StateFilter("*"))
async def stopwords_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]

    if action == "add_hard":
        await state.set_state(StopWordsState.waiting_hard_word)
        await callback.message.answer("🔴 Введи слово/фразу для жёсткого бана:")

    elif action == "add_suspect":
        await state.set_state(StopWordsState.waiting_suspect_word)
        await callback.message.answer("🟡 Введи слово/фразу для подозрительных:")

    elif action == "delete":
        await state.set_state(StopWordsState.waiting_delete_word)
        await callback.message.answer("➖ Введи слово/фразу для удаления:")

    await callback.answer()


@router.message(StateFilter(StopWordsState.waiting_hard_word))
async def add_hard_word(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    word = (message.text or "").strip().lower()
    if not word:
        await message.answer("Пустой ввод, попробуй ещё раз.")
        return
    await state.clear()
    async with _db.db_pool.acquire() as conn:
        result = await conn.execute(
            "INSERT INTO stop_words (word, type) VALUES ($1, 'hard_ban') ON CONFLICT (word) DO NOTHING", word
        )
    if "INSERT 0 0" in result:
        await message.answer(f"⚠️ «{word}» уже есть в списке.")
    else:
        await message.answer(f"✅ «{word}» добавлено в жёсткий бан.")
    await show_stopwords(message)


@router.message(StateFilter(StopWordsState.waiting_suspect_word))
async def add_suspect_word(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    word = (message.text or "").strip().lower()
    if not word:
        await message.answer("Пустой ввод, попробуй ещё раз.")
        return
    await state.clear()
    async with _db.db_pool.acquire() as conn:
        result = await conn.execute(
            "INSERT INTO stop_words (word, type) VALUES ($1, 'suspect') ON CONFLICT (word) DO NOTHING", word
        )
    if "INSERT 0 0" in result:
        await message.answer(f"⚠️ «{word}» уже есть в списке.")
    else:
        await message.answer(f"✅ «{word}» добавлено в подозрительные.")
    await show_stopwords(message)


@router.message(StateFilter(StopWordsState.waiting_delete_word))
async def delete_word(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    word = (message.text or "").strip().lower()
    if not word:
        await message.answer("Пустой ввод, попробуй ещё раз.")
        return
    await state.clear()
    async with _db.db_pool.acquire() as conn:
        result = await conn.execute("DELETE FROM stop_words WHERE word=$1", word)
    if "DELETE 0" in result:
        await message.answer(f"❌ «{word}» не найдено в списках.")
    else:
        await message.answer(f"🗑 «{word}» удалено.")
    await show_stopwords(message)
