from datetime import datetime, timedelta, timezone
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.instagram.publishing import InstagramPublishingError
from app.loops.scheduler import enqueue_due_loop_publications
from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
)
from app.workers.loop_scheduler import (
    CONSECUTIVE_PUBLICATION_FAILURE_LIMIT,
    _update_account_health_after_failure,
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


def _active_account(workspace_id: uuid.UUID, username: str) -> InstagramAccount:
    return InstagramAccount(
        workspace_id=workspace_id,
        instagram_user_id=f"ig-{username}",
        username=username,
        encrypted_access_token=encrypt_value("token-for-tests"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=45),
        status="connected",
    )


@pytest.mark.anyio
async def test_owner_can_create_and_read_a_loop(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "flashpost_demo")
    db_session.add(account)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Reels da semana",
            "interval_min_minutes": 20,
            "interval_max_minutes": 40,
            "post_type": "reels",
            "repeat_media": False,
            "account_ids": [str(account.id)],
        },
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["name"] == "Reels da semana"
    assert result["repeat_media"] is False
    assert result["status"] == "active"
    assert "daily_limit_per_account" not in result
    assert (
        datetime.fromisoformat(result["next_run_at"])
        <= datetime.now(timezone.utc) + timedelta(seconds=5)
    )
    assert [item["id"] for item in result["accounts"]] == [str(account.id)]
    assert result["waiting_for_media_count"] == 0
    assert result["published_today_count"] == 0
    assert result["media_count"] == 0

    listing = await client.get("/api/loops")
    assert listing.status_code == 200
    assert listing.json()["loops"][0]["id"] == result["id"]
    assert listing.json()["available_accounts"][0]["username"] == "flashpost_demo"
    assert "publishing_enabled" in listing.json()


@pytest.mark.anyio
async def test_new_reel_loop_queues_the_same_first_video_for_every_account(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    accounts = [
        _active_account(workspace.id, "broadcast_one"),
        _active_account(workspace.id, "broadcast_two"),
    ]
    videos = [
        InstagramMedia(
            workspace_id=workspace.id,
            storage_path=f"{workspace.id}/broadcast/{index}.mp4",
            filename=f"{index}.mp4",
            mime_type="video/mp4",
            media_type="video",
            size_bytes=100,
        )
        for index in range(2)
    ]
    db_session.add_all([*accounts, *videos])
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Broadcast Reels",
            "interval_min_minutes": 20,
            "interval_max_minutes": 40,
            "daily_limit_per_account": 6,
            "post_type": "reels",
            "repeat_media": True,
            "account_ids": [str(account.id) for account in accounts],
            "media_ids": [str(video.id) for video in videos],
        },
    )

    assert response.status_code == 201, response.text
    jobs = (
        await db_session.scalars(
            select(InstagramPublicationJob).where(
                InstagramPublicationJob.loop_id == uuid.UUID(response.json()["id"])
            )
        )
    ).all()
    assert {job.account_id for job in jobs} == {account.id for account in accounts}
    assert len(jobs) == len(accounts)
    assert len({job.media_id for job in jobs}) == 1
    assert jobs[0].media_id in {video.id for video in videos}
    assert all(job.status == "queued" for job in jobs)
    assert all(
        job.scheduled_for.replace(tzinfo=timezone.utc)
        <= datetime.now(timezone.utc) + timedelta(seconds=5)
        for job in jobs
    )


@pytest.mark.anyio
async def test_account_added_to_loop_immediately_gets_next_video(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    existing_account = _active_account(workspace.id, "already_in_loop")
    added_account = _active_account(workspace.id, "newly_added")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Add account broadcast",
        interval_min_minutes=20,
        interval_max_minutes=40,
        daily_limit_per_account=6,
        post_type="reels",
        repeat_media=True,
        status="active",
        next_run_at=now + timedelta(minutes=20),
    )
    videos = [
        InstagramMedia(
            workspace_id=workspace.id,
            storage_path=f"{workspace.id}/add-account/{index}.mp4",
            filename=f"{index}.mp4",
            mime_type="video/mp4",
            media_type="video",
            size_bytes=100,
            created_at=now - timedelta(minutes=2 - index),
        )
        for index in range(2)
    ]
    db_session.add_all([existing_account, added_account, loop, *videos])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=loop.id, account_id=existing_account.id),
            *[
                InstagramLoopMedia(loop_id=loop.id, media_id=video.id)
                for video in videos
            ],
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=existing_account.id,
                media_id=videos[0].id,
                scheduled_for=now - timedelta(minutes=20),
                status="published",
                attempts=1,
                updated_at=now - timedelta(minutes=20),
            ),
        ]
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.put(
        f"/api/loops/{loop.id}/accounts",
        headers={"X-CSRF-Token": token},
        json={"account_ids": [str(existing_account.id), str(added_account.id)]},
    )

    assert response.status_code == 200, response.text
    job = await db_session.scalar(
        select(InstagramPublicationJob).where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.account_id == added_account.id,
        )
    )
    assert job is not None
    assert job.media_id == videos[1].id
    assert job.status == "queued"
    assert job.scheduled_for.replace(tzinfo=timezone.utc) >= now - timedelta(seconds=5)


