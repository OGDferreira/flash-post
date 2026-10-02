import unicodedata


def normalize_nickname(value: object) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(
            "Nickname must be 3-30 letters, numbers, dots, or underscores with no surrounding spaces."
        )
    value = unicodedata.normalize("NFC", value)
    if (
        not 3 <= len(value) <= 30
        or any(not char.isalnum() and char not in "._" for char in value)
    ):
        raise ValueError(
            "Nickname must be 3-30 letters, numbers, dots, or underscores with no surrounding spaces."
        )
    normalized = value.casefold()
    if not 3 <= len(normalized) <= 30:
        raise ValueError(
            "Nickname must be 3-30 letters, numbers, dots, or underscores with no surrounding spaces."
        )
    return normalized
