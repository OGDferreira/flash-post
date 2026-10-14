from datetime import datetime, timedelta, timezone

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.instagram.publishing import InstagramPublishingError
from app.instagram.storage import SupabaseStorageError
from app.models import (
    DiagnosticsEvent,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramPublicationJob,
)
from app.workers.loop_scheduler import _classify_failure, _record_publication_failure
from tests.test_loops import _active_account, _csrf, _login


def test_failures_are_classified_by_meta_code_before_text() -> None:
    assert _classify_failure(InstagramPublishingError("x", status_code=400, meta_error_code=4)) == "rate_limit"
    assert _classify_failure(InstagramPublishingError("x", status_code=401, meta_error_code=190)) == "token"
    assert _classify_failure(SupabaseStorageError("could not sign (HTTP 502)")) == "storage"
    assert _classify_failure(httpx.ConnectError("boom")) == "network"
    assert (
        _classify_failure(RuntimeError("Instagram could not process the video container"))
        == "video_format"
    )


async def _job(db_session: AsyncSession, workspace, attempts: int):
    account = _active_account(workspace.id, f"retry_{attempts}")
    loop = InstagramLoop(
        workspace_id=workspace.id,
        name=f"Retry {attempts}",
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
        attempts=attempts,
    )
    db_session.add_all([job, InstagramLoopAccount(loop_id=loop.id, account_id=account.id)])
    await db_session.commit()
    return job, account


@pytest.mark.anyio
async def test_soft_failure_is_requeued_with_backoff_then_fails(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    job, account = await _job(db_session, workspace, 1)
    await _record_publication_failure(
        db_session, job.id, account.id, httpx.ConnectError("network down")
    )
    await db_session.refresh(job)
    assert job.status == "queued"
    assert job.next_retry_at is not None
    assert job.error_category == "network"

    job.status = "publishing"
    job.attempts = 3
    await db_session.commit()
    await _record_publication_failure(
        db_session, job.id, account.id, httpx.ConnectError("network down")
    )
    await db_session.refresh(job)
    assert job.status == "failed"
    event = await db_session.scalar(
        select(DiagnosticsEvent).where(DiagnosticsEvent.job_id == job.id).order_by(
            DiagnosticsEvent.created_at.desc()
        )
    )
    assert event is not None and event.category == "network"
    assert event.account_id == account.id


@pytest.mark.anyio
async def test_failed_jobs_can_be_retried_and_alerts_and_health_work(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    job, account = await _job(db_session, workspace, 3)
    job.status = "failed"
    job.last_error = "boom"
    job.media_id = None
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    alerts = await client.get("/api/loops/alerts")
    assert alerts.status_code == 200
    assert alerts.json()["failed_today"] == 1
    assert alerts.json()["expiring_accounts"] == []

    health = await client.get(f"/api/loops/{job.loop_id}/health")
    assert health.status_code == 200
    loop = await db_session.get(InstagramLoop, job.loop_id)
    assert health.json()["target_per_account"] == loop.daily_limit_per_account
    assert health.json()["accounts"][0]["state"] in {"failing", "due", "scheduled"}
    assert health.json()["accounts"][0]["failed_today"] == 1

    # Jobs without media cannot be requeued.
    retry = await client.post(
        "/api/loops/failures/retry",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"job_ids": [str(job.id)]},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json() == {"requeued": 0}
