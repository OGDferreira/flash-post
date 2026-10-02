from enum import StrEnum

from pwdlib import PasswordHash


class WorkspaceRole(StrEnum):
    OWNER = "OWNER"
    COLLABORATOR = "COLLABORATOR"


class PlatformRole(StrEnum):
    USER = "USER"
    SUPER_ADMIN = "SUPER_ADMIN"


password_hasher = PasswordHash.recommended()
_dummy_password_hash = password_hasher.hash("flashpost-invalid-account-placeholder")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        password_hasher.verify(password, _dummy_password_hash)
        return False
    try:
        return password_hasher.verify(password, password_hash)
    except (ValueError, TypeError):
        password_hasher.verify(password, _dummy_password_hash)
        return False
