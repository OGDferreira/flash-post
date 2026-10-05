from datetime import datetime, timedelta, timezone
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import router as analytics_router
from app.core.crypto import encrypt_value
from app.instagram.oauth import InstagramInsightsPermissionError
from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramPublicationJob,
    SharkEvent,
)


async def _login(client: AsyncClient) -> None:
    csrf = await client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": csrf.json()["csrf_token"]},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200


def _account(workspace_id: uuid.UUID, username: str, followers: int, media: int):
    return InstagramAccount(
        workspace_id=workspace_id,
        instagram_user_id=f"ig-{username}",
        username=username,
        encrypted_access_token=encrypt_value(f"token-{username}"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=40),
        status="connected",
        follower_count=followers,
        media_count=media,
    )


@pytest.mark.anyio
async def test_analytics_summary_filters_and_aggregates_selected_accounts(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    collaborator,
) -> None:
    _user, workspace = owner
    first = _account(workspace.id, "flashpost_one", 120, 16)
    second = _account(workspace.id, "flashpost_two", 80, 9)
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Analytics test",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=8,
        post_type="reels",
    )
    db_session.add_all([first, second, loop])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=first.id,
                scheduled_for=now,
                updated_at=now,
                status="published",
            ),
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=first.id,
                scheduled_for=now - timedelta(days=8),
                updated_at=now - timedelta(days=8),
                status="published",
            ),
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=first.id,
                scheduled_for=now + timedelta(minutes=1),
                status="queued",
            ),
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=first.id,
                scheduled_for=now - timedelta(days=9),
                status="queued",
            ),
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=second.id,
                scheduled_for=now,
                status="failed",
            ),
        ]
    )
    await db_session.commit()
    await _login(client)

    selected = await client.get(
        "/api/analytics/summary",
        params=[("account_ids", str(first.id)), ("account_ids", str(second.id))],
    )

    assert selected.status_code == 200, selected.text
    result = selected.json()
    assert result["period"] == "7d"
    assert result["followers_count"] == 200
    assert result["media_count"] == 25
    assert result["active_accounts"] == 2
    assert result["active_collaborators"] == 1
    assert result["published_posts"] == 1
    assert result["queued_posts"] == 1
    assert result["failed_posts"] == 1
    assert len(result["accounts"]) == 2
    assert result["daily_publications"][-1]["published_posts"] == 1

    only_first = await client.get(
        "/api/analytics/summary",
        params={"account_ids": str(first.id)},
    )
    assert only_first.status_code == 200
    assert only_first.json()["followers_count"] == 120
    assert only_first.json()["failed_posts"] == 0

    all_time = await client.get("/api/analytics/summary", params={"period": "all"})
    assert all_time.status_code == 200
    assert all_time.json()["published_posts"] == 2
    assert all_time.json()["queued_posts"] == 2

    today = await client.get("/api/analytics/summary", params={"period": "today"})
    assert today.status_code == 200
    assert today.json()["published_posts"] == 1


@pytest.mark.anyio
async def test_analytics_reports_missing_meta_insights_permission(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, workspace = owner
    account = _account(workspace.id, "insights_permission_test", 10, 2)
    db_session.add(account)
    await db_session.commit()

    async def permission_denied(*_args):
        raise InstagramInsightsPermissionError

    monkeypatch.setattr(analytics_router, "fetch_instagram_views", permission_denied)
    await _login(client)
    response = await client.get(
        "/api/analytics/summary",
        params={
            "account_ids": str(account.id),
            "include_meta_insights": "true",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["missing_permissions"] == [
        "instagram_business_manage_insights"
    ]
    assert response.json()["insights_unavailable"] is False


@pytest.mark.anyio
async def test_analytics_reports_account_health_team_ranking_and_daily_connections(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    collaborator,
) -> None:
    owner_user, workspace = owner
    now = datetime.now(timezone.utc)
    accounts = [
        _account(workspace.id, "active-owner-account", 10, 2),
        _account(workspace.id, "error-owner-account", 10, 2),
        _account(workspace.id, "disconnected-collaborator-account", 10, 2),
        _account(workspace.id, "expired-collaborator-account", 10, 2),
    ]
    accounts[0].connected_by_user_id = owner_user.id
    accounts[0].first_connected_at = now - timedelta(days=2)
    accounts[1].connected_by_user_id = owner_user.id
    accounts[1].first_connected_at = now - timedelta(days=1)
    accounts[1].status = "error"
    accounts[2].connected_by_user_id = collaborator.id
    accounts[2].first_connected_at = now - timedelta(days=1)
    accounts[2].status = "disconnected"
    accounts[3].connected_by_user_id = collaborator.id
    accounts[3].first_connected_at = now - timedelta(days=3)
    accounts[3].token_expires_at = now - timedelta(hours=1)
    db_session.add_all(accounts)
    await db_session.commit()
    await _login(client)

    response = await client.get("/api/analytics/summary", params={"period": "7d"})

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["active_accounts"] == 1
    assert result["errored_accounts"] == 1
    assert result["disconnected_accounts"] == 1
    assert result["expired_accounts"] == 1
    ranking = {entry["role"]: entry["connected_accounts"] for entry in result["account_connection_ranking"]}
    assert ranking == {"COLLABORATOR": 2, "OWNER": 2}
    assert sum(
        entry["connected_accounts"]
        for entry in result["daily_account_connections"]
    ) == 4
    assert len(result["daily_account_connections"]) == 7


@pytest.mark.anyio
async def test_revenue_period_uses_sao_paulo_local_day_boundaries(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    db_session.add_all(
        [
            SharkEvent(
                workspace_id=workspace.id,
                event_type="pix_paid",
                source_event_key="before-local-day",
                amount="10.00",
                occurred_at=datetime(2026, 3, 8, 2, 59, tzinfo=timezone.utc),
            ),
            SharkEvent(
                workspace_id=workspace.id,
                event_type="pix_paid",
                source_event_key="on-local-day",
                amount="25.00",
                occurred_at=datetime(2026, 3, 8, 3, 0, tzinfo=timezone.utc),
            ),
            SharkEvent(
                workspace_id=workspace.id,
                event_type="pix_paid",
                source_event_key="after-local-day",
                amount="40.00",
                occurred_at=datetime(2026, 3, 9, 3, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    await db_session.commit()
    await _login(client)

    response = await client.get(
        "/api/analytics/summary",
        params={
            "period": "custom",
            "start_date": "2026-03-08",
            "end_date": "2026-03-08",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["pix_paid_amount"] == "25.00"
    assert response.json()["daily_revenue"] == [
        {"day": "2026-03-08", "amount": "25.00"}
    ]


@pytest.mark.anyio
async def test_analytics_summary_rejects_accounts_from_other_workspaces(
    client: AsyncClient,
    owner,
) -> None:
    await _login(client)
    response = await client.get(
        "/api/analytics/summary",
        params={"account_ids": str(uuid.uuid4())},
    )

    assert response.status_code == 404
