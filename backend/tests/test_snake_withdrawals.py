"""SnakePay Cash Out: each account withdraws its own SnakePay balance through Falcon, signed
like the docs say, saved before sending, never paid twice; and the Super Admin's blocks."""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.bots import http
from app.core.config import get_settings
from app.core.time import utc_now
from app.models import FinancialWithdrawal, TgOrder
from tests.test_affiliates import _make_owner
from tests.test_wallet import PIX, FakeSmokePay, _as, _paid

PLATFORM_SECRET = "cashout_platform_secret"
SELLER_SECRET = "cashout_seller_secret"


class FakeCashout:
    """SnakePay /withdrawals as documented; checks every signature."""

    def __init__(self) -> None:
        self.secrets = {"Bearer sk_platform": PLATFORM_SECRET, "Bearer seller_sk": SELLER_SECRET}
        self.posts: list[dict] = []
        self.gets: list[str] = []
        self.answer: tuple[int, dict] | None = None  # forced answer for the next POST
        self.status = "pending"
        self.by_request: dict[str, str] = {}
        self.smoke = FakeSmokePay()

    def handler(self, request: httpx.Request) -> httpx.Response:
        if "snake.test" not in str(request.url):
            if "/api/shops/" in request.url.path:
                return httpx.Response(404, json={"error": "not found"})
            return self.smoke.handler(request)
        raw = request.content.decode()
        timestamp = request.headers["x-snakepay-timestamp"]
        assert abs(int(timestamp) - int(utc_now().timestamp())) < 300
        secret = self.secrets[request.headers["authorization"]]
        expected = hmac.new(secret.encode(), f"{timestamp}.{request.method}.{request.url.path}.{raw}".encode(), hashlib.sha256).hexdigest()
        assert request.headers["x-snakepay-signature"] == expected, "bad signature"
        if request.method == "POST":
            assert request.url.path == "/api/public/v1/withdrawals"
            assert request.headers["content-type"] == "application/json"
            body = json.loads(raw)
            self.posts.append({**body, "_auth": request.headers["authorization"]})
            if self.answer is not None:
                status, data = self.answer
                self.answer = None
                return httpx.Response(status, json=data)
            withdrawal_id = self.by_request.setdefault(body["requestId"], f"wd_{len(self.by_request) + 1}")
            debit = 80.0 if body["amount"] == "MAX" else body["amount"]
            return httpx.Response(202, json={"id": withdrawal_id, "status": "pending", "total_debit": debit, "currency": "BRL"})
        assert raw == ""  # GET is signed with an empty body
        self.gets.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"id": self.gets[-1], "status": self.status})


@pytest.fixture
def cash(monkeypatch):
    fake = FakeCashout()
    http.set_transport(httpx.MockTransport(fake.handler))
    settings = get_settings()
    monkeypatch.setattr(settings, "snakepay_base_url", "https://snake.test/api/public/v1")
    monkeypatch.setattr(settings, "snakepay_api_key", SecretStr("sk_platform"))
    monkeypatch.setattr(settings, "snakepay_webhook_secret", SecretStr("whsec"))
    monkeypatch.setattr(settings, "snakepay_cashout_secret", SecretStr(PLATFORM_SECRET))
    monkeypatch.setattr(settings, "smokepay_api_key", SecretStr("main_key"))
    monkeypatch.setattr(settings, "smokepay_withdraw_api_key", SecretStr("withdraw_key"))
    yield fake
    http.set_transport(None)


async def _snake_sale(db, workspace, net: str) -> None:
    await _paid(db, workspace, partner_net=net)
    order = (await db.scalars(select(TgOrder).order_by(TgOrder.created_at.desc()))).first()
    order.gateway = "snakepay"
    await db.commit()


async def _age(db, item_id) -> None:
    item = await db.get(FinancialWithdrawal, item_id)
    item.last_checked_at = utc_now() - timedelta(seconds=31)
    await db.commit()


