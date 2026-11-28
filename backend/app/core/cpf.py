"""CPF handling: normalize to 11 digits and validate the two check digits.

This is format + checksum validation only (it proves the number is well-formed,
not that it belongs to the person). Real identity/KYC would be a separate
integration against an official base.
"""

import re

_NON_DIGITS = re.compile(r"\D")


class InvalidCpf(ValueError):
    """Raised when a CPF is malformed or fails its check digits."""


def normalize_cpf(value: str) -> str:
    """Strip everything but digits and require exactly 11. Raises ``InvalidCpf``."""
    if not isinstance(value, str):
        raise InvalidCpf("Informe um CPF válido.")
    digits = _NON_DIGITS.sub("", value)
    if len(digits) != 11:
        raise InvalidCpf("O CPF precisa ter 11 dígitos.")
    return digits


def _check_digit(digits: str, length: int) -> int:
    # Weights run high→low: 10..2 for the first digit, 11..2 for the second.
    total = sum(int(digits[i]) * (length + 1 - i) for i in range(length))
    remainder = (total * 10) % 11
    return 0 if remainder == 10 else remainder


def is_valid_cpf(value: str) -> bool:
    """True when ``value`` normalizes to 11 digits with correct check digits."""
    try:
        digits = normalize_cpf(value)
    except InvalidCpf:
        return False
    # All-equal digits (000...000, 111...111, ...) pass the checksum but are never
    # real CPFs, so reject them explicitly.
    if digits == digits[0] * 11:
        return False
    return _check_digit(digits, 9) == int(digits[9]) and _check_digit(digits, 10) == int(digits[10])


def validate_cpf(value: str) -> str:
    """Normalize and fully validate a CPF, returning the 11-digit form or raising."""
    digits = normalize_cpf(value)
    if not is_valid_cpf(digits):
        raise InvalidCpf("CPF inválido. Confira os números digitados.")
    return digits


def format_cpf(digits: str) -> str:
    """Pretty ``000.000.000-00`` form for display; returns input unchanged if not 11 digits."""
    if len(digits) != 11 or not digits.isdigit():
        return digits
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
