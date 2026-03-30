"""
Универсальная утилита для OpenRouter AI.
Используется модерацией и (в будущем) AI-персонажами.
"""

import os
import aiohttp
import logging

logger = logging.getLogger("matchme.ai_utils")

OPEN_ROUTER_KEY = os.environ.get("OPEN_ROUTER")
OPEN_ROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def get_ai_answer(
    prompt: str,
    system_prompt: str,
    model_name: str,
    max_tokens: int = 400,
) -> str | None:
    """
    Отправляет запрос в OpenRouter и возвращает текст ответа.

    Args:
        prompt:        Текст пользователя (user message)
        system_prompt: Системный промпт
        model_name:    Модель OpenRouter, например "google/gemini-flash-1.5"
        max_tokens:    Максимум токенов в ответе

    Returns:
        Строка с ответом или None при ошибке.
    """
    if not OPEN_ROUTER_KEY:
        logger.warning("Переменная окружения OPEN_ROUTER не задана")
        return None
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/MatchMeBot",
    }
    payload = {
        "model": model_name,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPEN_ROUTER_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                body = await resp.text()
                logger.error(f"OpenRouter {resp.status}: {body[:300]}")
                return None
    except Exception as e:
        logger.error(f"OpenRouter exception: {e}")
        return None
