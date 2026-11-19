"""Block attempts to share personal contacts in the global chat.

Users may talk freely, but not hand out a way to reach each other off-platform:
phone numbers (even spelled out with spaces or dots), @handles, and the usual
tricks of splitting a number with letters or symbols. The check is intentionally
strict — a false positive just asks the user to rephrase, while a leak defeats
the whole point of keeping contact off the platform.
"""

import re
import unicodedata

# Characters people slip between digits to dodge a naive filter: whitespace,
# dots, dashes, the pipe, slashes, parentheses, plus, and a few look-alikes.
_DIGIT_SEPARATORS = r"[\s.\-_/|\\()+*#·•:;,'\"]"

# A run of digits this long (after separators are stripped) reads as a phone
# number. BR mobiles are 10-11 digits; 8 catches partials and DDD-less shares.
_MIN_PHONE_DIGITS = 8
# This many number-words ("nove nove oito ...") spells out a phone, and this
# many digits mixed with number-words is the same trick with letters in between.
_MIN_SPELLED_DIGITS = 5
_MIN_MIXED_DIGITS = 5

# Words that spell digits, so "nove nove oito..." is caught too.
_SPELLED_DIGITS = {
    "zero": "0", "um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3",
    "quatro": "4", "cinco": "5", "seis": "6", "meia": "6", "sete": "7",
    "oito": "8", "nove": "9",
}

# @handle (Instagram/Telegram) — '@' then a couple of handle characters.
_HANDLE_RE = re.compile(r"@[a-z0-9._]{2,}", re.IGNORECASE)

# "arroba" / "arrouba" written out next to a name is the same move as '@'.
_WRITTEN_AT_RE = re.compile(r"\barr?o+u?ba\b", re.IGNORECASE)

# A long run of digits once the separators between them are removed.
_LONG_DIGIT_RUN_RE = re.compile(
    rf"(?:\d{_DIGIT_SEPARATORS}*){{{_MIN_PHONE_DIGITS},}}"
)


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def contains_contact(text: str) -> bool:
    """True when the message tries to share a phone number or a handle."""
    if not text:
        return False
    normalized = _strip_accents(text)

    # 1. An @handle, or the word "arroba" used to point at one.
    if _HANDLE_RE.search(normalized) or _WRITTEN_AT_RE.search(normalized):
        return True

    # 2. A long digit run with only separators between the digits.
    if _LONG_DIGIT_RUN_RE.search(normalized):
        return True

    # 3. A number spelled out in words ("nove nove oito ..."), or the same trick
    #    with a few letters dropped between the digits.
    digit_count = sum(ch.isdigit() for ch in normalized)
    spelled = sum(
        1
        for word in re.findall(r"[a-z]+", normalized.lower())
        if word in _SPELLED_DIGITS
    )
    if spelled >= _MIN_SPELLED_DIGITS:
        return True
    if spelled >= 1 and digit_count + spelled >= _MIN_MIXED_DIGITS:
        return True

    return False
