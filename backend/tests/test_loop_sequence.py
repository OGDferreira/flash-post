"""Per-account loop sequence, daily limit, intervals and safe retries."""

from datetime import datetime, timedelta, timezone
import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import next_local_midnight_utc
from app.loops import scheduler
from app.loops.scheduler import (
    enqueue_due_loop_publications,
    record_publication_confirmed,
    record_publication_given_up,
)
from app.models import (
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopAccountState,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
)
from tests.test_loops import _active_account, _csrf, _login


async def _setup(
    db: AsyncSession,
    workspace,
    *,
    accounts: int = 2,
    videos: int = 4,
    interval: tuple[int, int] = (60, 60),
    daily_limit: int = 100,
):
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name=f"Seq {uuid.uuid4().hex[:6]}",
        interval_min_minutes=interval[0],
        interval_max_minutes=interval[1],
        daily_limit_per_account=daily_limit,
        post_type="reels",
        repeat_media=True,
        status="active",
    )
    account_rows = [_active_account(workspace.id, f"seq_{uuid.uuid4().hex[:8]}") for _ in range(accounts)]
    db.add_all([loop, *account_rows])
    await db.flush()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    media_rows = [
        InstagramMedia(
            workspace_id=workspace.id,
            storage_path=f"{workspace.id}/{loop.id}/{index}.mp4",
            filename=f"video-{index + 1}.mp4",
            mime_type="video/mp4",
            media_type="video",
            size_bytes=10,
            created_at=base + timedelta(minutes=index),
        )
        for index in range(videos)
    ]
    db.add_all(media_rows)
    await db.flush()
    db.add_all([InstagramLoopMedia(loop_id=loop.id, media_id=m.id) for m in media_rows])
    db.add_all([InstagramLoopAccount(loop_id=loop.id, account_id=a.id) for a in account_rows])
    await db.commit()
    return loop, account_rows, media_rows


async def _active_job(db: AsyncSession, loop, account) -> InstagramPublicationJob | None:
    return await db.scalar(
        select(InstagramPublicationJob).where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.account_id == account.id,
            InstagramPublicationJob.status.in_(("queued", "publishing")),
        )
    )


async def _publish(db: AsyncSession, job: InstagramPublicationJob, when: datetime) -> None:
    job.status = "publishing"
    job.attempts += 1
    await record_publication_confirmed(db, job, when)
    await db.commit()


@pytest.mark.anyio
async def test_each_account_walks_the_whole_playlist_then_restarts(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    loop, (first, second), media = await _setup(db_session, workspace, videos=4)
    names = {m.id: m.filename for m in media}
    sequence: dict[uuid.UUID, list[str]] = {first.id: [], second.id: []}
    now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)

    # Second account joins two publications later: it must still start at video 1.
    await db_session.execute(
        InstagramLoopAccount.__table__.delete().where(InstagramLoopAccount.account_id == second.id)
    )
    await db_session.commit()
    for step in range(10):
        if step == 2:
            db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=second.id))
            await db_session.commit()
        await enqueue_due_loop_publications(db_session, now=now)
        for account in (first, second):
            job = await _active_job(db_session, loop, account)
            if job is not None:
                sequence[account.id].append(names[job.media_id])
                await _publish(db_session, job, now)
        now += timedelta(minutes=60)

    expected = [f"video-{(i % 4) + 1}.mp4" for i in range(10)]
    assert sequence[first.id] == expected
    assert sequence[second.id] == expected[:8]
    state = await db_session.get(InstagramLoopAccountState, (loop.id, first.id))
    assert state.cycles_completed == 2


