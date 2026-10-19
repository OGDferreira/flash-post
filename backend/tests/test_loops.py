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
    DiagnosticsEvent,
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
)
from app.workers.loop_scheduler import (
    _mark_account_as_error,
    _record_publication_failure,
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
    assert result["repeat_media"] is True
    assert result["status"] == "active"
    assert result["daily_limit_per_account"] == 100
    # No media yet: nothing is queued, the account is due as soon as media exists.
    assert result["next_run_at"] is not None
    assert result["queued_publication_count"] == 0
    assert [item["id"] for item in result["accounts"]] == [str(account.id)]
    assert result["accounts"][0]["connected_at"]
    assert result["accounts"][0]["status"] == "connected"
    assert result["accounts"][0]["error_at"] is None
    assert result["waiting_for_media_count"] == 0
    assert result["published_today_count"] == 0
    assert result["media_count"] == 0
    assert result["active_accounts_count"] == 1

    listing = await client.get("/api/loops")
    assert listing.status_code == 200
    assert listing.json()["loops"][0]["id"] == result["id"]
    assert listing.json()["available_accounts"][0]["username"] == "flashpost_demo"
    assert "publishing_enabled" in listing.json()

    errored_account = _active_account(workspace.id, "flashpost_error")
    errored_account.status = "error"
    db_session.add(errored_account)
    await db_session.flush()
    db_session.add(
        InstagramLoopAccount(
            loop_id=uuid.UUID(result["id"]),
            account_id=errored_account.id,
        )
    )
    await db_session.commit()
    refreshed = await client.get("/api/loops")
    assert refreshed.status_code == 200
    assert refreshed.json()["loops"][0]["active_accounts_count"] == 1
    assert [
        item["username"] for item in refreshed.json()["loops"][0]["accounts"]
    ] == ["flashpost_demo"]


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
    assert len({job.queue_sequence for job in jobs}) == len(jobs)
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
    added_accounts = [
        _active_account(workspace.id, "newly_added_a"),
        _active_account(workspace.id, "newly_added_b"),
    ]
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
        for index in range(3)
    ]
    db_session.add_all([existing_account, *added_accounts, loop, *videos])
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
        json={
            "account_ids": [
                str(existing_account.id),
                *[str(account.id) for account in added_accounts],
            ]
        },
    )

    assert response.status_code == 200, response.text
    jobs = (
        await db_session.scalars(
            select(InstagramPublicationJob)
            .where(InstagramPublicationJob.loop_id == loop.id)
            .where(
                InstagramPublicationJob.account_id.in_(
                    [account.id for account in added_accounts]
                )
            )
            .order_by(InstagramPublicationJob.queue_sequence)
        )
    ).all()
    assert [job.account_id for job in jobs] == [
        account.id for account in added_accounts
    ]
    assert [job.media_id for job in jobs] == [videos[0].id, videos[0].id]
    assert all(job.status == "queued" for job in jobs)
    assert all(
        job.scheduled_for.replace(tzinfo=timezone.utc)
        >= now - timedelta(seconds=5)
        for job in jobs
    )