@pytest.mark.anyio
async def test_owner_can_view_failed_publication_details_in_error_log(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "failure_log_account")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Failure log loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=3,
        post_type="reels",
        repeat_media=True,
        status="active",
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    db_session.add(
        InstagramPublicationJob(
            workspace_id=workspace.id,
            loop_id=loop.id,
            account_id=account.id,
            scheduled_for=datetime.now(timezone.utc),
            status="failed",
            attempts=1,
            last_error="Instagram rejected the publication request (HTTP 400).",
        )
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    response = await client.get("/api/loops/failures")

    assert response.status_code == 200, response.text
    assert response.json()["failures"][0]["account_username"] == "failure_log_account"
    assert response.json()["failures"][0]["error"] == (
        "Instagram rejected the publication request (HTTP 400)."
    )


@pytest.mark.anyio
async def test_loop_rejects_expired_and_cross_workspace_accounts(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    expired = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="expired-account",
        username="expired",
        encrypted_access_token=encrypt_value("expired-token"),
        token_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        status="connected",
    )
    disconnected = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="disconnected-account",
        username="disconnected",
        encrypted_access_token=None,
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        status="disconnected",
    )
    db_session.add_all([expired, disconnected])
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    for account in (expired, disconnected):
        response = await client.post(
            "/api/loops",
            headers={"X-CSRF-Token": token},
            json={
                "name": "Invalid account loop",
                "interval_min_minutes": 5,
                "interval_max_minutes": 5,
                "daily_limit_per_account": 1,
                "account_ids": [str(account.id)],
            },
        )
        assert response.status_code == 422


@pytest.mark.anyio
async def test_loop_accepts_more_than_24_videos(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "twenty_four_videos")
    videos = [
        InstagramMedia(
            workspace_id=workspace.id,
            storage_path=f"{workspace.id}/batch/{index}.mp4",
            filename=f"{index}.mp4",
            mime_type="video/mp4",
            media_type="video",
            size_bytes=100,
        )
        for index in range(25)
    ]
    db_session.add_all([account, *videos])
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    payload = {
        "name": "Loop com mais de 24 vídeos",
        "interval_min_minutes": 20,
        "interval_max_minutes": 40,
        "daily_limit_per_account": 24,
        "post_type": "reels",
        "repeat_media": False,
        "account_ids": [str(account.id)],
        "media_ids": [str(media.id) for media in videos],
    }

    response = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json=payload,
    )

    assert response.status_code == 201, response.text
    assert len(response.json()["media_ids"]) == 25
    assert response.json()["media_count"] == 25

    listing = await client.get("/api/loops")
    assert listing.status_code == 200
    assert listing.json()["loops"][0]["media_count"] == 25


