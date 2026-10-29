"""Athenas Pay PIX client and webhook signature verification."""

import asyncio
import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx

from app.bots import http
from app.core.config import get_settings


class AtenaspayError(RuntimeError):
    def __init__(
        self, message: str, status: int = 0, cooldown_seconds: int | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.cooldown_seconds = cooldown_seconds


class AtenaspayNotConfigured(AtenaspayError):
    pass


@dataclass
class PixCharge:
    transaction_id: str
    status: str
    amount: Decimal | None
    fee: Decimal | None
    net_amount: Decimal | None
    copy_paste: str | None
    qr_code_base64: str | None
    expires_at: str | None
    split_total: Decimal | None
    owner_net: Decimal | None
    payer_name: str | None = None


def configured() -> bool:
    settings = get_settings()
    return bool(
        api_configured()
        and settings.atenaspay_webhook_secret
        and settings.atenaspay_webhook_secret.get_secret_value().strip()
    )


def api_configured() -> bool:
    key = get_settings().atenaspay_api_key
    return bool(key and key.get_secret_value().strip())


def _api_key() -> str:
    key = get_settings().atenaspay_api_key
    if key is None or not key.get_secret_value().strip():
        raise AtenaspayNotConfigured("ATENASPAY_API_KEY is not configured.")
    return key.get_secret_value().strip()


def _money(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
        return amount.quantize(Decimal("0.01")) if amount.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _charge(data: dict) -> PixCharge:
    preview = data.get("splits_preview")
    split_items = preview.get("splits", []) if isinstance(preview, dict) else []
    split_amounts = [
        amount
        for item in split_items
        if isinstance(item, dict) and (amount := _money(item.get("amount"))) is not None
    ]
    return PixCharge(
        transaction_id=str(data.get("id") or data.get("transaction_id") or ""),
        status=str(data.get("status") or "pending"),
        amount=_money(data.get("amount")),
        fee=_money(data.get("fee")),
        net_amount=_money(data.get("net_amount")),
        copy_paste=data.get("pix_copia_cola"),
        qr_code_base64=data.get("qr_code_base64"),
        expires_at=data.get("expires_at"),
        split_total=sum(split_amounts, Decimal("0.00")) if split_amounts else None,
        owner_net=_money(preview.get("owner_net_amount")) if isinstance(preview, dict) else None,
        payer_name=data.get("payer_name"),
    )


def _payload(body: dict) -> dict:
    transaction = body.get("transaction")
    if isinstance(transaction, dict):
        return transaction
    return body


async def _request(method: str, path: str, json_body: dict | None = None, attempts: int = 3) -> dict:
    settings = get_settings()
    url = f"{settings.atenaspay_base_url.rstrip('/')}{path}"
    headers = {"x-api-key": _api_key(), "Content-Type": "application/json"}
    last: AtenaspayError | None = None
    for attempt in range(attempts):
        if attempt:
            await asyncio.sleep(2**attempt)
        try:
            async with http.client(20.0) as session:
                response = await session.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            last = AtenaspayError(f"Athenas Pay unreachable ({type(exc).__name__}).")
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            last = AtenaspayError(f"Athenas Pay HTTP {response.status_code}.", response.status_code)
            continue
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        if response.is_error:
            detail = str(body.get("error") or body.get("message") or "")[:200]
            cooldown = body.get("cooldown_seconds")
            raise AtenaspayError(
                f"Athenas Pay HTTP {response.status_code}: {detail}",
                response.status_code,
                cooldown if isinstance(cooldown, int) and not isinstance(cooldown, bool) else None,
            )
        return body
    assert last is not None
    raise last


async def create_pix(
    *,
    amount: Decimal,
    external_id: str,
    description: str,
    webhook_url: str,
    expiration_seconds: int,
    shop_id: str | None = None,
    splits: list[dict] | None = None,
) -> PixCharge:
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
    charge = _charge(_payload(await _request("POST", "/api/pix/create", payload)))
    if not charge.transaction_id or not charge.copy_paste:
        raise AtenaspayError("Athenas Pay answered without a transaction id or Pix code.")
    return charge


async def get_pix(identifier: str) -> PixCharge:
    return _charge(_payload(await _request("GET", f"/api/pix/{quote(identifier, safe='')}")))


@dataclass
class ShopPayout:
    withdrawal_id: str
    amount: Decimal
    fee: Decimal | None
    status: str
    failure_reason: str | None = None
    e2e_id: str | None = None
    pix_key: str | None = None
    pix_key_type: str | None = None
    processed_at: str | None = None


def _payout(data: dict) -> ShopPayout:
    return ShopPayout(
        withdrawal_id=str(data.get("withdrawal_id") or data.get("id") or ""),
        amount=_money(data.get("amount")) or Decimal("0.00"),
        fee=_money(data.get("fee")),
        status=str(data.get("status") or "processing").lower(),
        failure_reason=data.get("failure_reason"),
        e2e_id=data.get("gateway_e2eid") or data.get("e2e_id"),
        pix_key=data.get("pix_key"),
        pix_key_type=data.get("pix_key_type"),
        processed_at=data.get("processed_at"),
    )


async def _shop_id(shop_ref: str) -> str:
    body = await _request("GET", f"/api/shops/{quote(shop_ref, safe='')}")
    shop = body.get("shop")
    shop_id = shop.get("id") if isinstance(shop, dict) else None
    if not isinstance(shop_id, (str, int)) or not str(shop_id):
        raise AtenaspayError("Athenas Pay returned an invalid subaccount response.")
    return str(shop_id)


async def shop_balance(shop_ref: str) -> Decimal | None:
    try:
        shop_id = await _shop_id(shop_ref)
    except AtenaspayError as exc:
        if exc.status == 404:
            return None
        raise
    try:
        body = await _request("GET", f"/api/shops/{quote(shop_id, safe='')}/balance")
    except AtenaspayError as exc:
        if exc.status == 404:
            return None
        raise
    balance = body.get("wallet_balance")
    return _money(balance) if balance is not None else Decimal("0.00")


async def withdraw_shop(
    *,
    shop_ref: str,
    amount: Decimal,
    pix_key: str,
    pix_key_type: str,
    correlation_id: str,
    sub_shop_id: str,
) -> ShopPayout:
    shop_id = await _shop_id(shop_ref)
    body = await _request(
        "POST",
        f"/api/shops/{quote(shop_id, safe='')}/withdraw",
        {
            "amount": float(amount.quantize(Decimal("0.01"))),
            "pix_key": pix_key,
            "pix_key_type": pix_key_type,
            "correlation_id": correlation_id,
            "sub_shop_id": sub_shop_id,
        },
    )
    payout = _payout(body)
    if not payout.withdrawal_id:
        raise AtenaspayError("Athenas Pay answered without a withdrawal id.")
    return payout


async def shop_withdrawals(shop_ref: str) -> list[ShopPayout]:
    shop_id = await _shop_id(shop_ref)
    body = await _request(
        "GET",
        f"/api/shops/{quote(shop_id, safe='')}/withdrawals?page=1&limit=100",
    )
    items = body.get("withdrawals")
    if not isinstance(items, list):
        raise AtenaspayError("Athenas Pay returned an invalid withdrawals response.")
    return [_payout(item) for item in items if isinstance(item, dict)]


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    secret = get_settings().atenaspay_webhook_secret
    if secret is None or not secret.get_secret_value().strip() or not header:
        return False
    fields = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    timestamp, received = fields.get("t", ""), fields.get("v1", "")
    if not timestamp.isdigit() or not received:
        return False
    expected = hmac.new(
        secret.get_secret_value().strip().encode(),
        timestamp.encode() + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, received.lower())
