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


async def _request(method: str, path: str, json_body: dict | None = None) -> dict:
    url = f"{get_settings().smokepay_base_url.rstrip('/')}{path}"
    headers = {"x-api-key": _api_key(), "Content-Type": "application/json"}
    last: SmokepayError | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            await asyncio.sleep(2 ** attempt)
        try:
            async with http.client(20.0) as session:
                response = await session.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            last = SmokepayError(f"SmokePay unreachable ({type(exc).__name__}).")
            continue
        if response.status_code in (429, 500, 502, 503, 504):
            last = SmokepayError(f"SmokePay HTTP {response.status_code}.", response.status_code)
            continue
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.is_error:
            detail = str(body.get("error") or body.get("message") or "")[:200]
            raise SmokepayError(f"SmokePay HTTP {response.status_code}: {detail}", response.status_code)
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
