from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    if settings.master_encryption_key is None:
        raise RuntimeError("MASTER_ENCRYPTION_KEY is required for encryption.")
    key = settings.master_encryption_key.get_secret_value().encode("utf-8")
    try:
        return Fernet(key)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("MASTER_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def encrypt_value(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise ValueError("Encrypted value could not be decrypted.") from exc
