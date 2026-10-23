"""SnakePay Cash Out: withdraw an account's balance by Pix (docs shared by the platform owner, 2026-10).

* ``POST /withdrawals`` ``{amount (reais, 10–100000, or "MAX"), key, keyType, requestId}`` →
  202 ``{id, status: pending, total_debit, ...}``. ``requestId`` is a UUID saved BEFORE sending
  and reused on every retry of the same withdrawal (idempotency).
* ``GET /withdrawals/{id}`` → ``{id, status: pending|paid|failed, ...}``; ask at most every 30 s.
  There is no Cash Out webhook. ``failed`` gives the reserved balance back.
* Headers: ``Authorization: Bearer <api key>``, ``X-SnakePay-Timestamp`` (unix seconds) and
  ``X-SnakePay-Signature`` = HMAC-SHA256 hex, keyed with the account's Cash Out secret, of
  ``timestamp + "." + METHOD + "." + path + "." + raw body`` (empty body on GET).
* The account is the key's: never send a user id or ShopID. Keys and secrets stay server side.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from app.bots import http
from app.core.config import get_settings

MIN_AMOUNT = Decimal("10.00")
MAX_AMOUNT = Decimal("100000.00")


class CashoutError(RuntimeError):
    """``status`` 0 = no answer (the outcome is unknown: retry with the same requestId)."""

    def __init__(self, message: str, status: int = 0, detail: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail

    @property
    def retryable(self) -> bool:
        return self.status in (0, 429, 500, 502, 503, 504)


@dataclass
class Cashout:
    withdrawal_id: str
    status: str  # pending | paid | failed
    total_debit: Decimal | None


def _amount(value: object) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01")) if value is not None else None
    except ArithmeticError:
        return None


def sign(secret: str, timestamp: str, method: str, path: str, raw_body: str) -> str:
    message = f"{timestamp}.{method.upper()}.{path}.{raw_body}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _out(body: dict) -> Cashout:
    data = body.get("withdrawal") if isinstance(body.get("withdrawal"), dict) else body
    return Cashout(
        withdrawal_id=str(data.get("id") or ""),
        status=str(data.get("status") or "pending").lower(),
        total_debit=_amount(data.get("total_debit")),
    )


async def _call(method: str, path: str, body: dict | None, *, api_key: str, secret: str) -> dict:
    base = get_settings().snakepay_base_url.rstrip("/")
    full_path = urlsplit(base).path.rstrip("/") + path
    raw = json.dumps(body, separators=(",", ":")) if body is not None else ""
    timestamp = str(int(time.time()))
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-SnakePay-Timestamp": timestamp,
        "X-SnakePay-Signature": sign(secret, timestamp, method, full_path, raw),
    }
    try:
        async with http.client(20.0) as session:
            response = await session.request(method, f"{base}{path}", headers=headers, content=raw or None)
    except httpx.HTTPError as exc:
        raise CashoutError(f"SnakePay unreachable ({type(exc).__name__}).") from exc
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if response.is_error:
        raw_error = data.get("error") or data.get("message") or ""
        detail = str(raw_error.get("message") if isinstance(raw_error, dict) else raw_error)[:200]
        raise CashoutError(f"SnakePay Cash Out HTTP {response.status_code}: {detail}", response.status_code, detail)
    return data


async def create(*, amount: Decimal | None, pix_key: str, key_type: str, request_id: str, api_key: str, secret: str) -> Cashout:
    """``amount`` None = "MAX" (everything available). Same ``request_id`` on every retry."""
    body = {
        "amount": "MAX" if amount is None else float(amount.quantize(Decimal("0.01"))),
        "key": pix_key,
        "keyType": key_type,
        "requestId": request_id,
    }
    return _out(await _call("POST", "/withdrawals", body, api_key=api_key, secret=secret))


async def get(withdrawal_id: str, *, api_key: str, secret: str) -> Cashout:
    return _out(await _call("GET", f"/withdrawals/{withdrawal_id}", None, api_key=api_key, secret=secret))


def message(exc: CashoutError) -> str:
    """What to tell the user, in plain words."""
    detail = f" ({exc.detail})" if exc.detail else ""
    return {
        400: f"A SnakePay recusou os dados do saque: confira a chave Pix{detail}.",
        401: "A SnakePay não aceitou a chave ou o segredo de saque: confira em Gateways.",
        403: "O saque (Cash Out) não está liberado nesta conta da SnakePay.",
        404: "A SnakePay não encontrou este saque.",
        409: "Já existe um saque em andamento nesta conta da SnakePay. Aguarde ele terminar.",
        413: "A SnakePay recusou o pedido de saque (tamanho).",
        415: "A SnakePay recusou o pedido de saque (formato).",
        422: "Saldo insuficiente na SnakePay para este saque.",
    }.get(exc.status, "A SnakePay não respondeu agora. O saque fica aguardando e é confirmado sozinho.")
