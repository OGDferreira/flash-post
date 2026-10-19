"""SmokePay PIX client and webhook signature check (docs/bots-telegram/SMOKEPAY.md)."""

import asyncio
import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.bots import http
from app.core.config import get_settings

MAX_ATTEMPTS = 3
SIGNATURE_TOLERANCE_SECONDS = 300


class SmokepayError(RuntimeError):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status
        self.detail = ""
        self.cooldown_seconds: int | None = None
        self.requires_kyc = False


class SmokepayNotConfigured(SmokepayError):
    pass


@dataclass
class PixCharge:
    transaction_id: str
    external_id: str
    status: str
    amount: Decimal
    fee: Decimal | None
    net_amount: Decimal | None
    copy_paste: str | None
    qr_code_base64: str | None
    expires_at: str | None
    payer_name: str | None = None
    split_total: Decimal | None = None  # sum of splits_preview amounts
    owner_net: Decimal | None = None  # what stays in the charging subaccount


def _api_key() -> str:
    key = get_settings().smokepay_api_key
    if key is None or not key.get_secret_value().strip():
        raise SmokepayNotConfigured("SMOKEPAY_API_KEY is not configured.")
    return key.get_secret_value().strip()


def _money(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _charge(data: dict) -> PixCharge:
    preview = data.get("splits_preview") or data.get("splits") or {}
    parts = preview.get("splits") or preview.get("details") or [] if isinstance(preview, dict) else []
    amounts = [_money(p.get("amount")) for p in parts if isinstance(p, dict) and p.get("amount") is not None]
    return PixCharge(
        transaction_id=str(data.get("id") or data.get("transaction_id") or ""),
        external_id=str(data.get("external_id") or ""),
        status=str(data.get("status") or "pending"),
        amount=_money(data.get("amount")) or Decimal("0"),
        fee=_money(data.get("fee")),
        net_amount=_money(data.get("net_amount")),
        copy_paste=data.get("pix_copia_cola"),
        qr_code_base64=data.get("qr_code_base64"),
        expires_at=data.get("expires_at"),
        payer_name=data.get("payer_name"),
        split_total=sum(amounts, Decimal("0.00")) if amounts else None,
        owner_net=_money(preview.get("owner_net_amount")) if isinstance(preview, dict) else None,
    )


def _withdraw_key() -> str:
    key = get_settings().smokepay_withdraw_api_key
    if key is not None and key.get_secret_value().strip():
        return key.get_secret_value().strip()
    return _api_key()


async def _request(
    method: str, path: str, json_body: dict | None = None, *, key: str | None = None, attempts: int = MAX_ATTEMPTS
) -> dict:
    url = f"{get_settings().smokepay_base_url.rstrip('/')}{path}"
    headers = {"x-api-key": key or _api_key(), "Content-Type": "application/json"}
    last: SmokepayError | None = None
    for attempt in range(attempts):
        if attempt:
            await asyncio.sleep(2 ** attempt)
        try:
            async with http.client(20.0) as session:
                response = await session.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            last = SmokepayError(f"SmokePay unreachable ({type(exc).__name__}).")
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            last = SmokepayError(f"SmokePay HTTP {response.status_code}.", response.status_code)
            continue
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.is_error:
            detail = str(body.get("error") or body.get("message") or "")[:200]
            error = SmokepayError(f"SmokePay HTTP {response.status_code}: {detail}", response.status_code)
            error.detail = detail
            error.cooldown_seconds = body.get("cooldown_seconds")
            error.requires_kyc = bool(body.get("requires_kyc"))
            raise error
        return body
    assert last is not None
    raise last


async def create_pix(
    *, amount: Decimal, external_id: str, description: str, webhook_url: str, expiration_seconds: int,
    shop_id: str | None = None, splits: list[dict] | None = None,
) -> PixCharge:
    """Idempotent on ``external_id``: retries with the same id never create a second charge.

    ``shop_id`` charges into that subaccount (SmokePay creates it on first use);
    ``splits`` divides the net between subaccounts/parent, applied by SmokePay itself.
    """
    payload: dict = {
        "amount": float(amount.quantize(Decimal("0.01"))),
        "external_id": external_id,
        "description": description[:120],
        "webhook_url": webhook_url,
        "expiration": int(expiration_seconds),
    }
    if shop_id:
        payload["shop_id"] = shop_id
        if splits:
            payload["splits"] = splits
    body = await _request("POST", "/api/pix/create", payload)
    return _charge(body.get("transaction") or {})


async def get_pix(identifier: str) -> PixCharge:
    return _charge(await _request("GET", f"/api/pix/{identifier}"))


def verify_signature(raw_body: bytes, header: str | None, now: float | None = None) -> bool:
    """HMAC-SHA256 of ``"<t>.<raw body>"`` (header ``t=<unix>,v1=<hex>``), ±5 min."""
    secret = get_settings().smokepay_webhook_secret
    if secret is None or not header:
        return False
    fields = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    timestamp, received = fields.get("t", ""), fields.get("v1", "")
    if not timestamp.isdigit() or not received:
        return False
    if abs((now or time.time()) - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    expected = hmac.new(
        secret.get_secret_value().encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received.lower())


# ------------------------------------------------------------------ balances and withdrawals
# docs: "Subcontas" (GET /api/shops/{id}/balance, POST /api/shops/{id}/withdraw,
# GET /api/shops/{id}/withdrawals) and "Saldo"/"Saques" for the main wallet.


@dataclass
class Payout:
    withdrawal_id: str
    amount: Decimal
    fee: Decimal | None
    status: str  # completed | processing | pending | failed
    failure_reason: str | None = None
    e2e_id: str | None = None  # Pix end-to-end id (bank receipt)
    pix_key: str | None = None
    pix_key_type: str | None = None
    processed_at: str | None = None


def _payout(data: dict) -> Payout:
    return Payout(
        withdrawal_id=str(data.get("withdrawal_id") or data.get("id") or ""),
        amount=_money(data.get("amount")) or Decimal("0"),
        fee=_money(data.get("fee")),
        status=str(data.get("status") or "processing"),
        failure_reason=data.get("failure_reason"),
        e2e_id=data.get("gateway_e2eid") or data.get("e2e_id") or None,
        pix_key=data.get("pix_key"),
        pix_key_type=data.get("pix_key_type"),
        processed_at=data.get("processed_at"),
    )


async def shop_balance(shop_ref: str) -> Decimal | None:
    """Available balance of a subaccount; None when it was never created (no sale yet)."""
    try:
        body = await _request("GET", f"/api/shops/{shop_ref}/balance", key=_withdraw_key())
    except SmokepayError as exc:
        if exc.status == 404:
            return None
        raise
    return _money(body.get("wallet_balance")) or Decimal("0.00")


async def main_balance() -> Decimal:
    body = await _request("GET", "/api/wallet", key=_withdraw_key())
    return _money(body.get("wallet_balance", body.get("available"))) or Decimal("0.00")


async def withdraw(
    *, amount: Decimal, pix_key: str, pix_key_type: str, correlation_id: str,
    shop_ref: str | None = None, sub_shop_id: str | None = None,
) -> Payout:
    """Pix withdrawal from a subaccount (``shop_ref``) or the main wallet. One attempt
    only: a retry could move money twice (subaccounts are idempotent on correlation_id,
    the main wallet is not)."""
    body: dict = {"amount": float(amount.quantize(Decimal("0.01"))), "pix_key": pix_key, "pix_key_type": pix_key_type}
    if shop_ref:
        body.update({"correlation_id": correlation_id, "sub_shop_id": sub_shop_id or correlation_id})
        path = f"/api/shops/{shop_ref}/withdraw"
    else:
        path = "/api/withdrawals"
    return _payout(await _request("POST", path, body, key=_withdraw_key(), attempts=1))


async def withdrawals(shop_ref: str | None = None) -> list[Payout]:
    path = f"/api/shops/{shop_ref}/withdrawals?limit=50" if shop_ref else "/api/withdrawals?limit=50"
    body = await _request("GET", path, key=_withdraw_key())
    return [_payout(item) for item in body.get("withdrawals") or []]
