from datetime import datetime, timedelta, timezone

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.instagram import insights_sync
from app.models import InstagramMediaInsight, Workspace
from tests.test_loops import _active_account, _csrf, _login

NOW = datetime.now(timezone.utc)


class _FakeGraph:
    """Two pages of media; the image rejects the combined metric request."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url: str, params: dict):
        self.calls.append(url)
        request = httpx.Request("GET", url)
        if url.endswith("/media"):
            if "after" not in params:
                return httpx.Response(200, request=request, json={
                    "data": [
                        {"id": "v1", "media_type": "VIDEO", "timestamp": (NOW - timedelta(hours=2)).isoformat(),
                         "permalink": "https://instagram.com/p/v1", "like_count": 5, "comments_count": 1},
                        {"id": "img1", "media_type": "IMAGE", "timestamp": (NOW - timedelta(days=1)).isoformat(),
                         "like_count": 9, "comments_count": 2},
                    ],
                    "paging": {"cursors": {"after": "c1"}, "next": "https://next"},
                })
            return httpx.Response(200, request=request, json={
                "data": [
                    {"id": "v2", "media_type": "VIDEO", "timestamp": (NOW - timedelta(days=2)).isoformat()},
                    {"id": "old", "media_type": "VIDEO", "timestamp": (NOW - timedelta(days=400)).isoformat()},
                ],
                "paging": {"cursors": {"after": "c2"}, "next": "https://next2"},
            })
        media_id = url.split("/")[-2]
        metric = params["metric"]
        if media_id == "v1":
            return httpx.Response(200, request=request, json={"data": [
                {"name": "views", "values": [{"value": 1000}]},
                {"name": "reach", "values": [{"value": 800}]},
                {"name": "likes", "values": [{"value": 50}]},
                {"name": "comments", "values": [{"value": 10}]},
                {"name": "shares", "values": [{"value": 20}]},
                {"name": "saved", "values": [{"value": 20}]},
            ]})
        if media_id == "v2":
            return httpx.Response(200, request=request, json={"data": [
                {"name": "views", "values": [{"value": 5000}]},
                {"name": "likes", "values": [{"value": 100}]},
                {"name": "comments", "values": [{"value": 0}]},
                {"name": "shares", "values": [{"value": 50}]},
                {"name": "saved", "values": [{"value": 50}]},
            ]})
        if "," in metric:
            return httpx.Response(400, request=request, json={"error": {"message": "unsupported", "code": 100}})
        if metric == "shares":
            return httpx.Response(400, request=request, json={"error": {"message": "unsupported", "code": 100}})
        return httpx.Response(200, request=request, json={"data": [{"name": metric, "values": [{"value": 7}]}]})


@pytest.mark.anyio
async def test_sync_persists_metrics_without_inventing_zeros(
    db_session: AsyncSession, owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "insights_owner")
    db_session.add(account)
    await db_session.commit()
    monkeypatch.setattr(insights_sync.httpx, "AsyncClient", _FakeGraph)

    synced = await insights_sync.sync_account_media_insights(db_session, account, NOW)

    assert synced == 3  # "old" is outside the lookback window
    rows = {
        row.ig_media_id: row
        for row in (await db_session.scalars(select(InstagramMediaInsight))).all()
    }
    assert rows["v1"].views == 1000 and rows["v1"].saves == 20
    assert rows["v2"].reach is None  # Meta did not send it
    assert rows["img1"].shares is None
    assert "shares" in (rows["img1"].metrics_error or "")
    assert account.insights_synced_at is not None and account.insights_sync_error is None


async def _seed(db: AsyncSession, workspace, username: str, specs: list[dict]):
    account = _active_account(workspace.id, username)
    db.add(account)
    await db.flush()
    for index, spec in enumerate(specs):
        db.add(
            InstagramMediaInsight(
                workspace_id=workspace.id,
                account_id=account.id,
                ig_media_id=f"{username}-{index}",
                media_type="VIDEO",
                posted_at=spec.get("posted_at", NOW - timedelta(hours=index + 1)),
                synced_at=NOW,
                views=spec.get("views"),
                likes=spec.get("likes"),
                comments=spec.get("comments"),
                shares=spec.get("shares"),
                saves=spec.get("saves"),
            )
        )
    account.insights_synced_at = NOW
    await db.commit()
    return account


FULL = {"likes": 10, "comments": 5, "shares": 3, "saves": 2}  # 20 interactions


@pytest.mark.anyio
async def test_top_videos_sorting_engagement_and_isolation(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    hot = await _seed(db_session, workspace, "hot_account", [
        {"views": 10_000, **FULL},          # 0.2 %
        {"views": 100, **FULL},             # 20 %
        {"views": 50_000, "likes": 1},      # incomplete -> no rate
    ])
    other_workspace = Workspace(name="Outro", slug="outro", owner_id=_user.id, status="ACTIVE")
    db_session.add(other_workspace)
    await db_session.flush()
    await _seed(db_session, other_workspace, "foreign_account", [{"views": 999_999, **FULL}])
    await _login(client, "owner@example.com", "correct horse battery staple")

    by_views = (await client.get("/api/analytics/videos", params={"period": "7d"})).json()
    assert [item["views"] for item in by_views["items"]] == [50_000, 10_000, 100]
    assert all(item["username"] == "hot_account" for item in by_views["items"])

    by_rate = (await client.get(
        "/api/analytics/videos", params={"period": "7d", "sort": "engagement_rate"}
    )).json()["items"]
    assert [item["engagement_rate"] for item in by_rate] == [20.0, 0.2, None]
    asc = (await client.get(
        "/api/analytics/videos", params={"period": "7d", "sort": "engagement_rate", "order": "asc"}
    )).json()["items"]
    assert [item["engagement_rate"] for item in asc] == [0.2, 20.0, None]
    assert "visualizações" in by_views["formula"]

    only_account = (await client.get(
        "/api/analytics/videos", params={"period": "7d", "account_id": str(hot.id)}
    )).json()["items"]
    assert len(only_account) == 3


@pytest.mark.anyio
async def test_engagement_ranking_orders_accounts_and_respects_period(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    await _seed(db_session, workspace, "high_eng", [{"views": 100, **FULL}])          # 20 %
    await _seed(db_session, workspace, "low_eng", [{"views": 10_000, **FULL}])        # 0.2 %
    await _seed(db_session, workspace, "old_posts", [
        {"views": 100, **FULL, "posted_at": NOW - timedelta(days=60)}
    ])
    await _login(client, "owner@example.com", "correct horse battery staple")

    desc = (await client.get("/api/analytics/engagement-ranking", params={"period": "7d"})).json()
    names = [row["username"] for row in desc["rows"]]
    assert names[:2] == ["high_eng", "low_eng"]
    old = next(row for row in desc["rows"] if row["username"] == "old_posts")
    assert old["engagement_rate"] is None and old["publications"] == 0

    asc = (await client.get(
        "/api/analytics/engagement-ranking", params={"period": "7d", "order": "asc"}
    )).json()
    assert [row["username"] for row in asc["rows"]][:2] == ["low_eng", "high_eng"]


@pytest.mark.anyio
async def test_media_endpoints_are_owner_only(client: AsyncClient, owner, collaborator) -> None:
    await _login(client, "collaborator@example.com", "collaborator password")
    assert (await client.get("/api/analytics/videos")).status_code == 403
    assert (await client.get("/api/analytics/engagement-ranking")).status_code == 403
    response = await client.post(
        "/api/analytics/accounts/00000000-0000-0000-0000-000000000000/sync",
        headers={"X-CSRF-Token": await _csrf(client)},
    )
    assert response.status_code == 403
