"""One period for every metric, published counted by publication time, and
the two different view series (received on the day vs cumulative of the
videos published that day)."""

from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import APP_TIME_ZONE, day_bounds_utc, local_date
from app.instagram import daily_views_sync
from app.models import (
    InstagramAccountDailyViews,
    InstagramLoop,
    InstagramMediaInsight,
    InstagramPublicationJob,
)
from tests.test_loops import _active_account, _csrf, _login

PW = "correct horse battery staple"
NOW = datetime.now(timezone.utc)
TODAY = local_date(NOW)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    """A local wall-clock time of ``day`` expressed in UTC."""
    return datetime.combine(day, time(hour, minute), tzinfo=APP_TIME_ZONE).astimezone(timezone.utc)


async def _account_with_days(db: AsyncSession, workspace, username: str, views_by_offset: dict[int, int]):
    account = _active_account(workspace.id, username)
    account.connected_at = NOW - timedelta(days=60)
    db.add(account)
    await db.flush()
    for offset, views in views_by_offset.items():
        db.add(InstagramAccountDailyViews(
            workspace_id=workspace.id, account_id=account.id, day=TODAY - timedelta(days=offset),
            views=views, fetched_at=NOW,
        ))
    return account


def _video(workspace, account, key: str, posted_at: datetime, views: int | None, **extra) -> InstagramMediaInsight:
    return InstagramMediaInsight(
        workspace_id=workspace.id, account_id=account.id, ig_media_id=key, media_type="VIDEO",
        posted_at=posted_at, synced_at=NOW, views=views, **extra,
    )


