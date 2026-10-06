import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.crypto import decrypt_value, encrypt_value
from app.core.database import get_session_factory
from app.instagram.oauth import (
    InstagramOAuthError,
    instagram_api_error_detail,
    refresh_instagram_long_lived_token,
)
from app.instagram.publishing import InstagramPublishingError, publish_media
from app.instagram.storage import SupabaseStorage, SupabaseStorageError
from app.models import (
    InstagramAccount,
    InstagramLoopAccount,
    InstagramMedia,
    InstagramPublicationJob,
)
from app.loops.scheduler import enqueue_due_loop_publications

logger = logging.getLogger(__name__)
STALE_PUBLICATION_AFTER = timedelta(minutes=45)
TOKEN_REFRESH_WINDOW = timedelta(days=10)
TOKEN_REFRESH_RETRY_INTERVAL = timedelta(hours=12)
CONSECUTIVE_PUBLICATION_FAILURE_LIMIT = 5


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _remove_failed_loop_account(db, job: InstagramPublicationJob) -> None:
    await db.execute(
        delete(InstagramLoopAccount).where(
            InstagramLoopAccount.loop_id == job.loop_id,
            InstagramLoopAccount.account_id == job.account_id,
        )
    )
    await db.execute(
        delete(InstagramPublicationJob).where(
            InstagramPublicationJob.loop_id == job.loop_id,
            InstagramPublicationJob.account_id == job.account_id,
            InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
        )
    )


def _is_account_connection_failure(error: Exception) -> bool:
    if isinstance(error, InstagramPublishingError):
        if error.status_code in {401, 403} or error.meta_error_code in {102, 190}:
            return True
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in {401, 403}:
            return True
        try:
            payload = error.response.json()
        except ValueError:
            payload = None
        meta_error = payload.get("error") if isinstance(payload, dict) else None
        code = meta_error.get("code") if isinstance(meta_error, dict) else None
        message = meta_error.get("message") if isinstance(meta_error, dict) else None
        if code in {102, 190}:
            return True
        if isinstance(message, str):
            error = RuntimeError(message)
    message = str(error).casefold()
    return any(
        marker in message
        for marker in (
            "checkpoint challenge",
            "account suspended",
            "account disabled",
            "account has been disabled",
            "access token has expired",
            "invalid oauth access token",
            "token has been invalidated",
            "permission to perform this action",
        )
    )


async def _mark_expired_accounts(now: datetime) -> int:
    async with get_session_factory()() as db:
        expired_accounts = (
            await db.scalars(
                select(InstagramAccount).where(
                    InstagramAccount.status == "connected",
                    (
                        (InstagramAccount.encrypted_access_token.is_(None))
                        | (InstagramAccount.token_expires_at <= now)
                    ),
                )
            )
        ).all()
        for account in expired_accounts:
            await _mark_account_as_error(db, account)
        if expired_accounts:
            await db.commit()
        return len(expired_accounts)


async def _mark_account_as_error(
    db,
    account: InstagramAccount,
    reason: str = "A autorização do Instagram expirou ou deixou de ser válida.",
) -> None:
    account.status = "error"
    account.status_reason = reason[:500]
    await db.execute(
        delete(InstagramLoopAccount).where(
            InstagramLoopAccount.account_id == account.id
        )
    )
    await db.execute(
        delete(InstagramPublicationJob)
        .where(
            InstagramPublicationJob.account_id == account.id,
            InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
        )
    )


async def _update_account_health_after_failure(
    db,
    account_id,
    error: Exception,
) -> None:
    account = await db.get(InstagramAccount, account_id)
    if account is None or account.status != "connected":
        return
    if _is_account_connection_failure(error):
        reason = (
            instagram_api_error_detail(error)
            if isinstance(error, httpx.HTTPStatusError)
            else str(error)
        )
        await _mark_account_as_error(
            db,
            account,
            reason or "A autorização do Instagram foi recusada.",
        )
        await db.commit()
        return

    recent_jobs = (
        await db.scalars(
            select(InstagramPublicationJob.status)
            .where(
                InstagramPublicationJob.account_id == account_id,
                InstagramPublicationJob.attempts > 0,
                InstagramPublicationJob.status.in_(("published", "failed")),
            )
            .order_by(
                InstagramPublicationJob.updated_at.desc(),
                InstagramPublicationJob.id.desc(),
            )
            .limit(CONSECUTIVE_PUBLICATION_FAILURE_LIMIT + 1)
        )
    ).all()
    if (
        len(recent_jobs) > CONSECUTIVE_PUBLICATION_FAILURE_LIMIT
        and all(job_status == "failed" for job_status in recent_jobs)
    ):
        await _mark_account_as_error(
            db,
            account,
            "A conta foi marcada com erro após falhas consecutivas de publicação.",
        )
        await db.commit()


def _safe_publication_error(error: Exception) -> str:
    if isinstance(error, (InstagramPublishingError, SupabaseStorageError)):
        return str(error)[:500]
    if isinstance(error, httpx.HTTPError):
        return "A network error interrupted the publication; check the Instagram account before retrying."
    return "An unexpected error interrupted the publication. Check the worker logs."


