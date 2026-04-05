"""
Универсальная утилита для OpenRouter AI.
Используется модерацией и (в будущем) AI-персонажами.
"""

import os
import asyncio
import aiohttp
import logging

logger = logging.getLogger("matchme.ai_utils")

OPEN_ROUTER_KEY = os.environ.get("OPEN_ROUTER")
OPEN_ROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Semaphore: макс 20 одновременных запросов к API
_api_semaphore = asyncio.Semaphore(20)

# Budget fallback model (cheap, fast)
_BUDGET_MODEL = "google/gemini-flash-1.5"

# Hourly budget cap
from datetime import datetime as _dt
_AI_HOURLY_LIMIT = int(os.environ.get("AI_HOURLY_LIMIT", "500"))
_ai_hour_counter = 0
_ai_hour_reset = _dt.now()


def check_ai_budget() -> bool:
    """Returns True if within hourly AI call limit."""
    global _ai_hour_counter, _ai_hour_reset
    now = _dt.now()
    if (now - _ai_hour_reset).total_seconds() > 3600:
        _ai_hour_counter = 0
        _ai_hour_reset = now
    if _ai_hour_counter >= _AI_HOURLY_LIMIT:
        return False
    _ai_hour_counter += 1
    return True


def _record_ai_call():
    """Record AI call in monitoring if available."""
    try:
        from monitoring import metrics
        metrics.record_ai_call()
    except ImportError:
        pass


# Singleton aiohttp session (переиспользуем TCP-соединения)
_http_session: aiohttp.ClientSession | None = None


async def _get_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


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
    if not check_ai_budget():
        logger.warning("AI hourly budget exceeded")
        return None
    _record_ai_call()
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
        async with _api_semaphore:
            session = await _get_session()
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
    budget_mode: bool = False,
) -> str | None:
    """
    Отправляет запрос в OpenRouter с полной историей чата.

    Args:
        system_prompt: Системный промпт персонажа
        history:       Список сообщений [{"role": "user/assistant", "content": "..."}]
        model_name:    Модель OpenRouter
        max_tokens:    Максимум токенов в ответе
        temperature:   Температура генерации (None = дефолт модели)
        budget_mode:   При True — использовать дешёвую модель вместо запрошенной

    Returns:
        Строка с ответом или None при ошибке.
    """
    if not OPEN_ROUTER_KEY:
        logger.warning("Переменная окружения OPEN_ROUTER не задана")
        return None
    if not check_ai_budget():
        logger.warning("AI hourly budget exceeded")
        return None
    _record_ai_call()
    actual_model = _BUDGET_MODEL if budget_mode else model_name
    if budget_mode and actual_model != model_name:
        logger.info(f"Budget mode: {model_name} → {actual_model}")
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/MatchMeBot",
    }
    messages = [{"role": "system", "content": system_prompt}] + list(history)
    payload = {
        "model": actual_model,
        "max_tokens": max_tokens,
        "messages": messages,
        "transforms": ["cache-prompt"],  # OpenRouter prompt caching
    }
    if temperature is not None:
        payload["temperature"] = temperature
    try:
        async with _api_semaphore:
            session = await _get_session()
            async with session.post(
                OPEN_ROUTER_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Log token usage for cost tracking
                    usage = data.get("usage")
                    if usage:
                        total_tokens = usage.get("total_tokens", 0)
                        logger.info(f"Tokens: {total_tokens} model={actual_model}")
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
        async with _api_semaphore:
            session = await _get_session()
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
        async with _api_semaphore:
            session = await _get_session()
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


_SUMMARIZE_MODEL = "google/gemini-2.0-flash-001"

_SUMMARIZE_PROMPT = (
    "Ты анализируешь диалог между пользователем и AI-персонажем в чате знакомств.\n"
    "Напиши:\n"
    "1. Краткое резюме разговора (2-3 предложения, что обсуждали, какая была атмосфера)\n"
    "2. Ключевые факты о пользователе (имя, возраст, интересы, что рассказал о себе, настроение)\n\n"
    "Формат ответа СТРОГО:\n"
    "SUMMARY: <резюме>\n"
    "FACTS: <факт1> | <факт2> | <факт3>\n\n"
    "Если фактов нет — напиши FACTS: none\n"
    "Пиши кратко. Только факты из диалога, не додумывай."
)


async def summarize_conversation(history: list[dict]) -> tuple[str, list[str]]:
    """
    Summarize a conversation and extract user facts.
    Returns (summary, [fact1, fact2, ...]).
    Uses Gemini Flash for cost efficiency (~$0.001 per call).
    """
    if not history:
        return "", []

    # Format last 10 messages for summarization
    messages = history[-10:]
    chat_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'AI'}: {m['content']}"
        for m in messages
    )

    raw = await get_ai_answer(
        prompt=f"Диалог:\n{chat_text}",
        system_prompt=_SUMMARIZE_PROMPT,
        model_name=_SUMMARIZE_MODEL,
        max_tokens=300,
    )
    if not raw:
        return "", []

    summary = ""
    facts = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = line[len("SUMMARY:"):].strip()
        elif line.upper().startswith("FACTS:"):
            facts_raw = line[len("FACTS:"):].strip()
            if facts_raw.lower() != "none":
                facts = [f.strip() for f in facts_raw.split("|") if f.strip()]
    return summary, facts[:10]


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
