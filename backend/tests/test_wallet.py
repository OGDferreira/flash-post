"""Wallet: balance after split, automatic SmokePay withdrawals (subaccount and main)."""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.bots import http
from app.core.config import get_settings
from app.models import Affiliation, FinancialWithdrawal, TgBot, TgLead, TgOrder
from tests.test_affiliates import PASSWORD, _make_owner
from tests.test_loops import _csrf, _login


class FakeSmokePay:
    def __init__(self) -> None:
        self.shops: dict[str, float] = {}
        self.main = 100.0
        self.calls: list[tuple[str, str, dict]] = []
        self.cooldown = False
        self.main_status = "processing"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, path, body))
        assert request.headers["x-api-key"] == "withdraw_key"
        parts = path.strip("/").split("/")
        if parts[:2] == ["api", "shops"]:
            ref = parts[2]
            if ref not in self.shops:
                return httpx.Response(404, json={"error": "Subconta nao encontrada"})
            if parts[3] == "balance":
                return httpx.Response(200, json={"success": True, "wallet_balance": self.shops[ref]})
            if parts[3] == "withdraw":
                if self.cooldown:
                    return httpx.Response(429, json={"error": "cooldown", "cooldown_seconds": 180})
                self.shops[ref] -= body["amount"]
                return httpx.Response(200, json={"success": True, "withdrawal_id": "w-shop-1", "amount": body["amount"],
                                                 "fee": 2.0, "status": "completed", "new_balance": self.shops[ref]})
        if path == "/api/wallet":
            return httpx.Response(200, json={"success": True, "wallet_balance": self.main})
        if path == "/api/withdrawals" and request.method == "POST":
            self.main -= body["amount"]
            return httpx.Response(200, json={"success": True, "withdrawal_id": "w-main-1", "amount": body["amount"],
                                             "fee": 1.5, "status": self.main_status, "new_balance": self.main})
        if path == "/api/withdrawals":
            return httpx.Response(200, json={"success": True, "withdrawals": [{"id": "w-main-1", "amount": 30, "status": "completed"}]})
        raise AssertionError(f"unexpected {request.method} {path}")


@pytest.fixture
def smoke(monkeypatch):
    fake = FakeSmokePay()
    http.set_transport(httpx.MockTransport(fake.handler))
    settings = get_settings()
    monkeypatch.setattr(settings, "smokepay_api_key", SecretStr("main_key"))
    monkeypatch.setattr(settings, "smokepay_withdraw_api_key", SecretStr("withdraw_key"))
    yield fake
    http.set_transport(None)


async def _paid(db, workspace, chief_id=None, partner_net=None, commission=None):
    bot = await db.scalar(select(TgBot).where(TgBot.workspace_id == workspace.id))
    if bot is None:
        bot = TgBot(workspace_id=workspace.id, tg_bot_id=uuid.uuid4().int % 10**9, username="b", name="b",
                    encrypted_token="x", webhook_secret="s" * 32)
        db.add(bot)
        await db.flush()
    lead = TgLead(workspace_id=workspace.id, bot_id=bot.id, tg_user_id=uuid.uuid4().int % 10**9, chat_id=1)
    db.add(lead)
    await db.flush()
    now = datetime.now(timezone.utc)
    db.add(TgOrder(workspace_id=workspace.id, bot_id=bot.id, lead_id=lead.id, kind="plan", offer_id="vip", offer_name="VIP",
                   offer_snapshot={}, amount=Decimal("19.90"), status="paid", paid_at=now, expires_at=now,
                   gateway_fee=Decimal("1.00"), net_amount=Decimal("18.90"), split_chief_user_id=chief_id,
                   split_amount=Decimal(commission) if commission else None,
                   partner_net=Decimal(partner_net) if partner_net else None))
    await db.commit()


async def _as(client, email, password=PASSWORD) -> dict:
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    await _login(client, email, password)
    return {"X-CSRF-Token": await _csrf(client)}


PIX = {"pix_key_type": "cpf", "pix_key": "529.982.247-25"}


