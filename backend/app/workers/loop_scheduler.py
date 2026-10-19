import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.crypto import decrypt_value, encrypt_value
from app.core.database import get_session_factory
from app.instagram.oauth import (
    InstagramOAuthError,
    instagram_api_error_detail,
    refresh_instagram_long_lived_token,
)
from app.instagram.account_state import isolate_inactive_account
from app.instagram.publishing import (
    GRAPH_ENDPOINT,
    InstagramPublishingError,
    fetch_container_status,
    is_definitive_publish_rejection,
    publish_existing_container,
    publish_media,
)
from app.instagram.storage import SupabaseStorage, SupabaseStorageError
from app.models import (
    DiagnosticsEvent,
    InstagramAccount,
    InstagramLoop,
    InstagramMedia,
    InstagramPublicationJob,
)
from app.loops.scheduler import (
    enqueue_due_loop_publications,
    record_publication_confirmed,
    record_publication_given_up,
    workspaces_allowed_to_post,
)
from app.core.redaction import redact_secrets

logger = logging.getLogger(__name__)
STALE_PUBLICATION_AFTER = timedelta(minutes=45)
RECONCILE_RETRY_DELAY = timedelta(minutes=2)
RECONCILE_GIVE_UP_AFTER = timedelta(hours=24)
MAX_AUTO_ATTEMPTS = 3
AUTO_RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5))
FAILURE_RETENTION = timedelta(days=30)
DIAGNOSTICS_RETENTION = timedelta(days=14)
TOKEN_REFRESH_WINDOW = timedelta(days=10)
TOKEN_REFRESH_RETRY_INTERVAL = timedelta(hours=12)


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _meta_code_of(error: Exception) -> int | None:
    if isinstance(error, InstagramPublishingError):
        return error.meta_error_code
    if isinstance(error, httpx.HTTPStatusError):
        try:
            payload = error.response.json()
        except ValueError:
            return None
        meta_error = payload.get("error") if isinstance(payload, dict) else None
        code = meta_error.get("code") if isinstance(meta_error, dict) else None
        return code if isinstance(code, int) else None
    return None


def _classify_failure(error: Exception) -> str:
    """Categorise by Meta error code first and message text only as fallback."""
    if _connection_failure_kind(error) == "definitive":
        return "token"
    code = _meta_code_of(error)
    if code in {4, 17, 32, 613}:
        return "rate_limit"
    if isinstance(error, SupabaseStorageError):
        return "storage"
    if isinstance(error, httpx.HTTPError):
        return "network"
    message = str(error).casefold()
    if any(
        marker in message
        for marker in ("video container", "aspect ratio", "duration", "codec", "status error")
    ):
        return "video_format"
    if code is not None:
        return "meta_api"
    return "unknown"


_DEFINITIVE_TOKEN_MARKERS = (
    "access token has expired",
    "invalid oauth access token",
    "token has been invalidated",
    "rejected account identity verification",
    "belongs to a different account",
    "checkpoint challenge",
    "account suspended",
    "account disabled",
    "account has been disabled",
)
_AMBIGUOUS_ACCOUNT_MARKERS = (
    "permission to perform this action",
    "unsupported request",
    "account restricted",
    "has been restricted",
)


def _connection_failure_kind(error: Exception) -> str | None:
    """"definitive" (token/account is unusable), "ambiguous" (needs a token
    check before isolating the account) or None (publication-only failure)."""
    status_code: int | None = None
    code: int | None = None
    message_source: object = error
    if isinstance(error, InstagramPublishingError):
        status_code = error.status_code
        code = error.meta_error_code
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        try:
            payload = error.response.json()
        except ValueError:
            payload = None
        meta_error = payload.get("error") if isinstance(payload, dict) else None
        raw_code = meta_error.get("code") if isinstance(meta_error, dict) else None
        code = raw_code if isinstance(raw_code, int) else None
        message = meta_error.get("message") if isinstance(meta_error, dict) else None
        if isinstance(message, str):
            message_source = message
    if code in {102, 190} or status_code == 401:
        return "definitive"
    message = str(message_source).casefold()
    if any(marker in message for marker in _DEFINITIVE_TOKEN_MARKERS):
        return "definitive"
    if status_code == 403 or any(marker in message for marker in _AMBIGUOUS_ACCOUNT_MARKERS):
        return "ambiguous"
    return None


