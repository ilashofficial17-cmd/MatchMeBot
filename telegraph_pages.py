"""
Telegraph page creator for MatchMe legal documents.
Uses Telegraph API (https://telegra.ph/api) to create pages with legal texts.
Pages are created once on bot startup and URLs are cached.
"""

import aiohttp
import logging
import json
import os

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(os.path.dirname(__file__), ".telegraph_cache.json")

# Telegraph access token (created on first run)
_token = None
_page_urls = {}


def _html_to_nodes(html: str) -> list:
    """Convert simple HTML to Telegraph Node format."""
    import re
    nodes = []
    parts = re.split(r'(<[^>]+>)', html)
    current_tag = None
    current_children = []

    for part in parts:
        if not part:
            continue
        if part.startswith('<') and not part.startswith('</'):
            tag_match = re.match(r'<(\w+)(?:\s[^>]*)?>', part)
            if tag_match:
                if current_tag and current_children:
                    nodes.append({"tag": current_tag, "children": current_children})
                    current_children = []
                current_tag = tag_match.group(1)
        elif part.startswith('</'):
            if current_tag and current_children:
                nodes.append({"tag": current_tag, "children": current_children})
            current_tag = None
            current_children = []
        else:
            text = part.strip()
            if text:
                if current_tag:
                    current_children.append(text)
                else:
                    nodes.append(text)
    if current_tag and current_children:
        nodes.append({"tag": current_tag, "children": current_children})
    return nodes


def _build_legal_content(lang: str) -> list:
    """Build Telegraph content nodes for legal document."""
    from legal_texts import LEGAL_DOCS
    doc = LEGAL_DOCS[lang]
    nodes = []
    for line in doc.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('### '):
            nodes.append({"tag": "h4", "children": [line[4:]]})
        elif line.startswith('## '):
            nodes.append({"tag": "h3", "children": [line[3:]]})
        elif line.startswith('**') and line.endswith('**'):
            nodes.append({"tag": "p", "children": [{"tag": "strong", "children": [line[2:-2]]}]})
        elif line.startswith('*') and line.endswith('*') and not line.startswith('**'):
            nodes.append({"tag": "p", "children": [{"tag": "em", "children": [line[1:-1]]}]})
        else:
            nodes.append({"tag": "p", "children": [line]})
    return nodes


async def _create_account(session: aiohttp.ClientSession) -> str:
    """Create Telegraph account and return access token."""
    async with session.post(
        "https://api.telegra.ph/createAccount",
        json={
            "short_name": "MatchMe",
            "author_name": "MatchMe Bot",
            "author_url": "https://t.me/MyMatchMeBot"
        }
    ) as resp:
        data = await resp.json()
        if data.get("ok"):
            return data["result"]["access_token"]
        raise RuntimeError(f"Telegraph createAccount failed: {data}")


async def _create_page(session: aiohttp.ClientSession, token: str, title: str, content: list) -> str:
    """Create Telegraph page and return URL."""
    async with session.post(
        "https://api.telegra.ph/createPage",
        json={
            "access_token": token,
            "title": title,
            "author_name": "MatchMe Bot",
            "author_url": "https://t.me/MyMatchMeBot",
            "content": content,
            "return_content": False,
        }
    ) as resp:
        data = await resp.json()
        if data.get("ok"):
            return data["result"]["url"]
        raise RuntimeError(f"Telegraph createPage failed: {data}")


def _load_cache() -> dict:
    """Load cached page URLs from file."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cache(data: dict):
    """Save page URLs to cache file."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Failed to save telegraph cache: {e}")


TITLES = {
    "ru": "MatchMe — Условия использования и Политика конфиденциальности",
    "en": "MatchMe — Terms of Service & Privacy Policy",
    "es": "MatchMe — Términos de Servicio y Política de Privacidad",
}


async def create_legal_pages() -> dict:
    """Create Telegraph pages for all languages. Returns {lang: url}."""
    global _token, _page_urls

    # Try cache first
    cache = _load_cache()
    if cache.get("token") and all(cache.get(lang) for lang in ("ru", "en", "es")):
        _token = cache["token"]
        _page_urls = {lang: cache[lang] for lang in ("ru", "en", "es")}
        logger.info(f"Telegraph pages loaded from cache: {_page_urls}")
        return _page_urls

    async with aiohttp.ClientSession() as session:
        # Create account if needed
        _token = cache.get("token")
        if not _token:
            _token = await _create_account(session)

        # Create pages for each language
        for lang in ("ru", "en", "es"):
            if cache.get(lang):
                _page_urls[lang] = cache[lang]
                continue
            content = _build_legal_content(lang)
            url = await _create_page(session, _token, TITLES[lang], content)
            _page_urls[lang] = url
            logger.info(f"Telegraph page created [{lang}]: {url}")

    # Save cache
    _save_cache({"token": _token, **_page_urls})
    return _page_urls


def get_legal_url(lang: str) -> str:
    """Get cached legal page URL for language."""
    return _page_urls.get(lang, _page_urls.get("en", ""))
