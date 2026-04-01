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


async def get_ai_chat_response(
    system_prompt: str,
    history: list,
    model_name: str,
    max_tokens: int = 300,
    temperature: float | None = None,
) -> str | None:
    """
    Отправляет запрос в OpenRouter с полной историей чата.

    Args:
        system_prompt: Системный промпт персонажа
        history:       Список сообщений [{"role": "user/assistant", "content": "..."}]
        model_name:    Модель OpenRouter
        max_tokens:    Максимум токенов в ответе
        temperature:   Температура генерации (None = дефолт модели)

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
    messages = [{"role": "system", "content": system_prompt}] + list(history)
    payload = {
        "model": model_name,
        "max_tokens": max_tokens,
        "messages": messages,
        "transforms": ["cache-prompt"],  # OpenRouter prompt caching
    }
    if temperature is not None:
        payload["temperature"] = temperature
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
                logger.error(f"OpenRouter chat {resp.status}: {body[:300]}")
                return None
    except Exception as e:
        logger.error(f"OpenRouter chat exception: {e}")
        return None


async def describe_image(image_base64: str, lang: str = "ru") -> str | None:
    """
    Describe an image using GPT-4o-mini vision.
    Returns a brief description in the user's language.
    """
    if not OPEN_ROUTER_KEY:
        return None
    lang_prompts = {
        "ru": "Опиши кратко что на фото (1-2 предложения). Если на фото человек — опиши внешность, одежду, выражение. Если другое — опиши что видишь. Пиши на русском.",
        "en": "Briefly describe what's in the photo (1-2 sentences). If it's a person — describe appearance, clothing, expression. If something else — describe what you see.",
        "es": "Describe brevemente lo que hay en la foto (1-2 oraciones). Si es una persona — describe apariencia, ropa, expresión. Si es otra cosa — describe lo que ves.",
    }
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/MatchMeBot",
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "max_tokens": 150,
        "messages": [
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": lang_prompts.get(lang, lang_prompts["en"])},
            ]},
        ],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPEN_ROUTER_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                body = await resp.text()
                logger.error(f"OpenRouter vision {resp.status}: {body[:300]}")
                return None
    except Exception as e:
        logger.error(f"OpenRouter vision exception: {e}")
        return None


async def transcribe_voice(audio_base64: str, lang: str = "ru") -> str | None:
    """
    Transcribe a voice message using Gemini Flash via OpenRouter.
    Accepts base64-encoded OGG audio. Returns transcribed text.
    """
    if not OPEN_ROUTER_KEY:
        return None
    lang_hints = {
        "ru": "Транскрибируй это голосовое сообщение. Выведи ТОЛЬКО текст того что сказано, ничего больше. Язык: русский.",
        "en": "Transcribe this voice message. Output ONLY the spoken text, nothing else. Language: English.",
        "es": "Transcribe este mensaje de voz. Devuelve SOLO el texto hablado, nada más. Idioma: español.",
    }
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/MatchMeBot",
    }
    payload = {
        "model": "google/gemini-flash-1.5",
        "max_tokens": 500,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:audio/ogg;base64,{audio_base64}"},
                },
                {
                    "type": "text",
                    "text": lang_hints.get(lang, lang_hints["en"]),
                },
            ],
        }],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPEN_ROUTER_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                body = await resp.text()
                logger.error(f"OpenRouter voice transcription {resp.status}: {body[:300]}")
                return None
    except Exception as e:
        logger.error(f"OpenRouter voice transcription exception: {e}")
        return None


_LANG_NAMES = {"ru": "Russian", "en": "English", "es": "Spanish"}


async def translate_message(text: str, from_lang: str, to_lang: str) -> str | None:
    """
    Translate a chat message using OpenRouter gpt-4o-mini.
    Returns translated text or None on failure.
    """
    if from_lang == to_lang:
        return text
    target = _LANG_NAMES.get(to_lang, "English")
    system = (
        f"You are a translator. Translate the user's message into {target}. "
        "Output ONLY the translation, nothing else. Keep emojis and formatting. "
        "If the message is already in the target language, return it as-is."
    )
    return await get_ai_answer(
        prompt=text,
        system_prompt=system,
        model_name="openai/gpt-4o-mini",
        max_tokens=400,
    )
