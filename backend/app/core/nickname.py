import unicodedata


def normalize_nickname(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(
            "Nickname must contain between 2 and 40 characters."
        )

    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    if not 2 <= len(normalized) <= 40 or any(
        unicodedata.category(char) in {"Cc", "Cs"} for char in normalized
    ):
        raise ValueError(
            "Nickname must contain between 2 and 40 characters."
        )
    return normalized


def nickname_key(value: str) -> str:
    return normalize_nickname(value).casefold()