@pytest.mark.anyio
async def test_super_admin_withdraws_snakepay_saved_first_and_settled_later(client, db_session, owner, cash) -> None:
    chief, chief_ws = owner
    chief.platform_role = "SUPER_ADMIN"
    await db_session.commit()
    await _snake_sale(db_session, chief_ws, "100.00")
    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    wallet = (await client.get("/api/wallet")).json()
    snake = next(g for g in wallet["gateways"] if g["gateway"] == "snakepay")
    assert snake["ready"] and snake["available"] == 100.0 and snake["estimated"]

    assert (await client.post("/api/wallet/withdrawals", headers=headers,
                              json={"gateway": "snakepay", "amount": "5", **PIX})).status_code == 422  # min R$ 10
    sent = await client.post("/api/wallet/withdrawals", headers=headers, json={"gateway": "snakepay", "amount": "60", **PIX})
    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "PROCESSING" and sent.json()["gateway"] == "snakepay"
    post = cash.posts[-1]
    assert post == {"amount": 60.0, "key": "52998224725", "keyType": "cpf", "requestId": post["requestId"], "_auth": "Bearer sk_platform"}
    item = await db_session.scalar(select(FinancialWithdrawal))
    assert item.request_id == post["requestId"] and item.gateway_withdrawal_id == "wd_1"
    # a second one waits for the first
    again = await client.post("/api/wallet/withdrawals", headers=headers, json={"gateway": "snakepay", "amount": "10", **PIX})
    assert again.status_code == 409
    # checks wait 30 s between them; then "paid" settles it
    cash.status = "paid"
    await client.get("/api/wallet")
    assert cash.gets == []
    await _age(db_session, item.id)
    wallet = (await client.get("/api/wallet")).json()
    assert cash.gets == ["wd_1"] and wallet["withdrawals"][0]["status"] == "PAID"
    assert next(g for g in wallet["gateways"] if g["gateway"] == "snakepay")["available"] == 40.0
    assert wallet["withdrawn"] == 60.0


@pytest.mark.anyio
async def test_lost_answer_is_retried_with_the_same_request_id_and_never_pays_twice(client, db_session, owner, cash) -> None:
    chief, chief_ws = owner
    chief.platform_role = "SUPER_ADMIN"
    await db_session.commit()
    await _snake_sale(db_session, chief_ws, "100.00")
    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    cash.answer = (503, {"error": "temporarily unavailable"})
    sent = await client.post("/api/wallet/withdrawals", headers=headers, json={"gateway": "snakepay", "amount": "30", **PIX})
    assert sent.status_code == 201 and sent.json()["status"] == "PROCESSING"
    item = await db_session.scalar(select(FinancialWithdrawal))
    assert item.gateway_withdrawal_id is None
    await _age(db_session, item.id)
    await client.get("/api/wallet")
    assert len(cash.posts) == 2 and cash.posts[0]["requestId"] == cash.posts[1]["requestId"]
    await db_session.refresh(item)
    assert item.gateway_withdrawal_id == "wd_1" and item.status == "PROCESSING"


@pytest.mark.anyio
async def test_refusals_fail_the_withdrawal_with_a_clear_message(client, db_session, owner, cash) -> None:
    chief, chief_ws = owner
    chief.platform_role = "SUPER_ADMIN"
    await db_session.commit()
    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    cash.answer = (422, {"error": "Insufficient balance"})
    refused = await client.post("/api/wallet/withdrawals", headers=headers, json={"gateway": "snakepay", "amount": "30", **PIX})
    assert refused.status_code == 422 and "Saldo insuficiente" in refused.json()["detail"]
    item = await db_session.scalar(select(FinancialWithdrawal))
    assert item.status == "FAILED" and "Saldo insuficiente" in item.note
    cash.answer = (403, {"error": "Cash Out disabled"})
    blocked = await client.post("/api/wallet/withdrawals", headers=headers, json={"gateway": "snakepay", "amount": "30", **PIX})
    assert blocked.status_code == 422 and "não está liberado" in blocked.json()["detail"]


