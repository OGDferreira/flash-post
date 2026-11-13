import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.bots import stripe_gateway
from app.core.config import get_settings
from app.models import TgOrder
from tests.test_partners import _as
from tests.test_telegram_bots import _send, _setup, _start, _tap, apis


def _stripe_headers(raw: bytes, secret: str = "stripe_webhook_test") -> dict:
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}


def test_verify_signature_accepts_valid_and_rejects_tampered(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_webhook_secret", SecretStr("stripe_webhook_test"))
    raw = b'{"type":"checkout.session.completed"}'
    headers = _stripe_headers(raw)
    assert stripe_gateway.verify_signature(raw, headers["stripe-signature"]) is True
    assert stripe_gateway.verify_signature(raw + b"x", headers["stripe-signature"]) is False
    assert stripe_gateway.verify_signature(raw, "t=1,v1=deadbeef") is False
    assert stripe_gateway.verify_signature(raw, None) is False


@pytest.mark.anyio
async def test_create_checkout_session_sends_cents_and_metadata(monkeypatch, apis) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", SecretStr("stripe_test_key"))
    monkeypatch.setattr(settings, "stripe_webhook_secret", SecretStr("stripe_webhook_test"))
    session = await stripe_gateway.create_checkout_session(
        amount=Decimal("19.90"), external_id="tgo_abc", description="Funil · Plano",
        success_url="https://t.me/ana_vip_bot", cancel_url="https://t.me/ana_vip_bot",
    )
    body = apis.methods("stripe.checkout")[-1]
    assert body["line_items[0][price_data][unit_amount]"] == "1990"
    assert body["line_items[0][price_data][currency]"] == "brl"
    assert body["metadata[external_id]"] == "tgo_abc"
    assert session.session_id == "cs_tgo_abc"
    assert session.url == "https://checkout.stripe.com/pay/cs_tgo_abc"


@pytest.mark.anyio
async def test_stripe_charge_link_webhook_and_admin_release(
    client, db_session, owner, super_admin, monkeypatch, apis
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", SecretStr("stripe_test_key"))
    monkeypatch.setattr(settings, "stripe_webhook_secret", SecretStr("stripe_webhook_test"))

    admin = await _as(client, "superadmin@example.com", "super admin password")
    released = await client.put("/api/payment-gateways/stripe/enabled", headers=admin, json={"enabled": True})
    assert released.status_code == 200, released.text

    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    bot, _ = await _setup(client, headers)
    # The seller puts Stripe (card) as the principal gateway for the operation.
    priority = await client.put(
        "/api/payment-gateways/priority", headers=headers,
        json={"items": [
            {"gateway": "stripe", "enabled": True, "flow_ids": None},
            {"gateway": "smokepay", "enabled": True, "flow_ids": None},
        ]},
    )
    assert priority.status_code == 200, priority.text

    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))

    checkout = apis.methods("stripe.checkout")[-1]
    assert checkout["line_items[0][price_data][unit_amount]"] == "1990"
    order = await db_session.scalar(select(TgOrder))
    assert order is not None
    assert order.gateway == "stripe"
    assert order.gateway_transaction_id == f"cs_tgo_{order.id}"
    assert order.pix_copy_paste == f"https://checkout.stripe.com/pay/cs_tgo_{order.id}"
    # The bot sent the card link (no Pix code).
    links = [b.get("reply_markup", {}) for m, b in apis.calls if m == "sendMessage"]
    assert any(
        btn.get("url", "").startswith("https://checkout.stripe.com/")
        for markup in links for row in markup.get("inline_keyboard", []) for btn in row
    )

    raw = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {
            "payment_status": "paid",
            "amount_total": int(order.amount * 100),
            "metadata": {"external_id": f"tgo_{order.id}"},
        }},
    }).encode()
    invalid = await client.post("/api/bots/pay/stripe", content=raw, headers={"stripe-signature": "t=1,v1=bad"})
    assert invalid.status_code == 401
    for _ in range(2):  # idempotent: a retry delivers once
        response = await client.post("/api/bots/pay/stripe", content=raw, headers=_stripe_headers(raw))
        assert response.status_code == 200, response.text
    await db_session.refresh(order)
    assert order.status == "paid"
    assert len(apis.methods("createChatInviteLink")) == 1