@pytest.mark.anyio
async def test_loop_queue_count_includes_waiting_queued_and_publishing(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    account = _active_account(workspace.id, "queue_count_account")
    media = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/queue-count/video.mp4",
        filename="video.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
    )
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Queue count loop",
        interval_min_minutes=50,
        interval_max_minutes=60,
        post_type="reels",
        repeat_media=True,
        status="active",
    )
    db_session.add_all([account, media, loop])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=loop.id, account_id=account.id),
            InstagramLoopMedia(loop_id=loop.id, media_id=media.id),
        ]
    )
    # One unfinished job per account is allowed, so each status uses its own account.
    extra_accounts = [
        _active_account(workspace.id, f"queue_count_{index}") for index in range(3)
    ]
    db_session.add_all(extra_accounts)
    await db_session.flush()
    for index, status_value in enumerate(
        ("waiting_for_media", "queued", "publishing", "published", "failed")
    ):
        db_session.add(
            InstagramPublicationJob(
                workspace_id=workspace.id,
                loop_id=loop.id,
                account_id=(extra_accounts[index].id if index < 3 else account.id),
                media_id=None if status_value == "waiting_for_media" else media.id,
                scheduled_for=now + timedelta(seconds=index),
                status=status_value,
                attempts=1 if status_value in {"publishing", "published", "failed"} else 0,
            )
        )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    response = await client.get("/api/loops")

    assert response.status_code == 200, response.text
    loop_response = next(
        item for item in response.json()["loops"] if item["id"] == str(loop.id)
    )
    assert loop_response["waiting_for_media_count"] == 1
    assert loop_response["queued_publication_count"] == 3
    assert loop_response["video_count"] == 1
    assert loop_response["attempts_count"] == 3


