import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.models import InstagramAccount, MilestoneNotification, PushSubscription
from app.notifications import engagement as eng
from app.notifications import goals as goals_module
from app.notifications import milestones as ms
from app.notifications.webpush import PushResult
from tests.test_push_goals import ENDPOINT, _browser_keys

TODAY = date(2026, 10, 15)


def test_streak_and_record_math() -> None:
    counts = {TODAY - timedelta(days=d): 5 for d in range(1, 4)}  # 3 days in a row
    counts[TODAY - timedelta(days=5)] = 9
    stats = eng.compute_stats(counts | {TODAY: 2}, TODAY, goal=5)
    assert stats.streak_before_today == 3 and stats.streak == 3
    assert stats.missing_today == 3 and not stats.met_today
    assert stats.best_previous == 9 and not stats.is_record_today
    assert eng.compute_stats(counts | {TODAY: 10}, TODAY, goal=5).is_record_today
    assert eng.compute_stats(counts | {TODAY: 5}, TODAY, goal=5).streak == 4
    # No goal: one connection keeps the streak.
    assert eng.compute_stats({TODAY - timedelta(days=1): 1}, TODAY, goal=0).streak_before_today == 1


def test_ranking_events_detect_overtake_and_new_leader() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    previous = {a: (1, 5), b: (2, 4), c: (3, 1)}
    current = [(b, "Bia", 6), (a, "Ana", 5), (c, "Caio", 1)]
    events = eng.ranking_events(previous, current)
    assert events[b] == ("top", None)
    assert events[a] == ("passed", "Bia")
    assert c not in events
    assert eng.ranking_events({}, current) == {}


def _account(workspace_id, user_id, suffix, connected_at):
    return InstagramAccount(
        workspace_id=workspace_id,
        instagram_user_id=f"17840099{suffix}",
        username=f"eng_{suffix}",
        encrypted_access_token=encrypt_value(f"t-{suffix}"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        connected_at=connected_at,
        first_connected_at=connected_at,
        status="connected",
        connected_by_user_id=user_id,
    )


@pytest.mark.anyio
async def test_engagement_tick_streak_warning_and_summary(
    db_session: AsyncSession, owner, collaborator, monkeypatch: pytest.MonkeyPatch
) -> None:
    _owner_user, workspace = owner
    # Collaborator connected 1 account on each of the last 3 days, none today.
    for days in range(1, 4):
        stamp = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc) - timedelta(days=days)
        db_session.add(_account(workspace.id, collaborator.id, f"{days:02d}", stamp))
    _private, p256dh, auth = _browser_keys()
    db_session.add(
        PushSubscription(
            user_id=collaborator.id, workspace_id=workspace.id, endpoint=ENDPOINT, p256dh=p256dh, auth=auth
        )
    )
    await db_session.commit()
    sent: list[dict] = []

    async def fake_send(_client, **kwargs):
        sent.append(kwargs["payload"])
        return PushResult(ok=True, gone=False, status_code=201)

    async def fake_views(*_args):
        return 4321

    monkeypatch.setattr(ms, "send_web_push", fake_send)
    monkeypatch.setattr(goals_module, "fetch_instagram_views", fake_views)

    # 23:30 UTC = 20:30 in São Paulo: streak warning only.
    evening = datetime(2026, 10, 15, 23, 30, tzinfo=timezone.utc)
    await ms.run_milestones_tick(db_session, evening, refresh_followers=False)
    titles = [p["title"] for p in sent]
    assert any("sequência" in t.lower() or "seguidos" in t or "Sequência" in t for t in titles)
    assert not any("Resumo" in t or "Fechamento" in t or "Seu dia" in t for t in titles)

    # 01:10 UTC next day = 22:10 local on Oct 15: nightly summary, once.
    night = datetime(2026, 10, 16, 1, 10, tzinfo=timezone.utc)
    sent.clear()
    await ms.run_milestones_tick(db_session, night, refresh_followers=False)
    summaries = [p for p in sent if p["tag"] == "fun-summary"]
    assert len(summaries) == 1 and "0 conexões" in summaries[0]["body"]
    sent.clear()
    await ms.run_milestones_tick(db_session, night + timedelta(minutes=15), refresh_followers=False)
    assert not [p for p in sent if p["tag"] in {"fun-summary", "fun-streak_warn"}]
    kinds = set((await db_session.scalars(select(MilestoneNotification.kind))).all())
    assert {"streak_warn", "summary"} <= kinds
