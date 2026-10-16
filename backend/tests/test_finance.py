from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollaboratorPayment, WorkspaceMember


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def _login(client: AsyncClient, email: str, password: str) -> Response:
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response


@pytest.mark.anyio
async def test_finance_cash_flow_includes_smokepay_withdrawals_and_collaborator_payments(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    collaborator,
) -> None:
    owner_user, workspace = owner
    login = await _login(client, "owner@example.com", "correct horse battery staple")
    assert "max-age=2592000" in login.headers.get("set-cookie", "").lower()

    created = await client.post(
        "/api/integrations/smokepay",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"name": "Produto principal", "split_percent": "70"},
    )
    assert created.status_code == 201, created.text
    delivered = await client.post(
        created.json()["webhook_url"],
        json={
            "event": "payment.approved",
            "data": {"id": "finance-sale-1", "amount": "100.00"},
        },
    )
    assert delivered.status_code == 200, delivered.text

    membership = await db_session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == collaborator.id,
        )
    )
    assert membership is not None
    db_session.add(
        CollaboratorPayment(
            workspace_id=workspace.id,
            workspace_member_id=membership.id,
            paid_by_user_id=owner_user.id,
            amount=Decimal("12.00"),
            period_start=date.today().replace(day=1),
        )
    )
    await db_session.commit()

    withdrawal = await client.post(
        "/api/finance/withdrawals",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"amount": "20.00", "note": "Transferência bancária"},
    )
    assert withdrawal.status_code == 201, withdrawal.text

    summary = await client.get("/api/finance")
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["gross_sales"] == "100.00"
    assert data["income"] == "70.00"
    assert data["withdrawals"] == "20.00"
    assert data["collaborator_payments"] == "12.00"
    assert data["balance"] == "38.00"
    assert data["withdrawals_today"] == "20.00"
    assert data["withdrawal_history"][0]["note"] == "Transferência bancária"
    assert data["collaborator_payment_history"][0]["collaborator_name"] == "Colaborador"
    assert data["operation_revenue"][0]["operation_name"] == "Produto principal"
    assert {item["kind"] for item in data["transactions"]} == {
        "sale",
        "withdrawal",
        "collaborator_payment",
    }

    deleted = await client.delete(
        f"/api/integrations/smokepay/{created.json()['id']}",
        headers={"X-CSRF-Token": await _csrf(client)},
    )
    assert deleted.status_code == 204
    retained_finance = await client.get("/api/finance")
    assert retained_finance.status_code == 200
    assert retained_finance.json()["income"] == "70.00"
    assert retained_finance.json()["operation_revenue"][0]["operation_name"] == "Produto principal"

    saved_goal = await client.put(
        "/api/finance/daily-withdrawal-goal",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"amount": "200.00"},
    )
    assert saved_goal.status_code == 200, saved_goal.text
    assert saved_goal.json()["daily_withdrawal_goal"] == "200.00"


@pytest.mark.anyio
async def test_finance_is_only_available_to_workspace_owners(
    client: AsyncClient,
    owner,
    collaborator,
) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")
    logout = await client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": await _csrf(client)},
    )
    assert logout.status_code == 200
    await _login(client, "collaborator@example.com", "collaborator password")
    response = await client.get("/api/finance")
    assert response.status_code == 403


@pytest.mark.anyio
async def test_finance_month_uses_sharkbot_and_flashbot_and_subtracts_costs(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    collaborator,
) -> None:
    from datetime import datetime, timezone

    from app.core.crypto import encrypt_value
    from app.models import InstagramAccount, SharkTransaction, TgBot, TgLead, TgOrder

    owner_user, workspace = owner
    await _login(client, "owner@example.com", "correct horse battery staple")
    now = datetime.now(timezone.utc)
    for key, amount, status in (("s1", Decimal("100.00"), "paid"), ("s2", None, "paid"), ("s3", Decimal("70.00"), "pending")):
        db_session.add(SharkTransaction(
            workspace_id=workspace.id, transaction_key=key, status=status, amount=amount,
            created_at_source=now, paid_at=now if status == "paid" else None,
        ))
    bot = TgBot(
        workspace_id=workspace.id, tg_bot_id=42, username="vip_bot", name="VIP",
        encrypted_token=encrypt_value("1:x"), webhook_secret="s" * 32,
    )
    db_session.add(bot)
    await db_session.flush()
    lead = TgLead(workspace_id=workspace.id, bot_id=bot.id, tg_user_id=7, chat_id=7, first_name="Lucas")
    db_session.add(lead)
    await db_session.flush()
    db_session.add(TgOrder(
        workspace_id=workspace.id, bot_id=bot.id, lead_id=lead.id, offer_id="vip", offer_name="VIP",
        amount=Decimal("50.00"), net_amount=Decimal("48.00"), gateway_transaction_id="flashbot-tx-1",
        status="paid", paid_at=now,
    ))
    membership = await db_session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == collaborator.id)
    )
    membership.rate_per_connection = Decimal("10.00")
    db_session.add(InstagramAccount(
        workspace_id=workspace.id, connected_by_user_id=collaborator.id, first_connected_at=now,
        instagram_user_id="month-collab-account", username="month_collab",
        encrypted_access_token=encrypt_value("t"), token_expires_at=now, status="connected",
    ))
    db_session.add(CollaboratorPayment(
        workspace_id=workspace.id, workspace_member_id=membership.id, paid_by_user_id=owner_user.id,
        amount=Decimal("4.00"), period_start=date.today().replace(day=1),
    ))
    await db_session.commit()

    headers = {"X-CSRF-Token": await _csrf(client)}
    expense = await client.post("/api/finance/expenses", headers=headers, json={"amount": "25.50", "description": " Anúncios "})
    assert expense.status_code == 201, expense.text
    assert expense.json()["description"] == "Anúncios"
    other = await client.post("/api/finance/expenses", headers=headers, json={"amount": "5.00", "description": "Chip"})
    assert (await client.post("/api/finance/expenses", headers=headers, json={"amount": "0", "description": "x"})).status_code == 422
    assert (await client.post("/api/finance/expenses", headers=headers, json={"amount": "3", "description": "  "})).status_code == 422

    data = (await client.get("/api/finance/month")).json()
    assert data["sharkbot_gross"] == "100.00"
    assert data["sharkbot_sales_without_amount"] == 1
    assert data["flashbot_gross"] == "50.00"
    assert data["gross_revenue"] == "150.00"
    assert data["net_revenue"] == "148.00"  # Sharkbot 100 + FlashBot net 48
    assert data["sale_count"] == 3
    assert data["collaborator_earnings"] == "10.00"
    assert data["collaborator_paid"] == "4.00"
    assert data["collaborator_due"] == "6.00"
    assert data["expenses_total"] == "30.50"
    assert {item["description"] for item in data["expenses"]} == {"Anúncios", "Chip"}
    assert data["profit"] == "107.50"  # 148 - 10 - 30.50

    deleted = await client.delete(f"/api/finance/expenses/{other.json()['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/finance/month")).json()["profit"] == "112.50"
