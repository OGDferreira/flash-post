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