@pytest.mark.anyio
async def test_owner_can_view_failed_publication_details_in_error_log(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    failed_at = datetime(2026, 10, 10, 14, 30, tzinfo=timezone.utc)
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
            updated_at=failed_at,
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
    assert response.json()["failures"][0]["account_in_loop"] is False

    loops_response = await client.get("/api/loops")
    assert loops_response.status_code == 200, loops_response.text
    loop_response = next(
        item for item in loops_response.json()["loops"] if item["id"] == str(loop.id)
    )
    assert loop_response["latest_failed_at"] == failed_at.isoformat().replace(
        "+00:00", "Z"
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
async def test_loop_media_is_private_unless_the_loop_is_cloned(
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
    media = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/loop-media/removal.mp4",
        filename="removal.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
    )
    db_session.add_all([account, first_loop, media])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=first_loop.id, account_id=account.id),
            InstagramLoopMedia(loop_id=first_loop.id, media_id=media.id),
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

    cloned = await client.post(
        f"/api/loops/{first_loop.id}/clone",
        headers={"X-CSRF-Token": token},
    )
    assert cloned.status_code == 201, cloned.text
    clone_id = uuid.UUID(cloned.json()["id"])
    assert cloned.json()["status"] == "paused"
    assert cloned.json()["media_names"] == ["removal.mp4"]

    duplicate = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Uncloned duplicate",
            "interval_min_minutes": 10,
            "interval_max_minutes": 20,
            "post_type": "reels",
            "repeat_media": True,
            "account_ids": [str(account.id)],
            "media_ids": [str(media.id)],
        },
    )
    assert duplicate.status_code == 409
    assert "Clone o loop" in duplicate.json()["detail"]

    empty_loop = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Loop sem mídias",
            "interval_min_minutes": 10,
            "interval_max_minutes": 20,
            "post_type": "reels",
            "repeat_media": True,
            "account_ids": [str(account.id)],
            "media_ids": [],
        },
    )
    assert empty_loop.status_code == 201, empty_loop.text
    update_duplicate = await client.put(
        f"/api/loops/{empty_loop.json()['id']}",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Loop sem mídias",
            "interval_min_minutes": 10,
            "interval_max_minutes": 20,
            "post_type": "reels",
            "repeat_media": True,
            "account_ids": [str(account.id)],
            "media_ids": [str(media.id)],
        },
    )
    assert update_duplicate.status_code == 409

    response = await client.delete(
        f"/api/loops/{first_loop.id}/media/{media.id}",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 204
    assert await db_session.get(InstagramMedia, media.id) is not None
    assert await db_session.get(InstagramLoopMedia, (first_loop.id, media.id)) is None
    assert await db_session.get(InstagramLoopMedia, (clone_id, media.id)) is not None
    # The not-started job for the removed media is dropped (no progress lost).
    assert (
        await db_session.scalar(
            select(InstagramPublicationJob).where(InstagramPublicationJob.id == queued_job.id)
        )
        is None
    )


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
@pytest.mark.parametrize("failure_count", [5, 12])
async def test_account_stays_connected_after_many_isolated_publication_failures(
    db_session: AsyncSession,
    owner,
    failure_count: int,
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
    assert account.status == "connected"


@pytest.mark.anyio
async def test_authentication_rejection_immediately_marks_account_as_errored(
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.workers import loop_scheduler

    async def token_rejected(_account):
        return "invalid"

    # A bare 403 is ambiguous: the token is checked with Meta before isolating.
    monkeypatch.setattr(loop_scheduler, "verify_account_token", token_rejected)
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
    assert account.error_at is not None
    assert await db_session.get(InstagramLoopAccount, (loop.id, account.id)) is None
    assert await db_session.get(InstagramPublicationJob, queued_job.id) is None


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
    # Pausing drops jobs that never started; the account keeps its position.
    assert (
        await db_session.scalar(
            select(InstagramPublicationJob).where(InstagramPublicationJob.id == job.id)
        )
        is None
    )

    db_session.add(
        InstagramPublicationJob(
            workspace_id=workspace.id,
            loop_id=loop.id,
            account_id=account.id,
            media_id=media.id,
            scheduled_for=datetime.now(timezone.utc),
            status="publishing",
            attempts=1,
        )
    )
    await db_session.commit()
    delete_response = await client.delete(
        f"/api/loops/{loop.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert delete_response.status_code == 409


@pytest.mark.anyio
async def test_restarting_loop_clears_its_failed_publication_history(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "restart_failure_account")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Restart failure reset",
        interval_min_minutes=10,
        interval_max_minutes=20,
        post_type="images",
        repeat_media=True,
        status="paused",
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=account.id,
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=5),
        status="failed",
        attempts=1,
        last_error="A previous publication failed.",
    )
    db_session.add(job)
    await db_session.flush()
    db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    csrf = await _csrf(client)

    response = await client.patch(
        f"/api/loops/{loop.id}/status",
        headers={"X-CSRF-Token": csrf},
        json={"enabled": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["failed_count"] == 0
    assert (
        await db_session.scalar(
            select(InstagramPublicationJob).where(
                InstagramPublicationJob.id == job.id
            )
        )
        is None
    )
    # Resuming no longer silently removes accounts that had a failure.
    assert (
        await db_session.scalar(
            select(InstagramLoopAccount).where(
                InstagramLoopAccount.loop_id == loop.id,
                InstagramLoopAccount.account_id == account.id,
            )
        )
        is not None
    )


@pytest.mark.anyio
async def test_marking_account_error_detaches_it_and_discards_pending_loop_jobs(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "failed_loop_account")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Detach failed account",
        interval_min_minutes=10,
        interval_max_minutes=20,
        post_type="images",
        repeat_media=True,
        status="active",
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    failed_job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=account.id,
        scheduled_for=now,
        status="failed",
        attempts=1,
        last_error="Instagram rejected the publication.",
    )
    pending_job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=account.id,
        scheduled_for=now + timedelta(minutes=10),
        status="queued",
    )
    db_session.add_all([failed_job, pending_job])
    await db_session.flush()
    db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
    await db_session.commit()

    await _mark_account_as_error(db_session, account)
    await db_session.commit()

    association = await db_session.scalar(
        select(InstagramLoopAccount).where(
            InstagramLoopAccount.loop_id == loop.id,
            InstagramLoopAccount.account_id == account.id,
        )
    )
    assert association is None
    assert await db_session.get(InstagramPublicationJob, pending_job.id) is None
    assert await db_session.get(InstagramPublicationJob, failed_job.id) is not None


@pytest.mark.anyio
async def test_rate_limit_failure_keeps_account_in_loop_and_preserves_other_jobs(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    failed_account = _active_account(workspace.id, "isolated_failure")
    next_account = _active_account(workspace.id, "next_account")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Isolated publication failures",
        interval_min_minutes=10,
        interval_max_minutes=20,
        post_type="images",
        repeat_media=True,
        status="active",
    )
    db_session.add_all([failed_account, next_account, loop])
    await db_session.flush()
    failed_job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=failed_account.id,
        scheduled_for=datetime.now(timezone.utc),
        status="publishing",
        attempts=1,
    )
    next_job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=next_account.id,
        scheduled_for=datetime.now(timezone.utc) + timedelta(seconds=1),
        status="queued",
    )
    db_session.add_all([failed_job, next_job])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=loop.id, account_id=failed_account.id),
            InstagramLoopAccount(loop_id=loop.id, account_id=next_account.id),
        ]
    )
    await db_session.commit()

    await _record_publication_failure(
        db_session,
        failed_job.id,
        failed_account.id,
        InstagramPublishingError(
            "Instagram rejected media (HTTP 429, code 4). Rate limit reached."
        ),
    )

    await db_session.refresh(failed_account)
    assert failed_account.status == "connected"
    assert await db_session.get(InstagramPublicationJob, failed_job.id) is not None
    assert await db_session.get(InstagramPublicationJob, next_job.id) is not None
    await db_session.refresh(next_job)
    assert next_job.status == "queued"
    assert await db_session.get(
        InstagramLoopAccount, (loop.id, failed_account.id)
    ) is not None
    assert await db_session.get(
        InstagramLoopAccount, (loop.id, next_account.id)
    ) is not None
    diagnostic = await db_session.scalar(
        select(DiagnosticsEvent).where(
            DiagnosticsEvent.message.contains(str(failed_job.id))
        )
    )
    assert diagnostic is not None
    assert diagnostic.source == "server"