def _is_account_connection_failure(error: Exception) -> bool:
    return _connection_failure_kind(error) is not None


async def verify_account_token(account: InstagramAccount) -> str:
    """Ask Meta who the saved token belongs to: "valid", "invalid" or "unknown".

    Used before isolating an account on an ambiguous error, so an account that
    can still publish is never shown as disconnected.
    """
    try:
        token = decrypt_value(account.encrypted_access_token or "")
    except (RuntimeError, ValueError):
        return "invalid"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{GRAPH_ENDPOINT}/me",
                params={"fields": "user_id,username", "access_token": token},
            )
    except httpx.HTTPError:
        return "unknown"
    if response.status_code == 401:
        return "invalid"
    if response.is_error:
        try:
            payload = response.json()
        except ValueError:
            return "unknown"
        error = payload.get("error") if isinstance(payload, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        return "invalid" if code in {102, 190} else "unknown"
    try:
        payload = response.json()
    except ValueError:
        return "unknown"
    username = payload.get("username") if isinstance(payload, dict) else None
    if isinstance(username, str) and username.casefold() != str(account.username).casefold():
        return "invalid"
    return "valid"


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
    await isolate_inactive_account(db, account, "error", reason)


async def _update_account_health_after_failure(
    db,
    account_id,
    error: Exception,
) -> None:
    account = await db.get(InstagramAccount, account_id)
    if account is None or account.status != "connected":
        return
    kind = _connection_failure_kind(error)
    if kind is None:
        return  # Falhas isoladas de publicação não removem a conta do loop.
    if kind == "ambiguous":
        verdict = await verify_account_token(account)
        if verdict != "invalid":
            logger.info(
                "Ambiguous Meta error for account %s, but the token check returned %s; "
                "the account stays connected.",
                account.username,
                verdict,
            )
            return
    reason = (
        instagram_api_error_detail(error)
        if isinstance(error, httpx.HTTPStatusError)
        else redact_secrets(str(error))
    )
    await _mark_account_as_error(
        db,
        account,
        reason or "A autorização do Instagram foi recusada.",
    )
    await db.commit()


def _safe_publication_error(error: Exception) -> str:
    if isinstance(error, (InstagramPublishingError, SupabaseStorageError)):
        return redact_secrets(str(error))[:500]
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
    category = _classify_failure(error)
    now = datetime.now(timezone.utc)
    if (
        category != "token"
        and job.attempts < MAX_AUTO_ATTEMPTS
        and account is not None
        and account.status == "connected"
    ):
        delay = AUTO_RETRY_DELAYS[min(job.attempts - 1, len(AUTO_RETRY_DELAYS) - 1)]
        job.status = "queued"
        job.next_retry_at = now + delay
        # Nothing was published (definitive rejection or failure before
        # media_publish); the retry starts from a fresh container.
        job.container_id = None
        job.publish_requested_at = None
    else:
        job.status = "failed"
        job.next_retry_at = None
        await record_publication_given_up(
            db, job, now, skip_media=category == "video_format"
        )
    job.last_error = error_detail
    job.error_category = category
    db.add(
        DiagnosticsEvent(
            workspace_id=job.workspace_id,
            source="server",
            level="error" if job.status == "failed" else "warning",
            message=(
                f"[{category}] Publicação {job.id} (tentativa {job.attempts}/{MAX_AUTO_ATTEMPTS}"
                f"{', nova tentativa agendada' if job.status == 'queued' else ''}) "
                f"conta {account.username if account else account_id}: "
                f"{type(error).__name__}: {redact_secrets(str(error))[:1500]}"
            ),
            stack=redact_secrets("".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ))[-8000:]
            if error.__traceback__
            else None,
            path="/workers/loop_scheduler",
            account_id=account_id,
            loop_id=job.loop_id,
            job_id=job.id,
            category=category,
            meta_code=_meta_code_of(error),
        )
    )
    if account is not None and account.status == "connected":
        await _update_account_health_after_failure(db, account_id, error)
    try:
        await db.commit()
    except SQLAlchemyError:
        logger.exception(
            "Could not persist publication failure and diagnostics for job %s.",
            job_id,
        )
        raise
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