@pytest.mark.anyio
async def test_user_withdraws_with_their_own_key_and_everything_with_max(client, db_session, owner, cash) -> None:
    partner, partner_ws = await _make_owner(db_session, "socio")
    await _snake_sale(db_session, partner_ws, "80.00")
    headers = await _as(client, "socio@example.com")
    snake = next(g for g in (await client.get("/api/wallet")).json()["gateways"] if g["gateway"] == "snakepay")
    assert snake["available"] == 80.0 and not snake["ready"]
    missing = await client.post("/api/wallet/withdrawals", headers=headers, json={"gateway": "snakepay", "withdraw_all": True, **PIX})
    assert missing.status_code == 422 and "segredo de saque" in missing.json()["detail"]
    saved = await client.put("/api/payment-gateways/snakepay/credentials", headers=headers,
                             json={"api_key": "seller_sk", "webhook_secret": "whsec_seller", "cashout_secret": SELLER_SECRET})
    assert saved.status_code == 200 and saved.json()["snakepay_cashout_secret_set"]
    assert SELLER_SECRET not in saved.text
    done = await client.post("/api/wallet/withdrawals", headers=headers, json={"gateway": "snakepay", "withdraw_all": True, **PIX})
    assert done.status_code == 201, done.text
    assert cash.posts[-1]["amount"] == "MAX" and cash.posts[-1]["_auth"] == "Bearer seller_sk"
    assert done.json()["amount"] == 80.0  # SnakePay's total debit


@pytest.mark.anyio
async def test_super_admin_blocks_one_user_or_everyone_but_still_withdraws_for_a_partner(
    client, db_session, owner, super_admin, cash
) -> None:
    chief, chief_ws = owner
    partner, partner_ws = await _make_owner(db_session, "socio")
    from app.models import Affiliation

    db_session.add(Affiliation(chief_user_id=super_admin.id, affiliate_user_id=partner.id, status="ACTIVE"))
    await db_session.commit()
    await _snake_sale(db_session, partner_ws, "80.00")
    admin = await _as(client, "superadmin@example.com", "super admin password")
    assert (await client.put(f"/api/admin/users/{partner.id}/withdrawals-blocked", headers=admin, json={"blocked": True})).status_code == 200

    headers = await _as(client, "socio@example.com")
    assert (await client.get("/api/wallet")).json()["withdrawals_blocked"] is True
    await client.put("/api/payment-gateways/snakepay/credentials", headers=headers,
                     json={"api_key": "seller_sk", "webhook_secret": "whsec_seller", "cashout_secret": SELLER_SECRET})
    refused = await client.post("/api/wallet/withdrawals", headers=headers, json={"gateway": "snakepay", "amount": "20", **PIX})
    assert refused.status_code == 403 and cash.posts == []
    # everyone else too, with the general switch
    owner_headers = await _as(client, "owner@example.com", "correct horse battery staple")
    assert (await client.get("/api/wallet")).json()["withdrawals_blocked"] is False
    admin = await _as(client, "superadmin@example.com", "super admin password")
    assert (await client.put("/api/admin/withdrawals-blocked", headers=admin, json={"blocked": True})).status_code == 200
    owner_headers = await _as(client, "owner@example.com", "correct horse battery staple")
    assert (await client.post("/api/wallet/withdrawals", headers=owner_headers, json={"amount": "20", **PIX})).status_code == 403

    # the Super Admin still withdraws for the partner, from the partner's own SnakePay account
    admin = await _as(client, "superadmin@example.com", "super admin password")
    listing = (await client.get("/api/admin/partner-wallets")).json()
    assert listing["withdrawals_blocked"] is True
    row = next(item for item in listing["items"] if item["user_id"] == str(partner.id))
    assert row["withdrawals_blocked"] is True
    sent = await client.post(f"/api/admin/partner-wallets/{partner.id}/withdrawals", headers=admin,
                             json={"gateway": "snakepay", "amount": "20", **PIX})
    assert sent.status_code == 201, sent.text
    assert cash.posts[-1]["_auth"] == "Bearer seller_sk"
