"""SnakePay PIX client and webhook signature check.

API (docs shared by the platform owner, 2026-10):
* ``POST /charges`` ``{amount (reais), external_reference, payer?, split?}`` →
  ``{id, qrcode, net_amount (centavos), ...}``. Not idempotent: never retried.
* ``GET /charges/:id`` → ``{id, status, amount, net_amount, paid_at, split?, owner_amount?}``
  (amounts in centavos).
* Webhook ``POST`` with ``X-SnakePay-Signature: sha256=<hex>`` = HMAC-SHA256 of the raw
  body with the webhook secret; body ``{id, type: pix.paid|pix.expired|pix.failed,
  data: {charge_id, amount, net_amount, status, ...}}``. No automatic redelivery: the
  "Já paguei" button and the reconciliation job ask ``GET /charges/:id``.
* Split: ``[{recipient_id, percentage}]`` over the net (after 3% + R$ 0,25), up to 10
  accounts summing at most 100%; the rest stays in the key owner's account.
"""

import asyncio
import hashlib
import hmac
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal

import httpx

from app.bots import http
from app.core.config import get_settings

CENT = Decimal("0.01")
FEE_PERCENT = Decimal("3")
FEE_FIXED = Decimal("0.25")


class SnakepayError(RuntimeError):
    def __init__(self, message: str, status: int = 0, detail: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


class SnakepayNotConfigured(SnakepayError):
    pass


@dataclass
class SnakeCharge:
    charge_id: str
    status: str
    amount: Decimal | None
    net_amount: Decimal | None
    copy_paste: str | None
    owner_amount: Decimal | None = None
    split_amounts: dict[str, Decimal] | None = None  # recipient_id -> amount


def configured() -> bool:
    settings = get_settings()
    return bool(
        settings.snakepay_api_key and settings.snakepay_api_key.get_secret_value().strip()
        and settings.snakepay_webhook_secret and settings.snakepay_webhook_secret.get_secret_value().strip()
    )


def _api_key(api_key: str | None = None) -> str:
    if api_key is not None and api_key.strip():
        return api_key.strip()
    key = get_settings().snakepay_api_key
    if key is None or not key.get_secret_value().strip():
        raise SnakepayNotConfigured("SNAKEPAY_API_KEY is not configured.")
    return key.get_secret_value().strip()


def _cents(value: object) -> Decimal | None:
    """SnakePay returns money in centavos."""
    if value is None or value == "":
        return None
    try:
        return (Decimal(str(value)) / 100).quantize(CENT)
    except Exception:
        return None


def expected_net(amount: Decimal) -> Decimal:
    """Net after SnakePay's fee (3% + R$ 0,25), used before the charge answers."""
    return (amount - (amount * FEE_PERCENT / 100).quantize(CENT, ROUND_UP) - FEE_FIXED).quantize(CENT)


def share(net: Decimal, percentage: Decimal) -> Decimal:
    """A split payout: SnakePay rounds each one down to the centavo."""
    return (net * percentage / 100).quantize(CENT, ROUND_DOWN)


def _charge(data: dict) -> SnakeCharge:
    splits = data.get("split") if isinstance(data.get("split"), list) else []
    amounts = {
        str(item.get("recipient_id")): _cents(item.get("amount"))
        for item in splits
        if isinstance(item, dict) and item.get("recipient_id") and item.get("amount") is not None
    }
    return SnakeCharge(
        charge_id=str(data.get("id") or data.get("charge_id") or ""),
        status=str(data.get("status") or "pending"),
        amount=_cents(data.get("amount")),
        net_amount=_cents(data.get("net_amount")),
        copy_paste=data.get("qrcode") or data.get("pix_copia_cola") or data.get("copy_paste"),
        owner_amount=_cents(data.get("owner_amount")),
        split_amounts={k: v for k, v in amounts.items() if v is not None} or None,
    )


async def _request(
    method: str, path: str, json_body: dict | None = None, *, api_key: str | None = None, attempts: int = 3
) -> dict:
    url = f"{get_settings().snakepay_base_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    headers["Authorization"] = "Bearer " + _api_key(api_key)
    last: SnakepayError | None = None
    for attempt in range(attempts):
        if attempt:
            await asyncio.sleep(2 ** attempt)
        try:
            async with http.client(20.0) as session:
                response = await session.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            last = SnakepayError(f"SnakePay unreachable ({type(exc).__name__}).")
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            last = SnakepayError(f"SnakePay HTTP {response.status_code}.", response.status_code)
            continue
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        if response.is_error:
            raw = body.get("error") or body.get("message") or ""
            detail = str(raw.get("message") if isinstance(raw, dict) else raw)[:200]
            raise SnakepayError(f"SnakePay HTTP {response.status_code}: {detail}", response.status_code, detail)
        return body
    assert last is not None
    raise last


async def create_charge(
    *,
    amount: Decimal,
    external_reference: str,
    split: list[dict] | None = None,
    api_key: str | None = None,
) -> SnakeCharge:
    """One attempt only: the endpoint has no idempotency key, so a retry could create a
    second charge. ``split`` = ``[{"recipient_id": ..., "percentage": 12.5}]``."""
    payload: dict = {"amount": float(amount.quantize(CENT)), "external_reference": external_reference[:64]}
    if split:
        payload["split"] = split
    body = await _request("POST", "/charges", payload, api_key=api_key, attempts=1)
    charge = _charge(body.get("charge") if isinstance(body.get("charge"), dict) else body)
    if not charge.charge_id or not charge.copy_paste:
        raise SnakepayError("SnakePay answered without the Pix code.")
    return charge


async def get_charge(charge_id: str, *, api_key: str | None = None) -> SnakeCharge:
    body = await _request("GET", f"/charges/{charge_id}", api_key=api_key)
    return _charge(body.get("charge") if isinstance(body.get("charge"), dict) else body)


def alternate_recipient(value: str) -> str:
    """The other spelling of a ShopID: ``snakepay_<32 hex>`` <-> dashed UUID."""
    value = value.strip()
    if value.lower().startswith("snakepay_"):
        h = value[9:].lower()
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}" if len(h) == 32 else value
    bare = value.replace("-", "").lower()
    return f"snakepay_{bare}" if len(bare) == 32 else value


def verify_signature(raw_body: bytes, header: str | None, *, secret: str | None = None) -> bool:
    """``X-SnakePay-Signature: sha256=<hex HMAC-SHA256(raw body, webhook secret)>``."""
    if secret is None:
        configured_secret = get_settings().snakepay_webhook_secret
        secret = configured_secret.get_secret_value() if configured_secret else None
    if secret is None or not secret.strip() or not header:
        return False
    received = header.strip()
    if received.lower().startswith("sha256="):
        received = received[7:]
    expected = hmac.new(secret.strip().encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received.strip().lower())