@pytest.mark.anyio
async def test_daily_series_are_separate_and_grouped_by_local_day(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    account = await _account_with_days(db_session, workspace, "daily_ig", {5: 100, 4: 200, 3: 300})
    day3 = TODAY - timedelta(days=3)
    # Posted at 23:30 local on day 4 (= next UTC day): belongs to day 4, not day 3.
    db_session.add(_video(workspace, account, "late", _at(TODAY - timedelta(days=4), 23, 30), 1000))
    db_session.add(_video(workspace, account, "morning", _at(day3, 8), 400))
    db_session.add(_video(workspace, account, "noon", _at(day3, 12), 600))
    db_session.add(_video(workspace, account, "unknown", _at(TODAY - timedelta(days=5), 9), None))
    await db_session.commit()
    await _login(client, "owner@example.com", PW)

    start, end = TODAY - timedelta(days=5), TODAY - timedelta(days=3)
    data = (await client.get("/api/analytics/views-daily", params={
        "period": "custom", "start_date": start.isoformat(), "end_date": end.isoformat(),
    })).json()
    by_day = {point["day"]: point for point in data["days"]}
    assert list(by_day) == [(start + timedelta(days=i)).isoformat() for i in range(3)]
    d5, d4, d3 = (by_day[(TODAY - timedelta(days=n)).isoformat()] for n in (5, 4, 3))
    # Received on the day (Meta daily value), independent of publication dates.
    assert (d5["received_views"], d4["received_views"], d3["received_views"]) == (100, 200, 300)
    # Cumulative views of the videos published that day, grouped by LOCAL day.
    assert d4["published_videos"] == 1 and d4["published_videos_views"] == 1000
    assert d3["published_videos"] == 2 and d3["published_videos_views"] == 1000  # 400 + 600
    # A video without views makes that day's cumulative figure unavailable, not 0.
    assert d5["published_videos"] == 1 and d5["published_videos_views"] is None
    assert data["received_total"] == 600 and data["received_days_complete"] == 3
    assert data["published_videos_views_total"] == 2000
    assert "Não é acumulado" in data["definitions"]["received_views"]
    assert "acumuladas" in data["definitions"]["published_videos_views"]


@pytest.mark.anyio
async def test_incomplete_days_are_never_presented_as_exact_totals(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    await _account_with_days(db_session, workspace, "has_data", {2: 50, 1: 70})
    await _account_with_days(db_session, workspace, "missing_one_day", {2: 10})  # nothing for day 1
    await db_session.commit()
    await _login(client, "owner@example.com", PW)
    data = (await client.get("/api/analytics/views-daily", params={
        "period": "custom",
        "start_date": (TODAY - timedelta(days=2)).isoformat(), "end_date": (TODAY - timedelta(days=1)).isoformat(),
    })).json()
    first, second = data["days"]
    assert first["received_views"] == 60 and first["received_accounts"] == 2
    assert second["received_views"] is None and second["received_accounts"] == 1  # one account is missing
    assert second["expected_accounts"] == 2
    assert data["received_total"] is None  # an incomplete day -> no exact total
    assert data["received_days_complete"] == 1 and data["received_days_total"] == 2
    assert second["provisional"] is True


@pytest.mark.anyio
async def test_views_daily_account_filter_isolation_and_permissions(
    client: AsyncClient, db_session: AsyncSession, owner, collaborator
) -> None:
    _user, workspace = owner
    a = await _account_with_days(db_session, workspace, "acc_a", {1: 11})
    await _account_with_days(db_session, workspace, "acc_b", {1: 22})
    await db_session.commit()
    await _login(client, "owner@example.com", PW)
    params = {"period": "yesterday"}
    both = (await client.get("/api/analytics/views-daily", params=params)).json()
    assert both["days"][0]["received_views"] == 33
    only_a = (await client.get("/api/analytics/views-daily", params={**params, "account_id": str(a.id)})).json()
    assert only_a["days"][0]["received_views"] == 11
    assert (await client.get("/api/analytics/views-daily", params={
        **params, "account_id": "00000000-0000-0000-0000-000000000000"})).status_code == 404
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    await _login(client, "collaborator@example.com", "collaborator password")
    assert (await client.get("/api/analytics/views-daily")).status_code == 403


@pytest.mark.anyio
async def test_daily_sync_writes_days_keeps_final_days_and_records_errors(
    db_session: AsyncSession, owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "sync_daily")
    account.connected_at = NOW - timedelta(days=10)
    db_session.add(account)
    await db_session.commit()
    calls: list[tuple[datetime, datetime]] = []

    async def fake_views(_user_id, _token, since, until):
        calls.append((since, until))
        return 7

    monkeypatch.setattr(daily_views_sync, "fetch_instagram_views", fake_views)
    written = await daily_views_sync.sync_account_daily_views(db_session, account, NOW)
    rows = (await db_session.scalars(select(InstagramAccountDailyViews).order_by(InstagramAccountDailyViews.day))).all()
    assert written == len(rows) >= 10
    assert len({row.day for row in rows}) == len(rows)  # one row per day, never duplicated
    for since, until in calls:  # every request is one local day, never in the future
        assert since < until <= NOW
        assert since >= day_bounds_utc(local_date(since))[0]
    assert rows[0].day == local_date(NOW - timedelta(days=10))

    calls.clear()
    await daily_views_sync.sync_account_daily_views(db_session, account, NOW + timedelta(hours=3))
    refreshed_days = {local_date(since) for since, _ in calls}
    assert refreshed_days and all(day >= TODAY - timedelta(days=daily_views_sync.FINAL_AFTER_DAYS) for day in refreshed_days)
    assert len((await db_session.scalars(select(InstagramAccountDailyViews))).all()) == len(rows)  # no duplicates

    async def failing(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(daily_views_sync, "fetch_instagram_views", failing)
    await db_session.execute(InstagramAccountDailyViews.__table__.delete())
    await db_session.commit()
    assert await daily_views_sync.sync_account_daily_views(db_session, account, NOW) == 0
    assert account.insights_sync_error  # the failure is visible, nothing invented


@pytest.mark.anyio
async def test_summary_period_and_publication_day(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "period_ig")
    loop = InstagramLoop(
        workspace_id=workspace.id, name="L", interval_min_minutes=10, interval_max_minutes=20,
        daily_limit_per_account=8, post_type="reels",
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    yesterday_evening = _at(TODAY - timedelta(days=1), 22, 0)
    # Published yesterday evening, but the row was touched again today (e.g. a
    # later reconciliation): it must still count for yesterday.
    db_session.add(InstagramPublicationJob(
        workspace_id=workspace.id, loop_id=loop.id, account_id=account.id,
        scheduled_for=yesterday_evening, published_at=yesterday_evening, updated_at=NOW, status="published",
    ))
    await db_session.commit()
    await _login(client, "owner@example.com", PW)
    yesterday = (await client.get("/api/analytics/summary", params={"period": "yesterday"})).json()
    today = (await client.get("/api/analytics/summary", params={"period": "today"})).json()
    assert yesterday["published_posts"] == 1 and [d["day"] for d in yesterday["daily_publications"]] == [
        (TODAY - timedelta(days=1)).isoformat()
    ]
    assert today["published_posts"] == 0
    week = (await client.get("/api/analytics/summary", params={"period": "7d"})).json()
    assert week["published_posts"] == 1
    bad = await client.get("/api/analytics/summary", params={"period": "custom"})
    assert bad.status_code == 422


@pytest.mark.anyio
async def test_workspace_sync_endpoint_reports_status(client, owner, collaborator):
    from tests.test_loops import _login

    await _login(client, "owner@example.com", "correct horse battery staple")
    token = (await client.get("/api/auth/csrf")).json()["csrf_token"]
    started = await client.post("/api/analytics/sync", headers={"X-CSRF-Token": token})
    assert started.status_code == 200
    assert started.json()["running"] is False and started.json()["total"] == 0
    status = await client.get("/api/analytics/sync-status")
    assert status.status_code == 200 and status.json()["finished_at"] is not None