@pytest.mark.anyio
async def test_interval_is_respected_and_nothing_is_queued_twice(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    loop, (account,), media = await _setup(db_session, workspace, accounts=1, interval=(30, 30))
    now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    assert await enqueue_due_loop_publications(db_session, now=now) == 1
    # A second tick (or a concurrent worker) while the job is pending adds nothing.
    assert await enqueue_due_loop_publications(db_session, now=now) == 0
    job = await _active_job(db_session, loop, account)
    await _publish(db_session, job, now)
    state = await db_session.get(InstagramLoopAccountState, (loop.id, account.id))
    assert state.next_run_at.replace(tzinfo=timezone.utc) == now + timedelta(minutes=30)
    assert await enqueue_due_loop_publications(db_session, now=now + timedelta(minutes=29)) == 0
    assert await enqueue_due_loop_publications(db_session, now=now + timedelta(minutes=30)) == 1


@pytest.mark.anyio
async def test_random_interval_stays_inside_the_configured_range(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    loop, _accounts, _media = await _setup(db_session, workspace, accounts=1, interval=(20, 45))
    values = {scheduler.random_interval(loop) for _ in range(300)}
    assert min(values) >= timedelta(minutes=20)
    assert max(values) <= timedelta(minutes=45)
    assert len(values) > 1


@pytest.mark.anyio
async def test_database_rejects_a_second_unfinished_job_for_the_same_account(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    loop, (account,), media = await _setup(db_session, workspace, accounts=1)
    now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    await enqueue_due_loop_publications(db_session, now=now)
    db_session.add(
        InstagramPublicationJob(
            workspace_id=workspace.id,
            loop_id=loop.id,
            account_id=account.id,
            media_id=media[0].id,
            scheduled_for=now + timedelta(seconds=1),
            status="queued",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.anyio
async def test_failure_does_not_advance_but_unprocessable_video_is_skipped(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    loop, (account,), media = await _setup(db_session, workspace, accounts=1, interval=(10, 10))
    now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    await enqueue_due_loop_publications(db_session, now=now)
    job = await _active_job(db_session, loop, account)
    assert job.media_id == media[0].id
    job.status = "failed"
    await record_publication_given_up(db_session, job, now)
    await db_session.commit()

    later = now + timedelta(minutes=10)
    await enqueue_due_loop_publications(db_session, now=later)
    retry = await _active_job(db_session, loop, account)
    assert retry.media_id == media[0].id  # same video again, position kept

    retry.status = "failed"
    await record_publication_given_up(db_session, retry, later, skip_media=True)
    await db_session.commit()
    await enqueue_due_loop_publications(db_session, now=later + timedelta(minutes=10))
    following = await _active_job(db_session, loop, account)
    assert following.media_id == media[1].id


@pytest.mark.anyio
async def test_daily_limit_pauses_until_next_local_day_keeping_position(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    loop, (account,), media = await _setup(
        db_session, workspace, accounts=1, interval=(5, 5), daily_limit=2
    )
    # 12:00 UTC = 09:00 in São Paulo.
    now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    for _ in range(2):
        assert await enqueue_due_loop_publications(db_session, now=now) == 1
        await _publish(db_session, await _active_job(db_session, loop, account), now)
        now += timedelta(minutes=5)

    assert await enqueue_due_loop_publications(db_session, now=now) == 0
    state = await db_session.get(InstagramLoopAccountState, (loop.id, account.id))
    assert state.blocked_reason == "daily_limit"
    midnight = next_local_midnight_utc(now)
    assert state.next_run_at.replace(tzinfo=timezone.utc) == midnight
    assert midnight == datetime(2026, 3, 3, 3, 0, tzinfo=timezone.utc)

    # Re-running the tick (e.g. after a restart) never exceeds the limit.
    assert await enqueue_due_loop_publications(db_session, now=now + timedelta(hours=10)) == 0
    assert await enqueue_due_loop_publications(db_session, now=midnight) == 1
    job = await _active_job(db_session, loop, account)
    assert job.media_id == media[2].id  # continues with video 3


@pytest.mark.anyio
async def test_in_flight_publication_counts_toward_the_daily_limit(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    loop, (account,), _media = await _setup(db_session, workspace, accounts=1, daily_limit=1)
    now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    await enqueue_due_loop_publications(db_session, now=now)
    count = await scheduler.count_publications_today(db_session, loop.id, account.id, now)
    assert count == 1


@pytest.mark.anyio
async def test_loop_settings_are_validated(client: AsyncClient, owner, db_session) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "validation_account")
    db_session.add(account)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    base = {
        "name": "Validação",
        "post_type": "reels",
        "account_ids": [str(account.id)],
    }
    bad_range = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={**base, "interval_min_minutes": 60, "interval_max_minutes": 30},
    )
    assert bad_range.status_code == 422
    for limit in (0, 101):
        bad_limit = await client.post(
            "/api/loops",
            headers={"X-CSRF-Token": token},
            json={**base, "interval_min_minutes": 30, "interval_max_minutes": 30,
                  "daily_limit_per_account": limit},
        )
        assert bad_limit.status_code == 422
    ok = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={**base, "interval_min_minutes": 30, "interval_max_minutes": 30,
              "daily_limit_per_account": 12},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["daily_limit_per_account"] == 12


class _Storage:
    async def create_signed_url(self, _path: str) -> str:
        return "https://storage.example/video.mp4"


@pytest.mark.anyio
@pytest.mark.parametrize("container_status", ["PUBLISHED", "FINISHED"])
async def test_lost_publish_response_is_reconciled_without_publishing_twice(
    db_session: AsyncSession, owner, monkeypatch: pytest.MonkeyPatch, container_status: str
) -> None:
    from app.workers import loop_scheduler

    _user, workspace = owner
    loop, (account,), media = await _setup(db_session, workspace, accounts=1, interval=(15, 15))
    now = datetime.now(timezone.utc)
    await enqueue_due_loop_publications(db_session, now=now)

    publish_calls = 0

    async def flaky_publish(_account, _media, _token, _storage, before_publish=None):
        nonlocal publish_calls
        publish_calls += 1
        await before_publish("container-777")
        raise httpx.ReadTimeout("response lost after media_publish")

    existing_publishes: list[str] = []

    async def status(_user_id, container_id, _token):
        assert container_id == "container-777"
        return container_status

    async def publish_existing(_user_id, container_id, _token):
        existing_publishes.append(container_id)
        return "ig-media-1"

    monkeypatch.setattr(loop_scheduler, "publish_media", flaky_publish)
    monkeypatch.setattr(loop_scheduler.SupabaseStorage, "from_settings", classmethod(lambda cls: _Storage()))
    monkeypatch.setattr(loop_scheduler, "fetch_container_status", status)
    monkeypatch.setattr(loop_scheduler, "publish_existing_container", publish_existing)

    assert await loop_scheduler.process_one_queued_publication() is True
    loop_id, account_id = loop.id, account.id
    first_media_id = media[0].id
    db_session.expire_all()
    job = await db_session.scalar(
        select(InstagramPublicationJob).where(InstagramPublicationJob.loop_id == loop_id)
    )
    job_id = job.id
    assert job.status == "publishing"  # held, not requeued
    assert job.error_category == "uncertain"
    assert job.container_id == "container-777"
    # Nothing else may be queued for the account while the outcome is unknown.
    assert await enqueue_due_loop_publications(db_session, now=now + timedelta(hours=1)) == 0
    assert await loop_scheduler.process_one_queued_publication() is False

    resolved = await loop_scheduler.reconcile_uncertain_publications(now + timedelta(minutes=5))
    assert resolved == 1
    db_session.expire_all()
    job = await db_session.get(InstagramPublicationJob, job_id)
    assert job.status == "published"
    assert publish_calls == 1
    assert existing_publishes == (["container-777"] if container_status == "FINISHED" else [])
    state = await db_session.get(InstagramLoopAccountState, (loop_id, account_id))
    assert state.last_media_id == first_media_id
    total = await db_session.scalar(
        select(func.count(InstagramPublicationJob.id)).where(InstagramPublicationJob.loop_id == loop_id)
    )
    assert total == 1


@pytest.mark.anyio
async def test_unresolvable_outcome_blocks_the_account_for_review(
    db_session: AsyncSession, owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers import loop_scheduler

    _user, workspace = owner
    loop, (account,), _media = await _setup(db_session, workspace, accounts=1)
    requested = datetime.now(timezone.utc) - timedelta(hours=25)
    await enqueue_due_loop_publications(db_session, now=requested)
    job = await _active_job(db_session, loop, account)
    job.status = "publishing"
    job.container_id = "container-x"
    job.publish_requested_at = requested
    job.next_retry_at = requested
    await db_session.commit()

    async def unreachable(*_args):
        return None

    monkeypatch.setattr(loop_scheduler, "fetch_container_status", unreachable)
    job_id, key = job.id, (loop.id, account.id)
    await loop_scheduler.reconcile_uncertain_publications()
    db_session.expire_all()
    job = await db_session.get(InstagramPublicationJob, job_id)
    state = await db_session.get(InstagramLoopAccountState, key)
    assert job.status == "failed"
    assert state.blocked_reason == "needs_review"
    assert await enqueue_due_loop_publications(db_session) == 0


@pytest.mark.anyio
async def test_worker_restart_before_media_publish_requeues_same_video(
    db_session: AsyncSession, owner
) -> None:
    from app.workers import loop_scheduler

    _user, workspace = owner
    loop, (account,), media = await _setup(db_session, workspace, accounts=1)
    now = datetime.now(timezone.utc)
    await enqueue_due_loop_publications(db_session, now=now)
    job = await _active_job(db_session, loop, account)
    job.status = "publishing"
    job.attempts = 1
    job.updated_at = now - timedelta(hours=2)
    await db_session.commit()

    job_id, first_media_id = job.id, media[0].id
    await loop_scheduler.fail_stale_publication_jobs(now)
    db_session.expire_all()
    job = await db_session.get(InstagramPublicationJob, job_id)
    assert job.status == "queued"
    assert job.media_id == first_media_id


@pytest.mark.anyio
async def test_concurrent_ticks_queue_a_single_job_per_account(
    db_session: AsyncSession, owner
) -> None:
    import asyncio

    from app.core.database import get_session_factory

    _user, workspace = owner
    loop, accounts, _media = await _setup(db_session, workspace, accounts=3)
    loop_id = loop.id
    now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)

    async def tick() -> int:
        async with get_session_factory()() as session:
            try:
                return await enqueue_due_loop_publications(session, now=now)
            except Exception:
                await session.rollback()
                return 0

    results = await asyncio.gather(*(tick() for _ in range(4)))
    assert sum(results) == 3
    total = await db_session.scalar(
        select(func.count(InstagramPublicationJob.id)).where(
            InstagramPublicationJob.loop_id == loop_id,
            InstagramPublicationJob.status == "queued",
        )
    )
    assert total == 3
