from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models import SharkEvent, SmokepayOperation


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def _login(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_smokepay_operation_webhook_applies_split_and_deduplicates_sales(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    await _login(client)
    created = await client.post(
        "/api/integrations/smokepay",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"name": "Operação sócio", "split_percent": "70"},
    )
    assert created.status_code == 201, created.text
    operation_data = created.json()
    assert operation_data["webhook_url"].startswith(
        "http://testserver/api/webhooks/smokepay/"
    )
    operation = await db_session.get(
        SmokepayOperation, UUID(operation_data["id"])
    )
    assert operation is not None
    secret = operation_data["webhook_url"].rsplit("/", 1)[-1]
    assert operation.webhook_key_hash != secret
    assert decrypt_value(operation.encrypted_webhook_key) == secret

    bad_key = await client.post(
        operation_data["webhook_url"].replace(secret, "invalid-key"),
        json={"event": "payment.approved", "data": {"amount": "100", "id": "sale-1"}},
    )
    assert bad_key.status_code == 404

    payload = {
        "event": "payment.approved",
        "data": {
            "id": "sale-1",
            "amount": "100.00",
            "approved_at": "2026-10-06T12:00:00-03:00",
            "customer": {"name": "Comprador exemplo"},
            "product": {"name": "Plano"},
        },
    }
    accepted = await client.post(operation_data["webhook_url"], json=payload)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"accepted": 1, "duplicates": 0, "ignored": 0}
    duplicate = await client.post(operation_data["webhook_url"], json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json() == {"accepted": 0, "duplicates": 1, "ignored": 0}
    sale = await db_session.scalar(
        select(SharkEvent).where(
            SharkEvent.workspace_id == workspace.id,
            SharkEvent.operation_id == operation.id,
        )
    )
    assert sale is not None
    assert sale.amount == Decimal("100.00")
    assert sale.net_amount == Decimal("70.00")
    assert sale.customer_name == "Comprador exemplo"

    finance = await client.get("/api/analytics/smokepay")
    assert finance.status_code == 200, finance.text
    assert finance.json()["gross_total"] == "100.00"
    assert finance.json()["net_total"] == "70.00"
    assert finance.json()["sale_count"] == 1
    assert finance.json()["operations"][0]["name"] == "Operação sócio"
    assert finance.json()["recent_sales"][0]["transaction_id"] == "sale-1"


@pytest.mark.anyio
async def test_smokepay_finance_daily_goal_and_nonapproved_events(
    client: AsyncClient,
    owner,
) -> None:
    await _login(client)
    created = await client.post(
        "/api/integrations/smokepay",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"name": "Operação padrão"},
    )
    assert created.status_code == 201
    assert created.json()["split_percent"] == "100.00"

    ignored = await client.post(
        created.json()["webhook_url"],
        json={"event": "payment.pending", "data": {"id": "pending-sale", "amount": 99}},
    )
    assert ignored.status_code == 200
    assert ignored.json()["ignored"] == 1

    saved_goal = await client.put(
        "/api/analytics/smokepay/daily-goal",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"daily_goal": "1500.00"},
    )
    assert saved_goal.status_code == 200, saved_goal.text
    assert saved_goal.json()["daily_goal"] == "1500.00"
    assert saved_goal.json()["gross_total"] == "0.00"


@pytest.mark.anyio
async def test_smokepay_operations_are_workspace_isolated_and_owner_only(
    client: AsyncClient,
    collaborator,
    owner,
) -> None:
    await _login(client)
    created = await client.post(
        "/api/integrations/smokepay",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"name": "Minha operação"},
    )
    assert created.status_code == 201
    await _login_collaborator(client)
    denied = await client.get("/api/integrations/smokepay")
    assert denied.status_code == 403


async def _login_collaborator(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": await _csrf(client)},
    )
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={
            "email": "collaborator@example.com",
            "password": "collaborator password",
        },
    )
    assert response.status_code == 200, response.text