async def _post_caption_and_cover(
    db, loop: InstagramLoop | None, media: InstagramMedia | None
) -> tuple[str | None, InstagramMedia | None]:
    """The caption (None = the media's own) and Reels cover the loop sets for this post."""
    if loop is None or media is None:
        return None, None
    caption = (loop.caption or "") if loop.caption_mode == "all" else None
    cover_id = None
    if media.media_type == "video":
        if loop.cover_mode == "all":
            cover_id = loop.cover_media_id
        elif loop.cover_mode == "per_media":
            cover_id = media.cover_media_id
    cover = None
    if cover_id is not None:
        cover = await db.scalar(
            select(InstagramMedia).where(
                InstagramMedia.id == cover_id,
                InstagramMedia.workspace_id == media.workspace_id,
                InstagramMedia.media_type == "image",
            )
        )
    return caption, cover


async def process_one_queued_publication() -> bool:
    async with get_session_factory()() as db:
        job = await db.scalar(
            select(InstagramPublicationJob)
            .where(
                InstagramPublicationJob.status == "queued",
                or_(
                    InstagramPublicationJob.next_retry_at.is_(None),
                    InstagramPublicationJob.next_retry_at <= datetime.now(timezone.utc),
                ),
                # A blocked owner's queue waits until the Super Admin unblocks them.
                InstagramPublicationJob.workspace_id.in_(workspaces_allowed_to_post()),
            )
            .order_by(
                InstagramPublicationJob.scheduled_for,
                func.coalesce(InstagramPublicationJob.queue_sequence, -1),
                InstagramPublicationJob.id,
            )
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
        loop = await db.get(InstagramLoop, job.loop_id)
        post_caption, cover = await _post_caption_and_cover(db, loop, media)
        if (
            account is None
            or media is None
        ):
            job.status = "failed"
            job.last_error = "The connected account or selected media is no longer available."
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

    async def before_publish(container_id: str) -> None:
        # Persisted before media_publish: if the answer is lost we reconcile
        # through this container instead of publishing the video again.
        async with get_session_factory()() as marker_db:
            marker = await marker_db.get(InstagramPublicationJob, job_id)
            if marker is not None:
                marker.container_id = container_id[:128]
                marker.publish_requested_at = datetime.now(timezone.utc)
                await marker_db.commit()

    try:
        published_media_id = await publish_media(
            account, media, access_token, storage, before_publish=before_publish,
            caption=post_caption, cover=cover,
        )
    except Exception as exc:
        async with get_session_factory()() as db:
            if not await _hold_for_reconciliation(db, job_id, exc):
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
            job.published_media_id = published_media_id
            await record_publication_confirmed(db, job, datetime.now(timezone.utc))
            await db.commit()
    logger.info(
        "Publication job %s published media %s to account %s (source media %s).",
        job_id,
        published_media_id,
        account_id,
        media_id,
    )
    return True


async def _hold_for_reconciliation(db, job_id, error: Exception) -> bool:
    """Keep the job in "publishing" when media_publish may have succeeded."""
    job = await db.scalar(
        select(InstagramPublicationJob).where(
            InstagramPublicationJob.id == job_id,
            InstagramPublicationJob.status == "publishing",
        )
    )
    if job is None or job.publish_requested_at is None:
        return False
    if is_definitive_publish_rejection(error):
        return False
    now = datetime.now(timezone.utc)
    job.next_retry_at = now + RECONCILE_RETRY_DELAY
    job.error_category = "uncertain"
    job.last_error = (
        "A Meta não confirmou a publicação; o FlashPost vai verificar o container "
        "antes de qualquer nova tentativa."
    )
    db.add(
        DiagnosticsEvent(
            workspace_id=job.workspace_id,
            source="server",
            level="warning",
            message=(
                f"[uncertain] Publicação {job.id}: resposta incerta após media_publish "
                f"({type(error).__name__}: {redact_secrets(str(error))[:300]}). "
                "Reconciliação agendada."
            ),
            path="/workers/loop_scheduler",
            account_id=job.account_id,
            loop_id=job.loop_id,
            job_id=job.id,
            category="uncertain",
        )
    )
    await db.commit()
    logger.warning("Publication job %s has an uncertain outcome; reconciling.", job.id)
    return True


async def reconcile_uncertain_publications(now: datetime | None = None) -> int:
    """Resolve jobs whose media_publish answer was lost, without duplicates.

    Container status decides: PUBLISHED -> confirm; FINISHED -> publish that
    same container (it can only be published once); ERROR/EXPIRED -> nothing
    was published, normal retry rules apply; unknown -> check again later and
    after 24 h block the account for manual review.
    """
    current = now or datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        job_ids = (
            await db.scalars(
                select(InstagramPublicationJob.id).where(
                    InstagramPublicationJob.status == "publishing",
                    InstagramPublicationJob.publish_requested_at.is_not(None),
                    or_(
                        InstagramPublicationJob.next_retry_at <= current,
                        InstagramPublicationJob.updated_at < current - STALE_PUBLICATION_AFTER,
                    ),
                )
            )
        ).all()
    resolved = 0
    for job_id in job_ids:
        async with get_session_factory()() as db:
            job = await db.scalar(
                select(InstagramPublicationJob)
                .where(
                    InstagramPublicationJob.id == job_id,
                    InstagramPublicationJob.status == "publishing",
                )
                .with_for_update(skip_locked=True)
            )
            if job is None or job.container_id is None:
                if job is not None:
                    # Marked but no container saved: media_publish never ran.
                    job.publish_requested_at = None
                    await _record_publication_failure(
                        db, job.id, job.account_id,
                        InstagramPublishingError("Publicação interrompida antes do envio à Meta."),
                    )
                continue
            account = await db.get(InstagramAccount, job.account_id)
            token = None
            if account is not None and account.encrypted_access_token:
                try:
                    token = decrypt_value(account.encrypted_access_token)
                except (RuntimeError, ValueError):
                    token = None
            status_code = (
                await fetch_container_status(account.instagram_user_id, job.container_id, token)
                if token and account is not None
                else None
            )
            requested_at = _utc_datetime(job.publish_requested_at)
            if status_code == "PUBLISHED":
                await record_publication_confirmed(db, job, requested_at)
                await db.commit()
                resolved += 1
                logger.info("Reconciled job %s: container was already published.", job.id)
                continue
            if status_code == "FINISHED" and token and account is not None:
                try:
                    published_id = await publish_existing_container(
                        account.instagram_user_id, job.container_id, token
                    )
                except Exception as exc:
                    if is_definitive_publish_rejection(exc):
                        job.publish_requested_at = None
                        await _record_publication_failure(db, job.id, job.account_id, exc)
                        continue
                    status_code = None  # still uncertain; check again later
                else:
                    job.published_media_id = published_id
                    await record_publication_confirmed(db, job, datetime.now(timezone.utc))
                    await db.commit()
                    resolved += 1
                    continue
            if status_code in {"ERROR", "EXPIRED"}:
                job.publish_requested_at = None
                await _record_publication_failure(
                    db, job.id, job.account_id,
                    InstagramPublishingError(
                        f"O container da Meta terminou como {status_code}; nada foi publicado."
                    ),
                )
                continue
            # IN_PROGRESS or unknown: try again later, then ask for review.
            job.reconcile_attempts += 1
            if current - requested_at >= RECONCILE_GIVE_UP_AFTER:
                job.status = "failed"
                job.next_retry_at = None
                job.error_category = "uncertain"
                job.last_error = (
                    "Não foi possível confirmar se o vídeo foi publicado. Verifique no "
                    "Instagram e use “Tentar novamente” apenas se ele não aparecer."
                )
                await record_publication_given_up(db, job, current, needs_review=True)
            else:
                job.next_retry_at = current + RECONCILE_RETRY_DELAY * min(
                    job.reconcile_attempts, 15
                )
            await db.commit()
    return resolved


async def fail_stale_publication_jobs(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    cutoff = current - STALE_PUBLICATION_AFTER
    async with get_session_factory()() as db:
        stale_jobs = (
            await db.scalars(
                select(InstagramPublicationJob).where(
                    InstagramPublicationJob.status == "publishing",
                    InstagramPublicationJob.updated_at < cutoff,
                    # Jobs that reached media_publish are reconciled instead.
                    InstagramPublicationJob.publish_requested_at.is_(None),
                )
            )
        ).all()
        for job in stale_jobs:
            # The worker stopped before media_publish: nothing was published,
            # so the same video can safely be tried again.
            job.container_id = None
            if job.attempts < MAX_AUTO_ATTEMPTS:
                job.status = "queued"
                job.next_retry_at = current
                job.last_error = "O worker parou antes de enviar à Meta; nova tentativa agendada."
            else:
                job.status = "failed"
                job.next_retry_at = None
                job.last_error = "O worker parou antes de enviar à Meta repetidas vezes."
                await record_publication_given_up(db, job, current)
        await db.commit()
    if stale_jobs:
        logger.error("Marked %s stale publication jobs for manual review.", len(stale_jobs))
    return len(stale_jobs)


async def prune_old_records(now: datetime | None = None) -> None:
    current = now or datetime.now(timezone.utc)
    try:
        async with get_session_factory()() as db:
            await db.execute(
                delete(InstagramPublicationJob).where(
                    InstagramPublicationJob.status == "failed",
                    InstagramPublicationJob.updated_at < current - FAILURE_RETENTION,
                )
            )
            await db.execute(
                delete(DiagnosticsEvent).where(
                    DiagnosticsEvent.created_at < current - DIAGNOSTICS_RETENTION
                )
            )
            await db.commit()
    except SQLAlchemyError:
        logger.exception("Could not prune old failures and diagnostics.")


async def run_loop_scheduler_tick() -> int:
    logger.info("Starting Loop publication scheduler tick.")
    await _mark_expired_accounts(datetime.now(timezone.utc))
    await fail_stale_publication_jobs()
    try:
        await reconcile_uncertain_publications()
    except Exception as exc:
        logger.error("Publication reconciliation failed (%s); it will retry.", type(exc).__name__)
    refreshed_tokens = await refresh_due_instagram_tokens()
    async with get_session_factory()() as db:
        created_jobs = await enqueue_due_loop_publications(db)
    published_jobs = 0
    if get_settings().instagram_publishing_enabled:
        async def drain_queue() -> int:
            processed_jobs = 0
            while True:
                try:
                    processed = await process_one_queued_publication()
                except Exception as exc:
                    logger.error(
                        "Loop publication worker could not process the next queued job (%s); "
                        "remaining jobs will be retried on the next scheduler tick.",
                        type(exc).__name__,
                    )
                    return processed_jobs
                if not processed:
                    return processed_jobs
                processed_jobs += 1

        async with get_session_factory()() as db:
            queued_now = (
                await db.scalar(
                    select(func.count())
                    .select_from(InstagramPublicationJob)
                    .where(
                        InstagramPublicationJob.status == "queued",
                        or_(
                            InstagramPublicationJob.next_retry_at.is_(None),
                            InstagramPublicationJob.next_retry_at
                            <= datetime.now(timezone.utc),
                        ),
                        InstagramPublicationJob.workspace_id.in_(workspaces_allowed_to_post()),
                    )
                )
            ) or 0
        # One worker per ready job: there is no fixed concurrency cap.
        worker_results = await asyncio.gather(
            *(drain_queue() for _ in range(max(queued_now, 1)))
        )
        published_jobs = sum(worker_results)
        await prune_old_records()
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