@pytest.mark.anyio
async def test_partner_withdraws_from_own_subaccount(client, db_session, owner, smoke) -> None:
    chief, chief_ws = owner
    partner, partner_ws = await _make_owner(db_session, "socio")
    for _ in range(3):
        await _paid(db_session, partner_ws, chief.id, partner_net="13.23", commission="5.67")
    ref = f"fp-{partner_ws.id.hex}"

    headers = await _as(client, "socio@example.com")
    # no sale reached SmokePay yet: the subaccount does not exist, balance is 0 there
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["shop_ref"] == ref and wallet["is_main_account"] is False and wallet["available"] == 0.0
    smoke.shops[ref] = 39.69
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["available"] == 39.69 and wallet["balance_source"] == "smokepay"
    assert wallet["month_revenue"] == 59.7
    assert wallet["commission_paid"] == 17.01 and wallet["withdraw_fee"] == 3.0

    assert (await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "5", **PIX})).status_code == 422
    assert (await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "50", **PIX})).status_code == 422
    assert (await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "20"})).status_code == 422
    # a CPF with wrong check digits never reaches SmokePay (the bank would bounce it)
    calls = len(smoke.calls)
    bad = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "20", "pix_key_type": "cpf", "pix_key": "16051416796"})
    assert bad.status_code == 422 and "CPF inválido" in bad.json()["detail"] and len(smoke.calls) == calls
    done = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "30", **PIX})
    assert done.status_code == 201, done.text
    assert done.json()["status"] == "PAID" and done.json()["fee"] == 2.0
    method, path, body = smoke.calls[-1]
    assert path == f"/api/shops/{ref}/withdraw" and body["pix_key"] == "52998224725"
    assert body["correlation_id"] == done.json()["id"]  # idempotent on our row id
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["withdrawn"] == 30.0 and wallet["available"] == 9.69 and wallet["withdrawable"] == 6.69
    # the withdrawal fee comes out of the balance too: the full balance cannot be withdrawn
    smoke.shops[ref] = 12.42
    over = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "12.42", **PIX})
    assert over.status_code == 422 and "até R$ 9,42" in over.json()["detail"]

    # SmokePay cooldown is reported clearly and recorded as failed
    smoke.cooldown = True
    smoke.shops[ref] = 20.0
    blocked = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "10", **PIX})
    assert blocked.status_code == 422 or blocked.status_code == 429
    assert "5 minutos" in blocked.json()["detail"]
    assert (await client.get("/api/wallet")).json()["withdrawals"][0]["status"] == "FAILED"

    # a chief never withdraws from a partner's subaccount: the ref comes from the server
    smoke.cooldown = False
    chief_headers = await _as(client, "owner@example.com", "correct horse battery staple")
    smoke.shops[f"fp-{chief_ws.id.hex}"] = 17.01
    chief_wallet = (await client.get("/api/wallet")).json()
    assert chief_wallet["shop_ref"] == f"fp-{chief_ws.id.hex}" and chief_wallet["commissions_received"] == 17.01
    ok = await client.post("/api/wallet/withdrawals", headers=chief_headers, json={"amount": "10", **PIX})
    assert ok.status_code == 201 and smoke.calls[-1][1] == f"/api/shops/fp-{chief_ws.id.hex}/withdraw"


@pytest.mark.anyio
async def test_main_account_withdraws_and_reconciles(client, db_session, owner, smoke) -> None:
    chief, chief_ws = owner
    chief.platform_role = "SUPER_ADMIN"
    await db_session.commit()
    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["is_main_account"] is True and wallet["available"] == 100.0
    sent = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "30", **PIX})
    assert sent.status_code == 201 and sent.json()["status"] == "PROCESSING"
    assert smoke.calls[-1][1] == "/api/withdrawals"
    wallet = (await client.get("/api/wallet")).json()  # reconcile: SmokePay says completed
    assert wallet["withdrawals"][0]["status"] == "PAID" and wallet["withdrawn"] == 30.0
    summary = (await client.get("/api/wallet/summary")).json()
    assert summary["available"] is True and summary["target"] == 10000.0
    await db_session.commit()
    item = await db_session.scalar(select(FinancialWithdrawal))
    assert item.gateway_withdrawal_id == "w-main-1" and item.fee == Decimal("1.50")


