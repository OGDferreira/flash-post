"""Stripe (card / international) client and webhook signature verification.

Stripe charges cards on a hosted Checkout page: the bot sends the buyer a link,
they pay there, and Stripe calls back ``checkout.session.completed``. Unlike the
Pix gateways there is no QR/copy-and-paste code — the sale carries a URL instead.

The money lands in the platform's Stripe account (no Stripe Connect split in this
version); each seller's share is tracked on the order like any other gateway and
paid out through the Flash withdrawal flow. The secret key and the webhook signing
secret come from the server env (STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET).
"""

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.bots import http
from app.core.config import get_settings


class StripeError(RuntimeError):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class CheckoutSession:
    session_id: str
    url: str


def _secret_key() -> str | None:
    key = get_settings().stripe_secret_key
    if key is None:
        return None
    value = key.get_secret_value().strip()
    return value or None


def _webhook_secret() -> str | None:
    secret = get_settings().stripe_webhook_secret
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    return value or None


def api_configured() -> bool:
    return _secret_key() is not None


def configured() -> bool:
    """Both the secret key and the webhook secret are set: a sale can be charged and confirmed."""
    return _secret_key() is not None and _webhook_secret() is not None


async def create_checkout_session(
    *, amount: Decimal, external_id: str, description: str, success_url: str, cancel_url: str
) -> CheckoutSession:
    """Create a hosted Checkout session for ``amount`` (BRL) and return its id and URL.

    ``external_id`` (the order ref) rides on the session and the payment intent metadata so
    the webhook can match the order. Amount is sent in cents, as Stripe expects.
    """
    key = _secret_key()
    if key is None:
        raise StripeError("Stripe não está configurada no servidor.")
    cents = int((Decimal(amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))
    if cents <= 0:
        raise StripeError("Valor inválido para cobrança no cartão.")
    data = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": external_id,
        "metadata[external_id]": external_id,
        "payment_intent_data[metadata][external_id]": external_id,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "brl",
        "line_items[0][price_data][unit_amount]": str(cents),
        "line_items[0][price_data][product_data][name]": (description or "Pedido")[:250],
        "payment_method_types[0]": "card",
    }
    url = f"{get_settings().stripe_base_url.rstrip('/')}/v1/checkout/sessions"
    try:
        async with http.client() as session:
            response = await session.post(
                url, data=data, headers={"Authorization": f"Bearer {key}"}
            )
    except httpx.HTTPError as exc:
        raise StripeError(f"Stripe fora do ar: {exc}") from exc
    if response.status_code >= 400:
        message = "Stripe recusou a cobrança."
        try:
            message = (response.json().get("error") or {}).get("message") or message
        except ValueError:
            pass
        raise StripeError(message, status=response.status_code)
    body = response.json()
    checkout_url = body.get("url")
    session_id = body.get("id")
    if not checkout_url or not session_id:
        raise StripeError("Stripe não devolveu o link de pagamento.")
    return CheckoutSession(session_id=str(session_id), url=str(checkout_url))


def verify_signature(payload: bytes, signature_header: str | None, *, tolerance: int = 300) -> bool:
    """Validate the ``Stripe-Signature`` header against the webhook secret.

    Stripe signs ``f"{t}.{raw_body}"`` with HMAC-SHA256. The header is
    ``t=<ts>,v1=<sig>[,v1=<sig>...]``; any v1 matching is enough.
    """
    secret = _webhook_secret()
    if not signature_header or not secret:
        return False
    timestamp: str | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if not timestamp or not signatures:
        return False
    try:
        if abs(time.time() - int(timestamp)) > tolerance:
            return False
    except ValueError:
        return False
    signed = timestamp.encode() + b"." + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)