@pytest.mark.anyio
async def test_removing_media_from_loop_keeps_workspace_file_and_other_loop_link(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "loop_media_removal")
    first_loop = InstagramLoop(
        workspace_id=workspace.id,
        name="First loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=24,
        post_type="reels",
        repeat_media=True,
        status="active",
    )
    second_loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Second loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=24,
        post_type="reels",
        repeat_media=True,
        status="active",
    )
    media = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/loop-media/removal.mp4",
        filename="removal.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
    )
    db_session.add_all([account, first_loop, second_loop, media])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=first_loop.id, account_id=account.id),
            InstagramLoopMedia(loop_id=first_loop.id, media_id=media.id),
            InstagramLoopMedia(loop_id=second_loop.id, media_id=media.id),
        ]
    )
    queued_job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=first_loop.id,
        account_id=account.id,
        media_id=media.id,
        scheduled_for=datetime.now(timezone.utc),
        status="queued",
    )
    db_session.add(queued_job)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.delete(
        f"/api/loops/{first_loop.id}/media/{media.id}",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 204
    assert await db_session.get(InstagramMedia, media.id) is not None
    assert await db_session.get(InstagramLoopMedia, (first_loop.id, media.id)) is None
    assert await db_session.get(InstagramLoopMedia, (second_loop.id, media.id)) is not None
    await db_session.refresh(queued_job)
    assert queued_job.status == "waiting_for_media"
    assert queued_job.media_id is None


@pytest.mark.anyio
async def test_media_preview_redirects_to_a_temporary_storage_url(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, workspace = owner
    media = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/loop-media/preview.mp4",
        filename="preview.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
    )
    db_session.add(media)
    await db_session.commit()

    class FakeStorage:
        async def create_signed_url(self, path: str) -> str:
            assert path == media.storage_path
            return "https://storage.example/signed-preview"

    monkeypatch.setattr(
        "app.instagram.media_router._storage_or_http_error",
        lambda: FakeStorage(),
    )
    await _login(client, "owner@example.com", "correct horse battery staple")

    response = await client.get(f"/api/media/{media.id}/preview", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://storage.example/signed-preview"


@pytest.mark.anyio
async def test_collaborator_can_only_associate_accounts_with_existing_loops(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    collaborator,
) -> None:
    _owner_user, workspace = owner
    account = _active_account(workspace.id, "collaborator_loop_account")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Owner-configured loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=2,
        post_type="reels",
        repeat_media=True,
        status="active",
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
    additional_account = _active_account(workspace.id, "collaborator_additional_account")
    db_session.add(additional_account)
    await db_session.commit()
    await _login(client, "collaborator@example.com", "collaborator password")
    token = await _csrf(client)

    create_response = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Collaborator loop",
            "interval_min_minutes": 5,
            "interval_max_minutes": 10,
            "daily_limit_per_account": 2,
            "account_ids": [str(account.id)],
        },
    )

    assert create_response.status_code == 403
    update_response = await client.put(
        f"/api/loops/{loop.id}/accounts",
        headers={"X-CSRF-Token": token},
        json={"account_ids": [str(account.id), str(additional_account.id)]},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["name"] == "Owner-configured loop"
    assert {item["id"] for item in update_response.json()["accounts"]} == {
        str(account.id),
        str(additional_account.id),
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure_count", "expected_status"),
    [
        (CONSECUTIVE_PUBLICATION_FAILURE_LIMIT, "connected"),
        (CONSECUTIVE_PUBLICATION_FAILURE_LIMIT + 1, "error"),
    ],
)
async def test_account_enters_error_state_after_more_than_five_consecutive_failed_posts(
    db_session: AsyncSession,
    owner,
    failure_count: int,
    expected_status: str,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, f"failure-{failure_count}")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name=f"Failure loop {failure_count}",
        interval_min_minutes=5,
        interval_max_minutes=10,
        daily_limit_per_account=24,
        post_type="reels",
        repeat_media=True,
        status="active",
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=account.id,
                scheduled_for=now - timedelta(minutes=failure_count - index),
                status="failed",
                attempts=1,
                last_error="Test publication rejection.",
                updated_at=now - timedelta(minutes=failure_count - index),
            )
            for index in range(failure_count)
        ]
    )
    await db_session.commit()

    await _update_account_health_after_failure(
        db_session,
        account.id,
        InstagramPublishingError("Instagram rejected media."),
    )
    await db_session.refresh(account)
    assert account.status == expected_status


@pytest.mark.anyio
async def test_authentication_rejection_immediately_marks_account_as_errored(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "lost-auth-account")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Account health test",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=3,
        post_type="reels",
        repeat_media=True,
        status="active",
    )
    db_session.add(account)
    db_session.add(loop)
    await db_session.flush()
    db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
    queued_job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=account.id,
        scheduled_for=datetime.now(timezone.utc),
        status="queued",
        attempts=0,
    )
    db_session.add(queued_job)
    await db_session.commit()

    await _update_account_health_after_failure(
        db_session,
        account.id,
        InstagramPublishingError(
            "Instagram rejected media (HTTP 403).",
            status_code=403,
        ),
    )
    await db_session.refresh(account)
    assert account.status == "error"
    assert await db_session.get(InstagramLoopAccount, (loop.id, account.id)) is None
    assert await db_session.get(InstagramPublicationJob, queued_job.id) is None