async def _record_publication_failure(
    db,
    job_id,
    account_id,
    error: Exception,
) -> None:
    job = await db.scalar(
        select(InstagramPublicationJob).where(
            InstagramPublicationJob.id == job_id,
            InstagramPublicationJob.status == "publishing",
        )
    )
    account = await db.get(InstagramAccount, account_id)
    if job is None:
        logger.warning(
            "Publication job %s was no longer active after account %s failed.",
            job_id,
            account_id,
        )
        return

    error_detail = _safe_publication_error(error)
    job.status = "failed"
    job.last_error = error_detail
    await _remove_failed_loop_account(db, job)
    if account is not None and account.status == "connected":
        await _mark_account_as_error(
            db,
            account,
            f"Falha na publicação: {error_detail}"[:500],
        )
    await db.commit()
    logger.error(
        "Publication job %s failed for account %s (%s): %s",
        job_id,
        account_id,
        type(error).__name__,
        error_detail,
    )


async def refresh_due_instagram_tokens(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    refreshed_count = 0
    async with get_session_factory()() as db:
        account_ids = (
            await db.scalars(
                select(InstagramAccount.id)
                .where(
                    InstagramAccount.status == "connected",
                    InstagramAccount.encrypted_access_token.is_not(None),
                    InstagramAccount.token_expires_at > current,
                    InstagramAccount.token_expires_at <= current + TOKEN_REFRESH_WINDOW,
                    (
                        InstagramAccount.token_refresh_checked_at.is_(None)
                        | (
                            InstagramAccount.token_refresh_checked_at
                            <= current - TOKEN_REFRESH_RETRY_INTERVAL
                        )
                    ),
                )
                .order_by(InstagramAccount.token_expires_at, InstagramAccount.id)
            )
        ).all()

    for account_id in account_ids:
        async with get_session_factory()() as db:
            account = await db.scalar(
                select(InstagramAccount)
                .where(
                    InstagramAccount.id == account_id,
                    InstagramAccount.status == "connected",
                    InstagramAccount.encrypted_access_token.is_not(None),
                    InstagramAccount.token_expires_at > current,
                    InstagramAccount.token_expires_at <= current + TOKEN_REFRESH_WINDOW,
                    (
                        InstagramAccount.token_refresh_checked_at.is_(None)
                        | (
                            InstagramAccount.token_refresh_checked_at
                            <= current - TOKEN_REFRESH_RETRY_INTERVAL
                        )
                    ),
                )
                .with_for_update(skip_locked=True)
            )
            if account is None:
                continue
            account.token_refresh_checked_at = current
            try:
                access_token = decrypt_value(account.encrypted_access_token)
            except (RuntimeError, ValueError) as exc:
                await db.commit()
                logger.error(
                    "Instagram token refresh could not decrypt account %s (%s).",
                    account.id,
                    type(exc).__name__,
                )
                continue

            original_encrypted_token = account.encrypted_access_token
            await db.commit()
            try:
                refreshed_token, expires_at = await refresh_instagram_long_lived_token(
                    access_token
                )
                encrypted_token = encrypt_value(refreshed_token)
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Instagram token refresh was rejected for account %s (HTTP %s).",
                    account_id,
                    exc.response.status_code,
                )
                if _is_account_connection_failure(exc):
                    await _mark_account_as_error(
                        db,
                        account,
                        instagram_api_error_detail(exc),
                    )
                    await db.commit()
                continue
            except (httpx.HTTPError, InstagramOAuthError, RuntimeError) as exc:
                logger.warning(
                    "Instagram token refresh failed for account %s (%s).",
                    account_id,
                    type(exc).__name__,
                )
                continue

            account = await db.scalar(
                select(InstagramAccount)
                .where(
                    InstagramAccount.id == account_id,
                    InstagramAccount.status == "connected",
                    InstagramAccount.encrypted_access_token == original_encrypted_token,
                )
                .with_for_update(skip_locked=True)
            )
            if account is None or account.encrypted_access_token is None:
                continue
            account.encrypted_access_token = encrypted_token
            account.token_expires_at = expires_at
            account.token_refresh_checked_at = current
            await db.commit()
            refreshed_count += 1
            logger.info("Instagram access token refreshed for account %s.", account_id)
    return refreshed_count