@pytest.mark.anyio
async def test_goals_and_award_photos(client, db_session, owner, super_admin, monkeypatch) -> None:
    saved: dict[str, bytes] = {}

    class FakeStorage:
        async def upload(self, path, content, content_type):
            saved[path] = content

        async def create_signed_url(self, path):
            return f"https://cdn.test/{path}"

    from app.instagram import storage as storage_module
    from app.wallet import router as wallet_router

    monkeypatch.setattr(storage_module.SupabaseStorage, "from_settings", classmethod(lambda cls: FakeStorage()))
    wallet_router._signed_cache.clear()
    _, workspace = owner
    await _paid(db_session, workspace)

    await _as(client, "owner@example.com", "correct horse battery staple")
    goals = (await client.get("/api/wallet/goals")).json()
    assert goals["available"] and goals["month_revenue"] == 19.9 and goals["target"] == 10000.0
    assert [g["current"] for g in goals["goals"]] == [True] + [False] * 6
    assert goals["goals"][-1]["amount"] == 10_000_000
    assert all(g["image_url"].startswith("/premiacoes/flashbot-") for g in goals["goals"])
    # only the Super Admin uploads award photos
    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    denied = await client.put("/api/admin/awards/10000/image", headers={**headers, "Content-Type": "image/png"}, content=png)
    assert denied.status_code == 403

    admin = await _as(client, "superadmin@example.com", "super admin password")
    bad = await client.put("/api/admin/awards/10000/image", headers={**admin, "Content-Type": "image/png"}, content=b"nope")
    assert bad.status_code == 415
    assert (await client.put("/api/admin/awards/123/image", headers={**admin, "Content-Type": "image/png"}, content=png)).status_code == 404
    ok = await client.put("/api/admin/awards/10000/image", headers={**admin, "Content-Type": "image/png"}, content=png)
    assert ok.status_code == 200, ok.text
    items = (await client.get("/api/admin/awards")).json()["items"]
    assert items[0]["image_url"].startswith("https://cdn.test/awards/10000-") and items[0]["custom"]
    assert items[1]["image_url"] == "/premiacoes/flashbot-50k.webp" and not items[1]["custom"]

    await _as(client, "owner@example.com", "correct horse battery staple")
    goals = (await client.get("/api/wallet/goals")).json()
    assert goals["goals"][0]["image_url"] == items[0]["image_url"]
    admin = await _as(client, "superadmin@example.com", "super admin password")
    assert (await client.delete("/api/admin/awards/10000/image", headers=admin)).status_code == 200
    reset = (await client.get("/api/admin/awards")).json()["items"][0]
    assert reset["image_url"] == "/premiacoes/flashbot-10k.webp" and not reset["custom"]


@pytest.mark.anyio
async def test_only_super_admin_sees_and_withdraws_partner_balances(client, db_session, owner, super_admin, smoke) -> None:
    chief, _chief_ws = owner
    partner, partner_ws = await _make_owner(db_session, "socio")
    db_session.add(Affiliation(chief_user_id=chief.id, affiliate_user_id=partner.id, participation_percent=Decimal("30"),
                               accepted_percent=Decimal("30"), accepted_at=datetime.now(timezone.utc)))
    await db_session.commit()
    for _ in range(3):
        await _paid(db_session, partner_ws, chief.id, partner_net="13.23", commission="5.67")
    ref = f"fp-{partner_ws.id.hex}"
    smoke.shops[ref] = 39.69

    # the partner sees billing, net balance and what was paid out, never the chief's commission
    headers = await _as(client, "socio@example.com")
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["is_partner"] is True and wallet["available"] == 39.69 and wallet["month_revenue"] == 59.7
    assert "commission_paid" not in wallet and wallet["withdrawals"] == []
    refused = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "20", **PIX})
    assert refused.status_code == 403
    assert (await client.get("/api/admin/partner-wallets")).status_code == 403

    admin_headers = await _as(client, "superadmin@example.com", "super admin password")
    listing = (await client.get("/api/admin/partner-wallets")).json()
    (item,) = listing["items"]
    assert item["user_id"] == str(partner.id) and item["chief"] == chief.full_name and item["available"] == 39.69
    done = await client.post(f"/api/admin/partner-wallets/{partner.id}/withdrawals", headers=admin_headers, json={"amount": "30", **PIX})
    assert done.status_code == 201, done.text
    assert smoke.calls[-1][1] == f"/api/shops/{ref}/withdraw" and smoke.calls[-1][2]["sub_shop_id"] == str(partner.id)
    item = (await client.get("/api/admin/partner-wallets")).json()["items"][0]
    assert item["withdrawn"] == 30.0 and item["withdrawals"][0]["status"] == "PAID"
    # an independent user is not a partner: nothing to withdraw on their behalf
    missing = await client.post(f"/api/admin/partner-wallets/{chief.id}/withdrawals", headers=admin_headers, json={"amount": "10", **PIX})
    assert missing.status_code == 404

    # the partner now sees what was withdrawn, still without the history
    await _as(client, "socio@example.com")
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["withdrawn"] == 30.0 and wallet["withdrawals"] == []