@pytest.mark.anyio
async def test_identity_rejection_marks_account_as_error_and_removes_from_loop(
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "token_rejected")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Token rejection",
        interval_min_minutes=10,
        interval_max_minutes=20,
        post_type="reels",
        repeat_media=True,
        status="active",
    )
    db_session.add_all([account, loop])
    await db_session.flush()
    job = InstagramPublicationJob(
        workspace_id=workspace.id,
        loop_id=loop.id,
        account_id=account.id,
        scheduled_for=datetime.now(timezone.utc),
        status="publishing",
        attempts=1,
    )
    db_session.add_all(
        [job, InstagramLoopAccount(loop_id=loop.id, account_id=account.id)]
    )
    await db_session.commit()

    await _record_publication_failure(
        db_session,
        job.id,
        account.id,
        InstagramPublishingError(
            "Instagram rejected account identity verification (HTTP 400, code 100). "
            "Unsupported request - method type: get"
        ),
    )

    await db_session.refresh(account)
    assert account.status == "error"
    assert await db_session.get(InstagramLoopAccount, (loop.id, account.id)) is None




@pytest.mark.anyio
async def test_ambiguous_403_keeps_account_connected_when_token_still_works(
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.workers import loop_scheduler

    async def token_ok(_account):
        return "valid"

    monkeypatch.setattr(loop_scheduler, "verify_account_token", token_ok)
    _user, workspace = owner
    account = _active_account(workspace.id, "still_publishing")
    db_session.add(account)
    await db_session.commit()

    await _update_account_health_after_failure(
        db_session,
        account.id,
        InstagramPublishingError(
            "Instagram rejected media publication (HTTP 403). "
            "Application does not have permission to perform this action",
            status_code=403,
        ),
    )
    await db_session.refresh(account)
    assert account.status == "connected"


@pytest.mark.anyio
async def test_owner_edit_saves_settings_and_captions_even_if_an_account_errored_meanwhile(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    healthy = _active_account(workspace.id, "edit_healthy")
    flaky = _active_account(workspace.id, "edit_flaky")
    video = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/edit/1.mp4",
        filename="1.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
        caption="old caption",
    )
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Editable loop",
        interval_min_minutes=50,
        interval_max_minutes=60,
        daily_limit_per_account=100,
        post_type="reels",
        repeat_media=True,
        status="paused",
    )
    db_session.add_all([healthy, flaky, video, loop])
    await db_session.flush()
    db_session.add_all(
        [
            InstagramLoopAccount(loop_id=loop.id, account_id=healthy.id),
            InstagramLoopAccount(loop_id=loop.id, account_id=flaky.id),
            InstagramLoopMedia(loop_id=loop.id, media_id=video.id),
        ]
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    # The form was opened with both accounts; one errors before the owner saves.
    flaky.status = "error"
    await db_session.commit()

    response = await client.put(
        f"/api/loops/{loop.id}",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Editable loop",
            "interval_min_minutes": 10,
            "interval_max_minutes": 15,
            "daily_limit_per_account": 30,
            "post_type": "reels",
            "account_ids": [str(healthy.id), str(flaky.id)],
            "media_ids": [str(video.id)],
            "media_captions": {str(video.id): "  new caption  "},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["interval_min_minutes"], body["interval_max_minutes"]) == (10, 15)
    assert body["daily_limit_per_account"] == 30
    await db_session.refresh(video)
    assert video.caption == "new caption"
    # The errored account stays in the loop and comes back once reconnected.
    members = set(
        (
            await db_session.scalars(
                select(InstagramLoopAccount.account_id).where(InstagramLoopAccount.loop_id == loop.id)
            )
        ).all()
    )
    assert members == {healthy.id, flaky.id}

    # A form that never showed the errored account does not remove it either.
    response = await client.put(
        f"/api/loops/{loop.id}",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Editable loop",
            "interval_min_minutes": 10,
            "interval_max_minutes": 15,
            "daily_limit_per_account": 30,
            "post_type": "reels",
            "account_ids": [str(healthy.id)],
            "media_ids": [str(video.id)],
            "media_captions": {str(video.id): ""},
        },
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(video)
    assert video.caption is None


@pytest.mark.anyio
async def test_loop_edit_still_refuses_accounts_of_another_workspace(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "own_account")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Guarded loop",
        interval_min_minutes=10,
        interval_max_minutes=20,
        daily_limit_per_account=10,
        post_type="reels",
        repeat_media=True,
        status="paused",
    )
    db_session.add_all([account, loop])
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.put(
        f"/api/loops/{loop.id}",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Guarded loop",
            "interval_min_minutes": 10,
            "interval_max_minutes": 20,
            "post_type": "reels",
            "account_ids": [str(account.id), str(uuid.uuid4())],
        },
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_changing_the_interval_reschedules_every_account_right_away(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    from app.models import InstagramLoopAccountState

    _user, workspace = owner
    now = datetime.now(timezone.utc)
    accounts = [_active_account(workspace.id, f"resched_{index}") for index in range(3)]
    video = InstagramMedia(
        workspace_id=workspace.id,
        storage_path=f"{workspace.id}/resched/1.mp4",
        filename="1.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
    )
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name="Interval loop",
        interval_min_minutes=50,
        interval_max_minutes=60,
        daily_limit_per_account=100,
        post_type="reels",
        repeat_media=True,
        status="paused",
    )
    db_session.add_all([*accounts, video, loop])
    await db_session.flush()
    db_session.add(InstagramLoopMedia(loop_id=loop.id, media_id=video.id))
    published = now - timedelta(minutes=10)
    for account in accounts:
        db_session.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
        db_session.add(
            InstagramLoopAccountState(
                loop_id=loop.id,
                account_id=account.id,
                next_position=0,
                cycles_completed=0,
                last_published_at=published,
                next_run_at=published + timedelta(minutes=55),
            )
        )
    # One account already hit today's limit: it keeps waiting for midnight.
    blocked = accounts[2]
    await db_session.commit()
    state = await db_session.get(InstagramLoopAccountState, (loop.id, blocked.id))
    state.blocked_reason = "daily_limit"
    midnight = now + timedelta(hours=5)
    state.next_run_at = midnight
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.put(
        f"/api/loops/{loop.id}",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Interval loop",
            "interval_min_minutes": 20,
            "interval_max_minutes": 25,
            "daily_limit_per_account": 100,
            "post_type": "reels",
            "account_ids": [str(account.id) for account in accounts],
        },
    )

    assert response.status_code == 200, response.text
    loop_id, ids = loop.id, [account.id for account in accounts]
    db_session.expire_all()
    for account_id in ids[:2]:
        state = await db_session.get(InstagramLoopAccountState, (loop_id, account_id))
        wait = state.next_run_at.replace(tzinfo=timezone.utc) - published
        assert timedelta(minutes=20) <= wait <= timedelta(minutes=25)
    state = await db_session.get(InstagramLoopAccountState, (loop_id, ids[2]))
    assert abs(state.next_run_at.replace(tzinfo=timezone.utc) - midnight) < timedelta(seconds=1)