async def process_one_queued_publication() -> bool:
    async with get_session_factory()() as db:
        job = await db.scalar(
            select(InstagramPublicationJob)
            .where(InstagramPublicationJob.status == "queued")
            .order_by(InstagramPublicationJob.scheduled_for, InstagramPublicationJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return False
        account = await db.scalar(
            select(InstagramAccount).where(
                InstagramAccount.id == job.account_id,
                InstagramAccount.workspace_id == job.workspace_id,
            )
        )
        media = await db.scalar(
            select(InstagramMedia).where(
                InstagramMedia.id == job.media_id,
                InstagramMedia.workspace_id == job.workspace_id,
            )
        )
        if (
            account is None
            or media is None
        ):
            job.status = "failed"
            job.last_error = "The connected account or selected media is no longer available."
            await _remove_failed_loop_account(db, job)
            await db.commit()
            logger.error(
                "Publication job %s could not start: account_exists=%s media_exists=%s.",
                job.id,
                account is not None,
                media is not None,
            )
            return True
        if (
            account.status != "connected"
            or account.encrypted_access_token is None
            or _utc_datetime(account.token_expires_at) <= datetime.now(timezone.utc)
        ):
            if account.status == "connected":
                await _mark_account_as_error(db, account)
            job.status = "failed"
            job.last_error = "The connected account or selected media is no longer available."
            await _remove_failed_loop_account(db, job)
            await db.commit()
            logger.error(
                "Publication job %s skipped because account %s is not connected with a valid token.",
                job.id,
                account.username,
            )
            return True

        try:
            access_token = decrypt_value(account.encrypted_access_token)
        except (RuntimeError, ValueError) as exc:
            job.status = "failed"
            job.last_error = "The Instagram access token could not be read securely."
            await _remove_failed_loop_account(db, job)
            await _mark_account_as_error(
                db,
                account,
                "O token desta conta não pôde ser lido com segurança.",
            )
            await db.commit()
            logger.error(
                "Publication job %s could not decrypt the account token (%s).",
                job.id,
                type(exc).__name__,
            )
            return True
        try:
            storage = SupabaseStorage.from_settings()
        except (RuntimeError, ValueError) as exc:
            job.status = "failed"
            job.last_error = "Server-side media storage credentials are unavailable."
            await db.commit()
            logger.error(
                "Publication job %s for account %s could not initialize media storage (%s).",
                job.id,
                account.username,
                type(exc).__name__,
            )
            return True

        job.status = "publishing"
        job.attempts += 1
        job.last_error = None
        await db.commit()
        job_id = job.id
        account_id = account.id
        media_id = media.id
        logger.info(
            "Starting queued publication job %s for account %s (Instagram user %s, app credential %s), media %s.",
            job_id,
            account.username,
            account.instagram_user_id,
            account.app_credential_id or "legacy/unlinked",
            media_id,
        )

    try:
        published_media_id = await publish_media(account, media, access_token, storage)
    except Exception as exc:
        async with get_session_factory()() as db:
            await _record_publication_failure(db, job_id, account_id, exc)
        return True

    async with get_session_factory()() as db:
        job = await db.scalar(
            select(InstagramPublicationJob).where(
                InstagramPublicationJob.id == job_id,
                InstagramPublicationJob.status == "publishing",
            )
        )
        if job is not None:
            job.status = "published"
            job.published_media_id = published_media_id
            job.last_error = None
            await db.commit()
    logger.info(
        "Publication job %s published media %s to account %s (source media %s).",
        job_id,
        published_media_id,
        account_id,
        media_id,
    )
    return True


async def fail_stale_publication_jobs(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    cutoff = current - STALE_PUBLICATION_AFTER
    async with get_session_factory()() as db:
        stale_jobs = (
            await db.scalars(
                select(InstagramPublicationJob).where(
                    InstagramPublicationJob.status == "publishing",
                    InstagramPublicationJob.updated_at < cutoff,
                )
            )
        ).all()
        for job in stale_jobs:
            job.status = "failed"
            job.last_error = (
                "The worker stopped during publication; verify Instagram before retrying."
            )
            await _remove_failed_loop_account(db, job)
        await db.commit()
    if stale_jobs:
        logger.error("Marked %s stale publication jobs for manual review.", len(stale_jobs))
    return len(stale_jobs)


async def run_loop_scheduler_tick() -> int:
    logger.info("Starting Loop publication scheduler tick.")
    await _mark_expired_accounts(datetime.now(timezone.utc))
    await fail_stale_publication_jobs()
    refreshed_tokens = await refresh_due_instagram_tokens()
    async with get_session_factory()() as db:
        created_jobs = await enqueue_due_loop_publications(db)
    published_jobs = 0
    if get_settings().instagram_publishing_enabled:
        while True:
            try:
                processed = await process_one_queued_publication()
            except Exception as exc:
                logger.error(
                    "Loop publication worker could not process the next queued job (%s); "
                    "remaining jobs will be retried on the next scheduler tick.",
                    type(exc).__name__,
                )
                break
            if not processed:
                break
            published_jobs += 1
    else:
        logger.warning(
            "Instagram publishing is disabled by INSTAGRAM_PUBLISHING_ENABLED=false; "
            "queued publications are not being sent."
        )
    logger.info(
        "Loop scheduler prepared %s jobs, refreshed %s tokens, and processed %s publications.",
        created_jobs,
        refreshed_tokens,
        published_jobs,
    )
    return created_jobs


if __name__ == "__main__":
    asyncio.run(run_loop_scheduler_tick())
