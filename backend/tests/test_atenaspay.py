from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.bots import atenaspay
from app.core.config import get_settings
from app.models import TgOrder
from tests.test_partners import _as
from tests.test_telegram_bots import _send, _signed, _setup, _start, _tap, apis


@pytest.mark.anyio
async def test_create_pix_uses_idempotent_subaccount_split_payload(monkeypatch, apis) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "atenaspay_api_key", SecretStr("smoke_test_key"))
    monkeypatch.setattr(settings, "atenaspay_webhook_secret", SecretStr("atenas_webhook_test"))
    charge = await atenaspay.create_pix(
        amount=Decimal("19.90"),
        external_id="tgo_123",
        description="Funil · Plano",
        webhook_url="https://flash.example/api/bots/pay/atenaspay",
        expiration_seconds=1800,
        shop_id="fp-workspace",
        splits=[{"parent": True, "amount": 0.4}],
    )
    payload = apis.methods("pix.create")[-1]
    assert payload["external_id"] == "tgo_123"
    assert payload["amount"] == 19.9
    assert payload["expiration"] == 1800
    assert payload["shop_id"] == "fp-workspace"
    assert payload["splits"] == [{"parent": True, "amount": 0.4}]
    assert charge.transaction_id == "tx-tgo_123"
    assert charge.copy_paste == "00020126PIXCODE"


@pytest.mark.anyio
async def test_atenaspay_failover_webhook_and_admin_release(
    client, db_session, owner, super_admin, monkeypatch, apis
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "atenaspay_api_key", SecretStr("smoke_test_key"))
    monkeypatch.setattr(settings, "atenaspay_webhook_secret", SecretStr("atenas_webhook_test"))
    monkeypatch.setattr(settings, "smokepay_api_key", None)

    admin = await _as(client, "superadmin@example.com", "super admin password")
    released = await client.put(
        "/api/payment-gateways/atenaspay/enabled",
        headers=admin,
        json={"enabled": True},
    )
    assert released.status_code == 200, released.text

    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))

    request = apis.methods("pix.create")[-1]
    assert request["shop_id"].startswith("fp-")
    assert request["splits"] == [{"parent": True, "amount": 0.4}]
    order = await db_session.scalar(select(TgOrder))
    assert order is not None
    assert order.gateway == "atenaspay"
    assert order.gateway_transaction_id == f"tx-tgo_{order.id}"
    assert order.shop_ref == request["shop_id"]

    raw, headers = _signed(
        {
            "event": "payment.confirmed",
            "transaction_id": order.gateway_transaction_id,
            "external_id": f"tgo_{order.id}",
            "status": "paid",
            "amount": float(order.amount),
            "fee": 1.0,
            "net_amount": float(order.amount) - 1.0,
            "payer_name": "Comprador",
        },
        secret="atenas_webhook_test",
    )
    invalid = await client.post(
        "/api/bots/pay/atenaspay",
        content=raw,
        headers={**headers, "x-webhook-signature": "t=1,v1=invalid"},
    )
    assert invalid.status_code == 401
    for _ in range(2):
        response = await client.post("/api/bots/pay/atenaspay", content=raw, headers=headers)
        assert response.status_code == 200, response.text
    await db_session.refresh(order)
    assert order.status == "paid"
    assert len(apis.methods("createChatInviteLink")) == 1