@pytest.mark.anyio
async def test_loop_saves_one_caption_and_reels_covers_used_on_publish(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    from app.workers.loop_scheduler import _post_caption_and_cover

    _user, workspace = owner
    account = _active_account(workspace.id, "cover_account")

    def _file(name: str, kind: str, **extra) -> InstagramMedia:
        return InstagramMedia(
            workspace_id=workspace.id,
            storage_path=f"{workspace.id}/cover/{name}",
            filename=name,
            mime_type="video/mp4" if kind == "video" else "image/jpeg",
            media_type=kind,
            size_bytes=100,
            **extra,
        )

    first = _file("1.mp4", "video", caption="own caption")
    second = _file("2.mp4", "video")
    shared_cover = _file("all.jpg", "image", is_cover=True)
    own_cover = _file("own.jpg", "image", is_cover=True)
    db_session.add_all([account, first, second, shared_cover, own_cover])
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    base = {
        "name": "Reels com capa",
        "interval_min_minutes": 20,
        "interval_max_minutes": 40,
        "post_type": "reels",
        "account_ids": [str(account.id)],
        "media_ids": [str(first.id), str(second.id)],
    }

    # A cover image cannot be put in the playlist as a post.
    response = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={**base, "media_ids": [str(first.id), str(shared_cover.id)]},
    )
    assert response.status_code == 422, response.text

    response = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={
            **base,
            "caption_mode": "all",
            "caption": "  Legenda de todos  ",
            "cover_mode": "all",
            "cover_media_id": str(shared_cover.id),
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["caption_mode"], body["caption"]) == ("all", "Legenda de todos")
    assert (body["cover_mode"], body["cover_media_id"]) == ("all", str(shared_cover.id))
    loop = await db_session.get(InstagramLoop, uuid.UUID(body["id"]))
    await db_session.refresh(loop)
    for video in (first, second):
        caption, cover = await _post_caption_and_cover(db_session, loop, video)
        assert caption == "Legenda de todos"
        assert cover is not None and cover.id == shared_cover.id

    # One cover per video: the second has none and Instagram picks a frame.
    response = await client.put(
        f"/api/loops/{loop.id}",
        headers={"X-CSRF-Token": token},
        json={
            **base,
            "caption_mode": "per_media",
            "cover_mode": "per_media",
            "media_covers": {str(first.id): str(own_cover.id)},
        },
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(loop)
    await db_session.refresh(first)
    assert first.cover_media_id == own_cover.id
    caption, cover = await _post_caption_and_cover(db_session, loop, first)
    assert caption is None and cover is not None and cover.id == own_cover.id
    caption, cover = await _post_caption_and_cover(db_session, loop, second)
    assert caption is None and cover is None

    # "Uma capa para todos" needs the image.
    response = await client.put(
        f"/api/loops/{loop.id}",
        headers={"X-CSRF-Token": token},
        json={**base, "cover_mode": "all"},
    )
    assert response.status_code == 422
