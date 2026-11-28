"""Auto-translation of funnel copy via a self-hosted LibreTranslate on the VPS.

Off by default: with no ``LIBRETRANSLATE_URL`` the copy goes out unchanged. It never
raises — a failed or slow translation falls back to the original text so a sale is
never blocked by the translator.
"""

import httpx

from app.bots import http
from app.core.config import get_settings

# Languages LibreTranslate commonly ships; a lead's Telegram language_code outside this
# set falls back to the original copy (Portuguese) instead of a wrong guess.
SUPPORTED = {"en", "es", "fr", "de", "it", "pt", "ru", "ar", "zh", "ja", "nl", "pl", "tr", "ko", "id"}


def configured() -> bool:
    return bool(get_settings().libretranslate_url.strip())


def lang_of(language_code: str | None) -> str | None:
    """The 2-letter target from a Telegram ``language_code`` (e.g. 'en-US' -> 'en')."""
    if not language_code:
        return None
    code = language_code.strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED else None


async def translate(text: str, target: str | None, *, source: str = "pt") -> str:
    """Translate ``text`` to ``target`` (2-letter). Returns the original on any problem."""
    base = get_settings().libretranslate_url.strip()
    if not base or not text or not text.strip() or not target or target == source:
        return text
    api_key = ""  # self-hosted instance with no key; kept for parity if one is set later
    payload = {"q": text, "source": source, "target": target, "format": "html"}
    if api_key:
        payload["api_key"] = api_key
    try:
        async with http.client(timeout=8.0) as session:
            response = await session.post(f"{base.rstrip('/')}/translate", json=payload)
        if response.status_code >= 400:
            return text
        translated = response.json().get("translatedText")
    except (httpx.HTTPError, ValueError):
        return text
    return translated if isinstance(translated, str) and translated.strip() else text