@pytest.mark.anyio
async def test_scheduler_creates_one_waiting_publication_job_per_due_loop(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    account = _active_account(workspace.id, "scheduler_target")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Due loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=3,
        post_type="reels",
        repeat_media=True,
        status="active",
        next_run_at=now - timedelta(minutes=1),
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
    await db_session.commit()

    created = await enqueue_due_loop_publications(db_session, now=now)
    jobs = (
        await db_session.scalars(
            select(InstagramPublicationJob).where(
                InstagramPublicationJob.loop_id == loop.id
            )
        )
    ).all()
    await db_session.refresh(loop)
    assert created == 1
    assert len(jobs) == 1
    assert jobs[0].status == "waiting_for_media"
    assert jobs[0].account_id == account.id
    assert loop.last_run_at is not None
    assert loop.next_run_at is not None
    assert loop.next_run_at.replace(tzinfo=timezone.utc) > now

    second_tick = await enqueue_due_loop_publications(db_session, now=now)
    assert second_tick == 0


@pytest.mark.anyio
async def test_scheduler_ignores_legacy_daily_limit_setting(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    account = _active_account(workspace.id, "unlimited_daily_posts")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="No configured daily cap",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=1,
        post_type="reels",
        repeat_media=True,
        status="active",
        next_run_at=now - timedelta(minutes=1),
    )
    media = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/unlimited/daily.mp4",
        filename="daily.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
    )
    db_session.add_all([account, loop, media])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=loop.id, account_id=account.id),
            InstagramLoopMedia(loop_id=loop.id, media_id=media.id),
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=account.id,
                media_id=media.id,
                scheduled_for=now - timedelta(minutes=5),
                status="published",
                attempts=1,
                updated_at=now - timedelta(minutes=5),
            ),
        ]
    )
    await db_session.commit()

    created = await enqueue_due_loop_publications(db_session, now=now)

    assert created == 1
    jobs = (
        await db_session.scalars(
            select(InstagramPublicationJob).where(
                InstagramPublicationJob.loop_id == loop.id
            )
        )
    ).all()
    assert len(jobs) == 2
    assert {job.status for job in jobs} == {"published", "queued"}


@pytest.mark.anyio
async def test_scheduler_skips_expired_account_and_respects_paused_loop(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    expired = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="expired-scheduled-account",
        username="expired_target",
        encrypted_access_token=encrypt_value("expired-token"),
        token_expires_at=now - timedelta(minutes=1),
        status="connected",
    )
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Paused loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=3,
        post_type="images",
        repeat_media=False,
        status="paused",
        next_run_at=now - timedelta(minutes=1),
    )
    db_session.add_all([expired, loop])
    await db_session.flush()
    db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=expired.id))
    await db_session.commit()

    created = await enqueue_due_loop_publications(db_session, now=now)
    jobs = (
        await db_session.scalars(
            select(InstagramPublicationJob).where(
                InstagramPublicationJob.loop_id == loop.id
            )
        )
    ).all()
    assert created == 0
    assert jobs == []


@pytest.mark.anyio
async def test_scheduler_queues_matching_loop_media(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    account = _active_account(workspace.id, "media_target")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Media loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=3,
        post_type="reels",
        repeat_media=True,
        status="active",
        next_run_at=now - timedelta(minutes=1),
    )
    media = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/sample/reel.mp4",
        filename="reel.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
    )
    db_session.add_all([account, loop, media])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=loop.id, account_id=account.id),
            InstagramLoopMedia(loop_id=loop.id, media_id=media.id),
        ]
    )
    await db_session.commit()

    created = await enqueue_due_loop_publications(db_session, now=now)
    job = await db_session.scalar(
        select(InstagramPublicationJob).where(
            InstagramPublicationJob.loop_id == loop.id
        )
    )
    assert created == 1
    assert job is not None
    assert job.media_id == media.id
    assert job.status == "queued"


