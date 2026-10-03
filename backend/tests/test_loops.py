from datetime import datetime, timedelta, timezone
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.loops.scheduler import enqueue_due_loop_publications
from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
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
            "daily_limit_per_account": 6,
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
async def test_collaborator_cannot_manage_loops(
    client: AsyncClient,
    collaborator,
) -> None:
    await _login(client, "collaborator@example.com", "collaborator password")
    token = await _csrf(client)

    response = await client.post(
        "/api/loops",
        headers={"X-CSRF-Token": token},
        json={
            "name": "Forbidden loop",
            "interval_min_minutes": 5,
            "interval_max_minutes": 10,
            "daily_limit_per_account": 2,
            "account_ids": [str(uuid.uuid4())],
        },
    )

    assert response.status_code == 403


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
