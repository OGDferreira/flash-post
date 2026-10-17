"""Wallet: balance after split, withdrawal requests, Super Admin payout."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AppNotification, FinancialWithdrawal, TgBot, TgLead, TgOrder
from tests.test_affiliates import PASSWORD, _make_owner
from tests.test_loops import _csrf, _login


async def _paid(db, workspace, chief_id=None, net="18.90", partner_net=None, commission=None):
    bot = await db.scalar(select(TgBot).where(TgBot.workspace_id == workspace.id))
    if bot is None:
        bot = TgBot(workspace_id=workspace.id, tg_bot_id=abs(hash(workspace.id)) % 10**9, username="b", name="b",
                    encrypted_token="x", webhook_secret="s" * 32)
        db.add(bot)
        await db.flush()
    lead = TgLead(workspace_id=workspace.id, bot_id=bot.id, tg_user_id=uuid.uuid4().int % 10**9, chat_id=1)
    db.add(lead)
    await db.flush()
    now = datetime.now(timezone.utc)
    db.add(TgOrder(workspace_id=workspace.id, bot_id=bot.id, lead_id=lead.id, kind="plan", offer_id="vip", offer_name="VIP",
                   offer_snapshot={}, amount=Decimal("19.90"), status="paid", paid_at=now, expires_at=now,
                   gateway_fee=Decimal("1.00"), net_amount=Decimal(net), split_chief_user_id=chief_id,
                   split_amount=Decimal(commission) if commission else None,
                   partner_net=Decimal(partner_net) if partner_net else None))
    await db.commit()


async def _as(client, email, password=PASSWORD) -> dict:
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    await _login(client, email, password)
    return {"X-CSRF-Token": await _csrf(client)}


@pytest.mark.anyio
async def test_partner_requests_and_admin_pays(client, db_session, owner, super_admin) -> None:
    chief, _ = owner
    partner, partner_ws = await _make_owner(db_session, "socio")
    for _ in range(3):  # 3 sales: partner keeps 13.23 each, chief gets 5.67
        await _paid(db_session, partner_ws, chief.id, partner_net="13.23", commission="5.67")

    headers = await _as(client, "socio@example.com")
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["available"] == 39.69 and wallet["is_main_account"] is False
    assert wallet["month_revenue"] == 59.7 and wallet["goal"]["target"] == 10000.0
    too_small = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "5", "pix_key_type": "cpf", "pix_key": "12345678900"})
    assert too_small.status_code == 422
    too_big = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "50", "pix_key_type": "cpf", "pix_key": "12345678900"})
    assert too_big.status_code == 422
    no_key = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "20"})
    assert no_key.status_code == 422
    ok = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "30", "pix_key_type": "cpf", "pix_key": "12345678900"})
    assert ok.status_code == 201 and ok.json()["status"] == "REQUESTED"
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["available"] == 9.69 and wallet["pending"] == 30.0
    assert (await client.get("/api/wallet/requests")).status_code == 403  # only the Super Admin pays

    # chief's own wallet counts the commissions received
    await _as(client, "owner@example.com", "correct horse battery staple")
    chief_wallet = (await client.get("/api/wallet")).json()
    assert chief_wallet["commissions_received"] == 17.01 and chief_wallet["available"] == 17.01

    admin = await _as(client, "superadmin@example.com", "super admin password")
    requests = (await client.get("/api/wallet/requests")).json()["items"]
    assert len(requests) == 1 and requests[0]["pix_key"] == "12345678900"
    assert requests[0]["shop_ref"] == f"fp-{partner_ws.id.hex}"
    paid = await client.post(f"/api/wallet/requests/{requests[0]['id']}", headers=admin, json={"action": "paid"})
    assert paid.status_code == 200 and paid.json()["status"] == "PAID"
    again = await client.post(f"/api/wallet/requests/{requests[0]['id']}", headers=admin, json={"action": "paid"})
    assert again.status_code == 404  # never paid twice

    await _as(client, "socio@example.com")
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["withdrawn"] == 30.0 and wallet["pending"] == 0.0 and wallet["available"] == 9.69
    await db_session.commit()
    kinds = list(await db_session.scalars(select(AppNotification.kind).where(AppNotification.user_id == partner.id)))
    assert "withdrawal-paid" in kinds


@pytest.mark.anyio
async def test_main_account_records_withdrawal_and_cancel(client, db_session, owner) -> None:
    chief, chief_ws = owner
    chief.platform_role = "SUPER_ADMIN"
    await db_session.commit()
    await _paid(db_session, chief_ws, net="18.90")
    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    wallet = (await client.get("/api/wallet")).json()
    assert wallet["is_main_account"] is True and wallet["available"] == 18.9
    recorded = await client.post("/api/wallet/withdrawals", headers=headers, json={"amount": "8"})
    assert recorded.status_code == 201 and recorded.json()["status"] == "PAID"
    assert (await client.get("/api/wallet")).json()["available"] == 10.9
    summary = (await client.get("/api/wallet/summary")).json()
    assert summary["available"] is True and summary["target"] == 10000.0

    # a pending request can be cancelled by its owner, a paid one cannot
    item = await db_session.scalar(select(FinancialWithdrawal))
    assert (await client.delete(f"/api/wallet/withdrawals/{item.id}", headers=headers)).status_code == 404
