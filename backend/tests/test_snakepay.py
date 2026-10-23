"""SnakePay: gateway choice, split to the seller's (and chief's) account, webhook, fallback."""

import hashlib
import hmac
import json
import uuid
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.bots import engine, gateways, snakepay
from app.core.config import get_settings
from app.models import TgFlow, TgOrder, Workspace
from tests.test_partners import CHIEF_PASSWORD, _as, _chief_shares_funnel, _partner
from tests.test_telegram_bots import TOKEN, _send, _setup, _start, _tap, apis  # noqa: F401

SECRET = "whsec_snake_test"
SELLER = "11111111-2222-3333-4444-555555555555"
CHIEF = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def snake(apis, monkeypatch):
    """Answers SnakePay on https://snake.test like its docs describe (centavos)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "snakepay_api_key", SecretStr("sk_live_test"))
    monkeypatch.setattr(settings, "snakepay_webhook_secret", SecretStr(SECRET))
    monkeypatch.setattr(settings, "snakepay_base_url", "https://snake.test/api/public/v1")
    state = {"fail": False, "refuse": False, "status": "pending", "charges": {}, "uuid_only": False}
    smoke = apis.handler

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/shops/" in url or url.endswith("/api/wallet"):
            return httpx.Response(404, json={"error": "not found"})  # no SmokePay subaccount yet
        if "snake.test" not in url:
            return smoke(request)
        apis.calls.append(("snake.auth", {"authorization": request.headers["authorization"]}))
        assert request.headers["authorization"].startswith("Bearer ")
        if request.method == "POST" and url.endswith("/charges"):
            body = json.loads(request.content)
            apis.calls.append(("snake.create", body))
            if state["fail"]:
                return httpx.Response(422, json={"error": "payer.document is required"})
            if state["refuse"]:
                return httpx.Response(400, json={"error": "Dados inválidos (confira o ShopID dos recebedores)"})
            if state["uuid_only"] and any(item["recipient_id"].startswith("snakepay_") for item in body.get("split", [])):
                return httpx.Response(400, json={"error": "Dados inválidos (confira o ShopID dos recebedores)"})
            cents = round(body["amount"] * 100)
            net = snakepay.expected_net(Decimal(str(body["amount"])))
            split = [
                {"recipient_id": item["recipient_id"], "percentage": item["percentage"],
                 "amount": int(snakepay.share(net, Decimal(str(item["percentage"]))) * 100), "status": "pending"}
                for item in body.get("split", [])
            ]
            charge = {"id": f"in_{len(state['charges']) + 1}", "qrcode": "00020126SNAKEPIX", "amount": cents,
                      "net_amount": int(net * 100), "split": split, "status": "pending"}
            state["charges"][charge["id"]] = charge
            return httpx.Response(201, json=charge)
        charge_id = url.rsplit("/", 1)[-1]
        apis.calls.append(("snake.get", {"id": charge_id}))
        return httpx.Response(200, json={**state["charges"][charge_id], "status": state["status"]})

    from app.bots import http

    http.set_transport(httpx.MockTransport(handler))
    return state


def _event(charge: dict, secret: str = SECRET) -> tuple[bytes, dict]:
    raw = json.dumps({"id": "evt_1", "type": "pix.paid", "data": {
        "charge_id": charge["id"], "amount": charge["amount"], "net_amount": charge["net_amount"], "status": "paid",
    }}).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-SnakePay-Signature": f"sha256={sig}", "Content-Type": "application/json"}


async def _enable(client) -> None:
    admin = await _as(client, "superadmin@example.com", "super admin password")
    response = await client.put("/api/payment-gateways/snakepay/enabled", headers=admin, json={"enabled": True})
    assert response.status_code == 200, response.text


def test_signature_and_net_math(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "snakepay_webhook_secret", SecretStr(SECRET))
    raw = b'{"type":"pix.paid"}'
    good = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert snakepay.verify_signature(raw, good)
    assert not snakepay.verify_signature(raw + b" ", good)
    assert not snakepay.verify_signature(raw, None)
    # docs example: R$ 100,00 -> net 96,75; 30% -> 29,02 (rounded down)
    assert snakepay.expected_net(Decimal("100.00")) == Decimal("96.75")
    assert snakepay.share(Decimal("96.75"), Decimal("30")) == Decimal("29.02")
    assert gateways.valid_recipient(SELLER) and not gateways.valid_recipient("ana@example.com")


@pytest.mark.anyio
async def test_partner_sale_splits_to_the_partner_account_and_webhook_approves_once(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    partner, partner_ws, _ = await _partner(db_session, owner, accepted=True)
    headers = await _as(client, "socio@example.com")
    # not released by the Super Admin yet
    early = await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": SELLER})
    assert early.status_code == 409
    admin = await _as(client, "superadmin@example.com", "super admin password")
    assert (await client.put("/api/admin/platform-fee", headers=admin, json={"type": "fixed", "value": "1.00"})).status_code == 200
    await _enable(client)

    headers = await _as(client, "socio@example.com")
    state = (await client.get("/api/payment-gateways")).json()
    assert [g["id"] for g in state["gateways"] if g["available"]] == ["smokepay", "snakepay"]
    fees = {g["id"]: g["fee"] for g in state["gateways"]}
    assert fees["snakepay"].startswith("3% + R$ 0,25") and "saque R$ 3,00" in fees["smokepay"]
    assert "admin" not in state  # the webhook URL and key status are for the Super Admin only
    missing = await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay"})
    assert missing.status_code == 422
    bad = await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": "meu-email"})
    assert bad.status_code == 422
    chosen = await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": SELLER})
    assert chosen.status_code == 200 and chosen.json()["current"] == "snakepay"

    bot, _ = await _setup(client, headers)  # the partner's own funnel: platform fee only
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert not apis.methods("pix.create")  # SmokePay was not called
    created = apis.methods("snake.create")[-1]
    # net 19.05 (19.90 - 0.60 - 0.25); fee R$ 1,00 = 5.25% of it; the partner gets the rest
    assert created["amount"] == 19.9 and created["split"] == [{"recipient_id": SELLER, "percentage": 94.75}]
    assert "payer" not in created
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.gateway == "snakepay" and order.gateway_transaction_id == "in_1" and order.shop_ref is None
    assert order.net_amount == Decimal("19.05") and order.gateway_fee == Decimal("0.85")
    assert order.partner_net == Decimal("18.04") and order.platform_fee == Decimal("1.01")

    raw, sig = _event(snake["charges"]["in_1"])
    assert (await client.post("/api/bots/pay/snakepay", content=raw, headers={**sig, "X-SnakePay-Signature": "sha256=00"})).status_code == 401
    for _ in range(2):  # a repeated notice never pays twice
        assert (await client.post("/api/bots/pay/snakepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "paid"
    assert len([1 for m, b in apis.calls if m == "createChatInviteLink"]) == 1

    # SnakePay pays the partner directly: the FlashPost (SmokePay) wallet does not count it
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["available"] == 0.0 and wallet["snakepay_received"] == 18.04
    assert wallet["snakepay_sales"] == 18.04 and wallet["snakepay_fees"] == 0.0

    # the platform owner sees the fee that stayed in the charging account, apart from their sales;
    # their FlashPost revenue is still only their own sales
    chief, _ = owner
    chief.platform_role = "SUPER_ADMIN"
    await db_session.commit()
    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["snakepay_fees"] == 1.01 and wallet["snakepay_sales"] == 0.0 and wallet["snakepay_received"] == 1.01
    assert wallet["month_revenue"] == 0.0


@pytest.mark.anyio
async def test_shared_funnel_follows_the_chief_gateway_and_splits_the_commission(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    partner, partner_ws, _ = await _partner(db_session, owner, accepted=True)
    await _enable(client)
    flow_id = await _chief_shares_funnel(client, db_session, chief_ws)
    # the chief picks SnakePay; the partner's own operation stays on SmokePay, with no ShopID
    chief_headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    assert (await client.put("/api/payment-gateways", headers=chief_headers, json={"gateway": "snakepay", "snakepay_recipient_id": CHIEF})).status_code == 200
    headers = await _as(client, "socio@example.com")

    # a shared SnakePay funnel needs the seller's own SnakePay key: without it the funnel is locked
    blocked = await client.post("/api/bots", headers=headers, json={"token": TOKEN, "flow_id": flow_id})
    assert blocked.status_code == 409 and "SnakePay" in blocked.text
    assert (await client.get("/api/payment-gateways")).json()["current"] == "smokepay"

    # the partner saves their own SnakePay key: the charge is created in their account
    assert (await client.put("/api/payment-gateways/snakepay/credentials", headers=headers,
                             json={"api_key": "seller_sk_test", "webhook_secret": "seller_webhook_test"})).status_code == 200
    bot = (await client.post("/api/bots", headers=headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert not apis.methods("pix.create")
    created = apis.methods("snake.create")[-1]
    assert created["split"] == [{"recipient_id": CHIEF, "percentage": 30.0}]  # only the chief's commission goes out
    assert [call[1]["authorization"] for call in apis.calls if call[0] == "snake.auth"] == ["Bearer seller_sk_test"]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder).where(TgOrder.gateway == "snakepay"))
    # net 19.05: chief 30% = 5.71, partner keeps the rest
    assert order.split_chief_user_id == chief.id and order.split_amount == Decimal("5.71") and order.partner_net == Decimal("13.34")


@pytest.mark.anyio
async def test_partner_account_key_keeps_sale_in_seller_account_and_splits_only_chief(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    partner, partner_ws, _ = await _partner(db_session, owner, accepted=True)
    await _enable(client)
    flow_id = await _chief_shares_funnel(client, db_session, chief_ws)

    chief_headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    assert (
        await client.put(
            "/api/payment-gateways",
            headers=chief_headers,
            json={"gateway": "snakepay", "snakepay_recipient_id": CHIEF},
        )
    ).status_code == 200
    seller_headers = await _as(client, "socio@example.com")
    credentials = await client.put(
        "/api/payment-gateways/snakepay/credentials",
        headers=seller_headers,
        json={"api_key": "seller_sk_test", "webhook_secret": "seller_webhook_test"},
    )
    assert credentials.status_code == 200
    assert credentials.json()["snakepay_account_key_set"] and credentials.json()["snakepay_account_secret_set"]
    assert "seller_sk_test" not in credentials.text and "seller_webhook_test" not in credentials.text

    seller_headers = await _as(client, "socio@example.com")
    bot = (await client.post("/api/bots", headers=seller_headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    created = apis.methods("snake.create")[-1]
    assert created["amount"] == 19.9
    assert created["split"] == [{"recipient_id": CHIEF, "percentage": 30.0}]
    assert ("snake.auth", {"authorization": "Bearer seller_sk_test"}) in apis.calls
    assert partner_ws.snakepay_recipient_id is None
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder).where(TgOrder.gateway == "snakepay"))
    assert order.workspace_id == partner_ws.id
    assert order.snakepay_api_key_encrypted != "seller_sk_test"
    await engine.check_order(db_session, order)
    assert ("snake.auth", {"authorization": "Bearer seller_sk_test"}) in apis.calls

    invalid_raw, invalid_sig = _event(snake["charges"]["in_1"])
    assert (await client.post("/api/bots/pay/snakepay", content=invalid_raw, headers=invalid_sig)).status_code == 401
    raw, sig = _event(snake["charges"]["in_1"], "seller_webhook_test")
    assert (await client.post("/api/bots/pay/snakepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "paid" and order.split_amount == Decimal("5.71")
    assert order.partner_net == Decimal("13.34")


@pytest.mark.anyio
async def test_snakepay_refusal_falls_back_to_smokepay_and_check_button_asks_snakepay(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    await _enable(client)
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": SELLER})
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    snake["fail"] = True
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert apis.methods("snake.create") and apis.methods("pix.create")  # tried SnakePay, sold with SmokePay
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.gateway == "smokepay" and order.status == "pending"

    # with SnakePay working, "Já paguei" asks SnakePay for its own charges
    snake["fail"] = False
    order.status = "expired"
    await db_session.commit()
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await db_session.commit()
    snake_order = await db_session.scalar(select(TgOrder).where(TgOrder.gateway == "snakepay"))
    snake["status"] = "paid"
    from app.bots import engine

    await engine.check_order(db_session, snake_order)
    await db_session.refresh(snake_order)
    assert snake_order.status == "paid" and apis.methods("snake.get")


@pytest.mark.anyio
async def test_refused_shop_id_pauses_snakepay_until_the_settings_change(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    from app.bots import engine

    engine.resume_snakepay()
    await _enable(client)
    partner, partner_ws, _ = await _partner(db_session, owner, accepted=True)
    headers = await _as(client, "socio@example.com")
    await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": SELLER})
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    snake["refuse"] = True

    async def new_pix() -> None:
        await db_session.commit()
        for order in await db_session.scalars(select(TgOrder)):
            order.status = "expired"
        await db_session.commit()
        await _send(client, db_session, bot["id"], _tap("plan:vip"))

    await new_pix()
    tries = len(apis.methods("snake.create"))
    assert tries == 2 and len(apis.methods("pix.create")) == 1  # both ShopID spellings refused, SmokePay sold
    await new_pix()
    assert len(apis.methods("snake.create")) == tries and len(apis.methods("pix.create")) == 2  # straight to SmokePay

    # saving the gateway settings (a corrected ShopID) gives SnakePay a fresh try at once
    snake["refuse"] = False
    await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": SELLER})
    await new_pix()
    assert len(apis.methods("snake.create")) == tries + 1 and len(apis.methods("pix.create")) == 2


@pytest.mark.anyio
async def test_only_super_admin_releases_snakepay_and_only_when_configured(client, db_session, owner, super_admin, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "snakepay_api_key", None)
    admin = await _as(client, "superadmin@example.com", "super admin password")
    refused = await client.put("/api/payment-gateways/snakepay/enabled", headers=admin, json={"enabled": True})
    assert refused.status_code == 409 and "SNAKEPAY_API_KEY" in refused.json()["detail"]
    owner_headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    forbidden = await client.put("/api/payment-gateways/snakepay/enabled", headers=owner_headers, json={"enabled": True})
    assert forbidden.status_code == 403


@pytest.mark.anyio
async def test_gateway_per_funnel_or_for_all(client, db_session, owner, super_admin, snake, apis) -> None:
    chief, _ = owner
    chief.platform_role = "SUPER_ADMIN"  # only the Super Admin chooses/orders gateways
    await db_session.commit()
    await _enable(client)
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    # default stays SmokePay; only this funnel uses SnakePay
    saved = await client.put("/api/payment-gateways", headers=headers, json={"gateway": "smokepay", "snakepay_recipient_id": SELLER})
    assert saved.status_code == 200
    bot, flow = await _setup(client, headers)
    one = await client.put(f"/api/payment-gateways/flows/{flow['id']}", headers=headers, json={"gateway": "snakepay"})
    assert one.status_code == 200 and one.json()["flows"][0]["gateway"] == "snakepay"
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert apis.methods("snake.create") and not apis.methods("pix.create")

    # "all funnels": the default wins again
    everyone = await client.put(
        "/api/payment-gateways", headers=headers, json={"gateway": "smokepay", "snakepay_recipient_id": SELLER, "apply_to_all": True}
    )
    assert everyone.json()["flows"][0]["gateway"] is None
    await db_session.commit()
    for order in await db_session.scalars(select(TgOrder)):
        order.status = "expired"
    await db_session.commit()
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert apis.methods("pix.create")

    other_flow = await client.put("/api/payment-gateways/flows/00000000-0000-0000-0000-000000000000", headers=headers, json={"gateway": None})
    assert other_flow.status_code == 404


@pytest.mark.anyio
async def test_regular_user_never_picks_a_gateway_snakepay_first_smokepay_backup(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner  # a regular USER, not the Super Admin
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    bot, flow = await _setup(client, headers)
    workspace = await db_session.get(Workspace, chief_ws.id)
    flow_row = await db_session.get(TgFlow, uuid.UUID(flow["id"]))

    # SnakePay not released by the admin yet: SmokePay only.
    assert await gateways.gateway_order(db_session, workspace, flow_row) == ["smokepay"]

    # Released: SnakePay is the principal and SmokePay the automatic backup — the user chose nothing.
    await _enable(client)
    assert await gateways.gateway_order(db_session, workspace, flow_row) == ["snakepay", "smokepay"]

    # Without a SnakePay ShopID the sale still goes through SmokePay (SnakePay cannot charge).
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert apis.methods("pix.create") and not apis.methods("snake.create")

    # With a ShopID saved, SnakePay charges it, splitting to the user's account.
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    assert (await client.put("/api/payment-gateways", headers=headers,
                             json={"gateway": "smokepay", "snakepay_recipient_id": SELLER})).status_code == 200
    await db_session.commit()
    for order in await db_session.scalars(select(TgOrder)):
        order.status = "expired"
    await db_session.commit()
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert apis.methods("snake.create")


def test_recipient_accepts_the_snakepay_shop_id() -> None:
    assert gateways.valid_recipient("snakepay_6fde14d647ba4acbb45855490d22f435")
    assert not gateways.valid_recipient("snakepay_xyz")


@pytest.mark.anyio
async def test_smokepay_fee_shows_the_real_average(client, db_session, owner) -> None:
    from app.bots.gateways_router import _smokepay_fee_text
    from tests.test_wallet import _paid

    _, workspace = owner
    await _paid(db_session, workspace)  # 19.90 with R$ 1,00 fee
    assert await _smokepay_fee_text(db_session) == "≈ 5,0% por venda (média das últimas vendas) · saque R$ 3,00"


PLATFORM = "snakepay_6fde14d647ba4acbb45855490d22f435"
PARTNER_SHOP = "snakepay_0123456789abcdef0123456789abcdef"


@pytest.mark.anyio
async def test_platform_shop_id_never_goes_in_the_split_and_other_format_is_retried(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    chief.platform_role = "SUPER_ADMIN"  # the platform owner, whose key charges the sales
    chief_ws.snakepay_recipient_id = PLATFORM
    await db_session.commit()
    partner, partner_ws, _ = await _partner(db_session, owner, accepted=True)
    await _enable(client)

    headers = await _as(client, "socio@example.com")
    # a partner cannot paste the platform's ShopID as their own
    wrong = await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": PLATFORM})
    assert wrong.status_code == 422 and "plataforma" in wrong.json()["detail"]
    ok = await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": PARTNER_SHOP})
    assert ok.status_code == 200

    # SnakePay wants the dashed UUID: the first try (snakepay_…) gets a 400, the retry goes through
    snake["uuid_only"] = True
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    tries = apis.methods("snake.create")
    assert len(tries) == 2 and not apis.methods("pix.create")
    assert tries[-1]["split"] == [{"recipient_id": "01234567-89ab-cdef-0123-456789abcdef", "percentage": 100.0}]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.gateway == "snakepay" and order.partner_net == Decimal("19.05")


@pytest.mark.anyio
async def test_transaction_fee_becomes_a_percentage_on_snakepay(client, db_session, owner, super_admin, snake, apis, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "flashbot_transaction_fee", Decimal("0.40"))
    await _partner(db_session, owner, accepted=True)
    await _enable(client)
    headers = await _as(client, "socio@example.com")
    await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": SELLER})
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    # net 19.05: R$ 0,40 = 2.10% (rounded up), the partner gets 97.90%; the rest stays with the platform
    assert apis.methods("snake.create")[-1]["split"] == [{"recipient_id": SELLER, "percentage": 97.9}]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.partner_net == Decimal("18.64") and order.platform_fee == Decimal("0.41")


@pytest.mark.anyio
async def test_gateways_tab_shows_the_transaction_fee_except_to_the_super_admin(client, db_session, owner, super_admin, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "flashbot_transaction_fee", Decimal("0.40"))
    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    state = await client.get("/api/payment-gateways")
    assert state.status_code == 200, state.text
    fees = [g["fee"] for g in state.json()["gateways"]]
    assert all("taxa Falcon Bot R$ 0,40 por venda" in fee for fee in fees)
    chief, _ = owner
    chief.platform_role = "SUPER_ADMIN"  # the platform owner's own operation
    await db_session.commit()
    fees = [g["fee"] for g in (await client.get("/api/payment-gateways")).json()["gateways"]]
    assert not any("taxa Falcon Bot" in fee for fee in fees)
