from datetime import datetime, timedelta, timezone
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    InstagramMedia,
    InstagramProfileFolder,
    InstagramScheduledPost,
    InstagramScheduledPostTarget,
)
from app.publications import scheduler as pub_scheduler
from tests.test_loops import _active_account, _csrf, _login


def _media(workspace_id: uuid.UUID, name: str, media_type: str = "image") -> InstagramMedia:
    ext = "jpg" if media_type == "image" else "mp4"
    return InstagramMedia(
        workspace_id=workspace_id,
        storage_path=f"{workspace_id}/pub/{name}.{ext}",
        filename=f"{name}.{ext}",
        mime_type="image/jpeg" if media_type == "image" else "video/mp4",
        media_type=media_type,
        size_bytes=100,
    )


@pytest.mark.anyio
async def test_create_targets_union_of_accounts_and_folder(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    folder = InstagramProfileFolder(workspace_id=workspace.id, name="Promo")
    db_session.add(folder)
    await db_session.flush()
    a1 = _active_account(workspace.id, "acc_one")
    a2 = _active_account(workspace.id, "acc_two")
    a2.profile_folder_id = folder.id  # reached via the folder
    media = _media(workspace.id, "foto")
    db_session.add_all([a1, a2, media])
    await db_session.commit()

    await _login(client, "owner@example.com", "correct horse battery staple")
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    resp = await client.post(
        "/api/publications",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={
            "media_id": str(media.id), "kind": "post", "caption": "Olá!",
            "scheduled_for": when, "account_ids": [str(a1.id)], "folder_ids": [str(folder.id)],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["targets"]["total"] == 2  # a1 directly + a2 via folder (deduped)
    assert body["kind"] == "post"

    listed = await client.get("/api/publications")
    assert listed.status_code == 200
    assert len(listed.json()["publications"]) == 1


@pytest.mark.anyio
async def test_past_date_and_empty_target_rejected(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    media = _media(workspace.id, "foto2")
    account = _active_account(workspace.id, "acc_solo")
    db_session.add_all([media, account])
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r1 = await client.post("/api/publications", headers={"X-CSRF-Token": token}, json={
        "media_id": str(media.id), "scheduled_for": past, "account_ids": [str(account.id)]})
    assert r1.status_code == 422

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r2 = await client.post("/api/publications", headers={"X-CSRF-Token": token}, json={
        "media_id": str(media.id), "scheduled_for": future, "account_ids": []})
    assert r2.status_code == 422


@pytest.mark.anyio
async def test_worker_publishes_due_targets_including_story(
    client: AsyncClient, db_session: AsyncSession, owner, monkeypatch
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "acc_pub")
    media = _media(workspace.id, "video1", media_type="video")
    db_session.add_all([account, media])
    await db_session.flush()
    post = InstagramScheduledPost(
        workspace_id=workspace.id, media_id=media.id, kind="story",
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1), status="scheduled",
    )
    db_session.add(post)
    await db_session.flush()
    db_session.add(InstagramScheduledPostTarget(
        post_id=post.id, workspace_id=workspace.id, account_id=account.id, status="queued"))
    await db_session.commit()
    post_id = post.id

    calls: list[dict] = []

    async def fake_publish(acc, med, token, storage, *, caption=None, story=False, **_kw):
        calls.append({"username": acc.username, "story": story, "caption": caption})
        return "ig_published_1"

    class FakeStorage:
        pass

    monkeypatch.setattr(pub_scheduler, "publish_media", fake_publish)
    monkeypatch.setattr(pub_scheduler.SupabaseStorage, "from_settings", classmethod(lambda _c: FakeStorage()))

    handled = await pub_scheduler.run_due_scheduled_posts()
    assert handled == 1
    assert calls == [{"username": "acc_pub", "story": True, "caption": None}]  # story, no caption

    target = await db_session.scalar(
        select(InstagramScheduledPostTarget).where(InstagramScheduledPostTarget.post_id == post_id)
    )
    await db_session.refresh(target)
    assert target.status == "published"
    assert target.published_media_id == "ig_published_1"
    refreshed_post = await db_session.get(InstagramScheduledPost, post_id)
    await db_session.refresh(refreshed_post)
    assert refreshed_post.status == "done"
