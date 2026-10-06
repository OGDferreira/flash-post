from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.models import (
    CollaboratorWorkDay,
    InstagramAccount,
    User,
    WorkspaceMember,
)


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def _login(client: AsyncClient, email: str, password: str) -> None:
    token = await _csrf(client)
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_owner_manages_collaborator_goals_and_records_monthly_payout(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _owner_user, workspace = owner
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    created = await client.post(
        "/api/collaborators",
        headers={"X-CSRF-Token": token},
        json={
            "full_name": "Equipe Flash",
            "nickname": "Equipe Flash",
            "email": "collaborator.created@example.com",
            "password": "safe-collaborator-password",
            "rate_per_connection": "12.50",
            "daily_connection_goal": 2,
            "monthly_connection_goal": 1,
            "monthly_bonus": "25.00",
        },
    )
    assert created.status_code == 201, created.text
    assert len(created.json()["collaborators"]) == 1
    item = created.json()["collaborators"][0]
    assert item["connections_today"] == 0
    assert item["rate_per_connection"] == "12.50"

    member = await db_session.get(WorkspaceMember, uuid.UUID(item["member_id"]))
    user = await db_session.get(User, uuid.UUID(item["user_id"]))
    assert member is not None
    assert user is not None
    assert member.role == "COLLABORATOR"

    db_session.add(
        InstagramAccount(
            workspace_id=workspace.id,
            connected_by_user_id=user.id,
            first_connected_at=datetime.now(timezone.utc),
            instagram_user_id="new-account-for-collaborator",
            username="new_collab_account",
            encrypted_access_token=encrypt_value("test-token"),
            token_expires_at=datetime.now(timezone.utc),
            status="connected",
        )
    )
    await db_session.commit()

    report = await client.get("/api/collaborators")
    assert report.status_code == 200, report.text
    item = report.json()["collaborators"][0]
    assert item["connections_today"] == 1
    assert item["connections_month"] == 1
    assert Decimal(item["earnings_today"]) == Decimal("12.50")
    assert Decimal(item["due_month"]) == Decimal("37.50")
    assert report.json()["team_connections_today"] == 1

    payout_token = await _csrf(client)
    paid = await client.post(
        f"/api/collaborators/{member.id}/payout",
        headers={"X-CSRF-Token": payout_token},
    )
    assert paid.status_code == 201, paid.text
    assert Decimal(paid.json()["payment"]["amount"]) == Decimal("37.50")

    refreshed = await client.get("/api/collaborators")
    assert refreshed.status_code == 200
    assert Decimal(refreshed.json()["collaborators"][0]["paid_month"]) == Decimal("37.50")
    assert Decimal(refreshed.json()["collaborators"][0]["due_month"]) == Decimal("0.00")

    await _login(
        client,
        "collaborator.created@example.com",
        "safe-collaborator-password",
    )
    dashboard = await client.get("/api/collaborators/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["connections_today"] == 1
    assert dashboard.json()["daily_progress"] == 50
    assert Decimal(dashboard.json()["paid_month"]) == Decimal("37.50")
    assert Decimal(dashboard.json()["paid_total"]) == Decimal("37.50")
    assert sum(
        Decimal(value) for value in dashboard.json()["recent_earnings"]
    ) == Decimal("12.50")
    assert sum(
        Decimal(value) for value in dashboard.json()["recent_payments"]
    ) == Decimal("37.50")
    ranking = await client.get("/api/collaborators/ranking")
    assert ranking.status_code == 200, ranking.text


@pytest.mark.anyio
async def test_owner_selects_paid_work_days_and_deletes_collaborator(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _owner_user, _workspace = owner
    await _login(client, "owner@example.com", "correct horse battery staple")
    csrf_token = await _csrf(client)
    created = await client.post(
        "/api/collaborators",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "full_name": "Calendário Colaborador",
            "nickname": "Calendário Colaborador",
            "email": "calendar.collaborator@example.com",
            "password": "safe-calendar-password",
            "rate_per_connection": "12.50",
            "daily_connection_goal": 0,
            "monthly_connection_goal": 0,
            "monthly_bonus": "0.00",
        },
    )
    assert created.status_code == 201, created.text
    item = created.json()["collaborators"][0]
    member_id = uuid.UUID(item["member_id"])
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Sao_Paulo")).date()
    month = today.strftime("%Y-%m")
    path = f"/api/collaborators/{member_id}/work-days?month={month}"

    selected = await client.put(
        path,
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"days": [today.isoformat()]},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["total_amount"] == "12.50"
    assert selected.json()["days"] == [
        {"day": today.isoformat(), "amount": "12.50", "paid": False}
    ]
    report = await client.get("/api/collaborators")
    assert report.status_code == 200, report.text
    collaborator_report = report.json()["collaborators"][0]
    assert Decimal(collaborator_report["earnings_today"]) == Decimal("12.50")
    assert Decimal(collaborator_report["earnings_month"]) == Decimal("12.50")
    assert sum(
        Decimal(value) for value in collaborator_report["recent_earnings"]
    ) == Decimal("12.50")

    paid = await client.post(
        f"/api/collaborators/{member_id}/payout",
        headers={"X-CSRF-Token": await _csrf(client)},
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["payment"]["amount"] == "12.50"
    work_days = await client.get(path)
    assert work_days.json()["days"][0]["paid"] is True

    unsaved = await client.put(
        path,
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"days": []},
    )
    assert unsaved.status_code == 200, unsaved.text
    assert unsaved.json()["days"][0]["paid"] is True

    deleted = await client.delete(
        f"/api/collaborators/{member_id}",
        headers={"X-CSRF-Token": await _csrf(client)},
    )
    assert deleted.status_code == 204, deleted.text
    assert await db_session.get(WorkspaceMember, member_id) is None
    assert await db_session.scalar(
        select(CollaboratorWorkDay).where(
            CollaboratorWorkDay.workspace_member_id == member_id
        )
    ) is None
    ranking = await client.get("/api/collaborators/ranking")
    assert ranking.status_code == 200, ranking.text
    assert all(
        collaborator["user_id"] != item["user_id"]
        for collaborator in ranking.json()["collaborators"]
    )
    await _login(
        client,
        "calendar.collaborator@example.com",
        "safe-calendar-password",
    )
    forbidden_report = await client.get("/api/collaborators")
    forbidden_analytics = await client.get("/api/analytics/summary")
    assert forbidden_report.status_code == 403
    assert forbidden_analytics.status_code == 403


@pytest.mark.anyio
async def test_owner_cannot_register_a_zero_or_duplicate_monthly_payout(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _owner_user, _workspace = owner
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    created = await client.post(
        "/api/collaborators",
        headers={"X-CSRF-Token": token},
        json={
            "full_name": "Zero Production",
            "nickname": "Zero Production",
            "email": "zero.production@example.com",
            "password": "safe-collaborator-password",
            "rate_per_connection": "10",
            "daily_connection_goal": 1,
            "monthly_connection_goal": 1,
            "monthly_bonus": "5",
        },
    )
    assert created.status_code == 201, created.text
    member_id = created.json()["collaborators"][0]["member_id"]
    payment_token = await _csrf(client)

    response = await client.post(
        f"/api/collaborators/{member_id}/payout",
        headers={"X-CSRF-Token": payment_token},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Não há saldo pendente para pagar."


@pytest.mark.anyio
async def test_owner_can_block_and_restore_collaborator_workspace_access(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    collaborator,
) -> None:
    _owner_user, workspace = owner
    member = await db_session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == collaborator.id,
        )
    )
    assert member is not None
    db_session.add(
        InstagramAccount(
            workspace_id=workspace.id,
            connected_by_user_id=collaborator.id,
            first_connected_at=datetime.now(timezone.utc),
            instagram_user_id="blocked-member-account",
            username="blocked_member_account",
            encrypted_access_token=encrypt_value("blocked-member-token"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            status="connected",
        )
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    blocked = await client.patch(
        f"/api/collaborators/{member.id}/access",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"enabled": False},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["access_status"] == "SUSPENDED"
    assert len(blocked.json()["account_earnings"]) == 1

    listed = await client.get("/api/collaborators")
    assert listed.status_code == 200, listed.text
    assert listed.json()["collaborators"][0]["access_status"] == "SUSPENDED"
    assert listed.json()["team_connections_today"] == 0

    blocked_login = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={
            "email": "collaborator@example.com",
            "password": "collaborator password",
        },
    )
    assert blocked_login.status_code == 403
    assert blocked_login.json()["detail"] == (
        "O acesso ao workspace foi bloqueado pelo administrador."
    )

    await _login(client, "owner@example.com", "correct horse battery staple")
    restored = await client.patch(
        f"/api/collaborators/{member.id}/access",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"enabled": True},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["access_status"] == "ACTIVE"
    assert len(restored.json()["account_earnings"]) == 1

    await _login(client, "collaborator@example.com", "collaborator password")
    dashboard = await client.get("/api/collaborators/dashboard")
    assert dashboard.status_code == 200, dashboard.text


@pytest.mark.anyio
async def test_owner_can_query_historical_monthly_collaborator_rankings(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    collaborator,
) -> None:
    owner_user, workspace = owner
    connection_time = datetime(2026, 8, 15, 15, tzinfo=timezone.utc)
    for index in range(2):
        db_session.add(
            InstagramAccount(
                workspace_id=workspace.id,
                connected_by_user_id=collaborator.id,
                first_connected_at=connection_time + timedelta(days=index),
                instagram_user_id=f"historical-ranking-{index}",
                username=f"ranking_{index}",
                encrypted_access_token=encrypt_value(f"ranking-token-{index}"),
                token_expires_at=connection_time + timedelta(days=60),
                status="connected",
            )
        )
    db_session.add(
        InstagramAccount(
            workspace_id=workspace.id,
            connected_by_user_id=owner_user.id,
            first_connected_at=connection_time + timedelta(days=2),
            instagram_user_id="historical-owner-ranking",
            username="owner_ranking",
            encrypted_access_token=encrypt_value("owner-ranking-token"),
            token_expires_at=connection_time + timedelta(days=60),
            status="connected",
        )
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    historical = await client.get(
        "/api/collaborators/ranking",
        params={"month": "2026-08"},
    )
    assert historical.status_code == 200, historical.text
    body = historical.json()
    assert body["month"] == "2026-08"
    assert body["collaborators"][0]["user_id"] == str(collaborator.id)
    assert body["collaborators"][0]["connections"] == 2
    assert body["collaborators"][0]["average_daily_connections"] == "0.06"
    owner_ranking = next(
        person for person in body["collaborators"] if person["user_id"] == str(owner_user.id)
    )
    assert owner_ranking["nickname"] == "chefe"
    assert owner_ranking["connections"] == 1
    assert owner_ranking["position"] == 2
    assert body["total_connections"] == 3

    invalid = await client.get(
        "/api/collaborators/ranking",
        params={"month": "not-a-month"},
    )
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_rate_change_preserves_existing_account_value_and_prices_new_connections(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    collaborator,
) -> None:
    _owner_user, workspace = owner
    member = await db_session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == collaborator.id,
        )
    )
    assert member is not None
    now = datetime.now(timezone.utc)
    db_session.add(
        InstagramAccount(
            workspace_id=workspace.id,
            connected_by_user_id=collaborator.id,
            first_connected_at=now - timedelta(days=1),
            collaborator_rate_at_connection=Decimal("10.00"),
            instagram_user_id="rate-before-change",
            username="before_change",
            encrypted_access_token=encrypt_value("rate-before-token"),
            token_expires_at=now + timedelta(days=60),
            status="connected",
        )
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    token = await _csrf(client)
    changed = await client.patch(
        f"/api/collaborators/{member.id}",
        headers={"X-CSRF-Token": token},
        json={
            "rate_per_connection": "15.00",
            "daily_connection_goal": 0,
            "monthly_connection_goal": 3,
            "monthly_bonus": "5.00",
        },
    )
    assert changed.status_code == 200, changed.text

    db_session.add(
        InstagramAccount(
            workspace_id=workspace.id,
            connected_by_user_id=collaborator.id,
            first_connected_at=now,
            collaborator_rate_at_connection=Decimal("15.00"),
            instagram_user_id="rate-after-change",
            username="after_change",
            encrypted_access_token=encrypt_value("rate-after-token"),
            token_expires_at=now + timedelta(days=60),
            status="connected",
        )
    )
    await db_session.commit()

    report = await client.get("/api/collaborators")
    assert report.status_code == 200, report.text
    item = report.json()["collaborators"][0]
    assert item["connections_month"] == 2
    assert Decimal(item["earnings_month"]) == Decimal("25.00")
    saved_rates = {
        account["username"]: Decimal(account["rate_per_connection"])
        for account in item["account_earnings"]
    }
    assert saved_rates == {
        "before_change": Decimal("10.00"),
        "after_change": Decimal("15.00"),
    }

    retroactive_token = await _csrf(client)
    retroactive = await client.patch(
        f"/api/collaborators/{member.id}",
        headers={"X-CSRF-Token": retroactive_token},
        json={
            "rate_per_connection": "20.00",
            "daily_connection_goal": 0,
            "monthly_connection_goal": 3,
            "monthly_bonus": "5.00",
            "apply_rate_to_existing_accounts": True,
        },
    )
    assert retroactive.status_code == 200, retroactive.text
    assert Decimal(retroactive.json()["earnings_month"]) == Decimal("40.00")
    assert Decimal(retroactive.json()["projected_month"]) == Decimal("65.00")
    assert {
        account["username"]: Decimal(account["rate_per_connection"])
        for account in retroactive.json()["account_earnings"]
    } == {
        "before_change": Decimal("20.00"),
        "after_change": Decimal("20.00"),
    }