@pytest.mark.anyio
async def test_scheduler_broadcasts_each_video_to_all_accounts_in_queue_order(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    accounts = [
        _active_account(workspace.id, "playlist_account_one"),
        _active_account(workspace.id, "playlist_account_two"),
    ]
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Synchronized reel playlist",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=6,
        post_type="reels",
        repeat_media=True,
        status="active",
        next_run_at=now - timedelta(minutes=1),
    )
    videos = [
        InstagramMedia(
            workspace_id=workspace.id,
            storage_path=f"{workspace.id}/playlist/{index}.mp4",
            filename=f"{index}.mp4",
            mime_type="video/mp4",
            media_type="video",
            size_bytes=100,
            created_at=now - timedelta(minutes=2 - index),
        )
        for index in range(2)
    ]
    db_session.add_all([*accounts, loop, *videos])
    await db_session.flush()
    db_session.add_all(
        [
            *[
                InstagramLoopAccount(loop_id=loop.id, account_id=account.id)
                for account in accounts
            ],
            *[
                InstagramLoopMedia(loop_id=loop.id, media_id=video.id)
                for video in videos
            ],
        ]
    )
    await db_session.commit()

    first_count = await enqueue_due_loop_publications(db_session, now=now)
    first_jobs = (
        await db_session.scalars(
            select(InstagramPublicationJob)
            .where(InstagramPublicationJob.loop_id == loop.id)
            .order_by(InstagramPublicationJob.account_id)
        )
    ).all()
    assert first_count == len(accounts)
    assert {job.account_id for job in first_jobs} == {account.id for account in accounts}
    assert {job.media_id for job in first_jobs} == {videos[0].id}

    for job in first_jobs:
        job.status = "published"
        job.updated_at = now
    second_tick = now + timedelta(minutes=2)
    loop.next_run_at = second_tick
    await db_session.commit()
    second_count = await enqueue_due_loop_publications(db_session, now=second_tick)
    all_jobs = (
        await db_session.scalars(
            select(InstagramPublicationJob).where(
                InstagramPublicationJob.loop_id == loop.id,
                InstagramPublicationJob.status == "queued",
            )
        )
    ).all()
    assert second_count == len(accounts)
    assert len(all_jobs) == len(accounts)
    assert {job.account_id for job in all_jobs} == {account.id for account in accounts}
    assert {job.media_id for job in all_jobs} == {videos[1].id}


@pytest.mark.anyio
async def test_scheduler_releases_waiting_job_after_media_is_added(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    account = _active_account(workspace.id, "waiting_media_target")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Waiting loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=3,
        post_type="images",
        repeat_media=True,
        status="active",
        next_run_at=now + timedelta(minutes=10),
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=account.id,
        scheduled_for=now - timedelta(minutes=1),
        status="waiting_for_media",
    )
    db_session.add(job)
    await db_session.flush()
    db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
    media = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/sample/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        media_type="image",
        size_bytes=100,
    )
    db_session.add(media)
    await db_session.flush()
    db_session.add(InstagramLoopMedia(loop_id=loop.id, media_id=media.id))
    await db_session.commit()

    created = await enqueue_due_loop_publications(db_session, now=now)
    await db_session.refresh(job)
    assert created == 0
    assert job.media_id == media.id
    assert job.status == "queued"


@pytest.mark.anyio
async def test_pausing_loop_stops_queued_job_and_prevents_delete_during_publish(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "pause_target")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Pause loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=3,
        post_type="images",
        repeat_media=True,
        status="active",
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    media = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/pause/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        media_type="image",
        size_bytes=100,
    )
    db_session.add_all([account, loop, media])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=loop.id, account_id=account.id),
            InstagramLoopMedia(loop_id=loop.id, media_id=media.id),
        ]
    )
    job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=account.id,
        media_id=media.id,
        scheduled_for=datetime.now(timezone.utc),
        status="queued",
    )
    db_session.add(job)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    csrf = await _csrf(client)

    pause_response = await client.patch(
        f"/api/loops/{loop.id}/status",
        headers={"X-CSRF-Token": csrf},
        json={"enabled": False},
    )
    assert pause_response.status_code == 200
    await db_session.refresh(job)
    assert job.status == "waiting_for_media"
    assert job.media_id is None

    job.status = "publishing"
    await db_session.commit()
    delete_response = await client.delete(
        f"/api/loops/{loop.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert delete_response.status_code == 409
