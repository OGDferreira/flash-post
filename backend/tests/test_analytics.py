from datetime import datetime, timedelta, timezone
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.models import InstagramAccount, InstagramLoop, InstagramPublicationJob


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

    today = await client.get("/api/analytics/summary", params={"period": "today"})
    assert today.status_code == 200
    assert today.json()["published_posts"] == 1


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
