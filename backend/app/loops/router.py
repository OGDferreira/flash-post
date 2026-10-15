from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.auth.dependencies import (
    DbSession,
    LoopManagerAccess,
    OwnerAccess,
    WorkspaceMemberAccess,
    require_csrf,
)
from app.core.config import get_settings
from app.core.time import local_day_bounds_utc, utc_now
from app.instagram.account_state import classify_inactive_account
from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopAccountState,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
)
from app.loops.scheduler import (
    ACTIVE_JOB_STATUSES,
    BLOCKED_NEEDS_REVIEW,
    enqueue_loop_publications_now,
    loop_media_pool,
    next_media_index,
    record_publication_confirmed,
)
from app.core.security import WorkspaceRole
from app.schemas.loops import (
    InstagramAccountDailyProgress,
    InstagramAlertsResponse,
    InstagramLoopHealthResponse,
    InstagramRetryFailuresRequest,
    InstagramRetryFailuresResponse,
    InstagramPublicationFailureResponse,
    InstagramPublicationFailuresResponse,
    InstagramLoopAccountResponse,
    InstagramLoopAccountsUpdateRequest,
    InstagramLoopCreateRequest,
    InstagramLoopResponse,
    InstagramLoopStatusRequest,
    InstagramLoopsResponse,
)

router = APIRouter(prefix="/api/loops", tags=["Instagram loops"])
def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _workspace_accounts(
    workspace_id: uuid.UUID,
    db: DbSession,
    account_ids: list[uuid.UUID] | None = None,
) -> list[InstagramAccount]:
    query = select(InstagramAccount).where(
        InstagramAccount.workspace_id == workspace_id,
        InstagramAccount.status == "connected",
        InstagramAccount.encrypted_access_token.is_not(None),
        InstagramAccount.token_expires_at > utc_now(),
    )
    if account_ids is not None:
        query = query.where(InstagramAccount.id.in_(account_ids))
    return list((await db.scalars(query.order_by(InstagramAccount.username))).all())


async def _loop_response(
    loop: InstagramLoop,
    db: DbSession,
    now: datetime,
) -> InstagramLoopResponse:
    accounts = (
        await db.scalars(
            select(InstagramAccount)
            .join(
                InstagramLoopAccount,
                InstagramLoopAccount.account_id == InstagramAccount.id,
            )
            .where(
                InstagramLoopAccount.loop_id == loop.id,
                InstagramAccount.workspace_id == loop.workspace_id,
                InstagramAccount.status == "connected",
                InstagramAccount.encrypted_access_token.is_not(None),
                InstagramAccount.token_expires_at > now,
            )
            .order_by(InstagramAccount.username)
        )
    ).all()
    local_day_start, local_day_end = local_day_bounds_utc(now)
    job = InstagramPublicationJob
    today = (job.updated_at >= local_day_start) & (job.updated_at < local_day_end)
    published_today = (job.published_at >= local_day_start) & (job.published_at < local_day_end)
    counts = (
        await db.execute(
            select(
                func.count(job.id).filter(job.status == "waiting_for_media"),
                func.count(job.id).filter(
                    job.status.in_(("waiting_for_media", "queued", "publishing"))
                ),
                func.count(job.id).filter((job.status == "published") & published_today),
                func.coalesce(func.sum(job.attempts), 0),
                func.coalesce(func.sum(job.attempts).filter(today), 0),
                func.count(job.id).filter((job.status == "failed") & today),
                func.count(job.id).filter(job.status == "failed"),
                func.max(job.updated_at).filter(job.status == "failed"),
            ).where(job.loop_id == loop.id)
        )
    ).one()
    (
        waiting_count,
        queued_count,
        published_count,
        attempts_count,
        attempts_today_count,
        failed_today_count,
        failed_count,
        latest_failed_at,
    ) = counts
    selected_media = list(
        (
            await db.scalars(
                select(InstagramMedia)
                .join(
                    InstagramLoopMedia,
                    InstagramLoopMedia.media_id == InstagramMedia.id,
                )
                .where(
                    InstagramLoopMedia.loop_id == loop.id,
                    InstagramMedia.workspace_id == loop.workspace_id,
                )
                .order_by(InstagramMedia.created_at, InstagramMedia.id)
            )
        ).all()
    )
    return InstagramLoopResponse(
        id=loop.id,
        name=loop.name,
        auto_folder_ids=[uuid.UUID(str(item)) for item in (loop.auto_folder_ids or [])],
        interval_min_minutes=loop.interval_min_minutes,
        interval_max_minutes=loop.interval_max_minutes,
        daily_limit_per_account=loop.daily_limit_per_account,
        post_type=loop.post_type,
        repeat_media=loop.repeat_media,
        status=loop.status,
        next_run_at=_utc_datetime(loop.next_run_at) if loop.next_run_at else None,
        last_run_at=_utc_datetime(loop.last_run_at) if loop.last_run_at else None,
        accounts=[
            InstagramLoopAccountResponse(
                id=account.id,
                profile_folder_id=account.profile_folder_id,
                username=account.username,
                token_expires_at=_utc_datetime(account.token_expires_at),
                connected_at=_utc_datetime(account.connected_at),
                error_at=_utc_datetime(account.error_at) if account.error_at else None,
                status=account.status,
            )
            for account in accounts
        ],
        active_accounts_count=len(accounts),
        media_ids=[item.id for item in selected_media],
        media_names=[item.filename for item in selected_media],
        media_count=len(selected_media),
        video_count=sum(item.media_type == "video" for item in selected_media),
        waiting_for_media_count=waiting_count or 0,
        queued_publication_count=queued_count or 0,
        attempts_count=attempts_count or 0,
        attempts_today_count=attempts_today_count or 0,
        published_today_count=published_count or 0,
        failed_today_count=failed_today_count or 0,
        failed_count=failed_count or 0,
        latest_failed_at=(
            _utc_datetime(latest_failed_at) if latest_failed_at else None
        ),
    )


@router.get("", response_model=InstagramLoopsResponse)
async def list_loops(
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> InstagramLoopsResponse:
    now = utc_now()
    loops = (
        await db.scalars(
            select(InstagramLoop)
            .where(InstagramLoop.workspace_id == access.workspace.id)
            .order_by(InstagramLoop.created_at.desc(), InstagramLoop.id)
        )
    ).all()
    accounts = await _workspace_accounts(access.workspace.id, db)
    return InstagramLoopsResponse(
        can_manage=access.membership.role
        in {WorkspaceRole.OWNER.value, WorkspaceRole.COLLABORATOR.value},
        can_configure=access.membership.role == WorkspaceRole.OWNER.value,
        can_delete=access.membership.role == WorkspaceRole.OWNER.value,
        publishing_enabled=get_settings().instagram_publishing_enabled,
        loops=[await _loop_response(loop, db, now) for loop in loops],
        available_accounts=[
            InstagramLoopAccountResponse(
                id=account.id,
                profile_folder_id=account.profile_folder_id,
                username=account.username,
                token_expires_at=_utc_datetime(account.token_expires_at),
                connected_at=_utc_datetime(account.connected_at),
                error_at=_utc_datetime(account.error_at) if account.error_at else None,
                status=account.status,
            )
            for account in accounts
        ],
    )


@router.get("/failures", response_model=InstagramPublicationFailuresResponse)
async def list_publication_failures(
    access: OwnerAccess,
    db: DbSession,
    limit: int = Query(default=1000, ge=1, le=2000),
) -> InstagramPublicationFailuresResponse:
    rows = (
        await db.execute(
            select(
                InstagramPublicationJob,
                InstagramLoop.name,
                InstagramAccount.username,
                InstagramMedia.filename,
                InstagramAccount.status,
                select(InstagramLoopAccount.account_id)
                .where(
                    InstagramLoopAccount.loop_id == InstagramPublicationJob.loop_id,
                    InstagramLoopAccount.account_id == InstagramPublicationJob.account_id,
                )
                .exists(),
            )
            .outerjoin(
                InstagramLoop,
                InstagramLoop.id == InstagramPublicationJob.loop_id,
            )
            .join(
                InstagramAccount,
                InstagramAccount.id == InstagramPublicationJob.account_id,
            )
            .outerjoin(
                InstagramMedia,
                InstagramMedia.id == InstagramPublicationJob.media_id,
            )
            .where(
                InstagramPublicationJob.workspace_id == access.workspace.id,
                InstagramPublicationJob.status == "failed",
            )
            .order_by(
                InstagramPublicationJob.updated_at.desc(),
                InstagramPublicationJob.id.desc(),
            )
            .limit(limit)
        )
    ).all()
    return InstagramPublicationFailuresResponse(
        failures=[
            InstagramPublicationFailureResponse(
                id=job.id,
                account_id=job.account_id,
                loop_name=loop_name or "Loop removido",
                account_username=username,
                media_filename=filename,
                scheduled_for=_utc_datetime(job.scheduled_for),
                updated_at=_utc_datetime(job.updated_at),
                attempts=job.attempts,
                error=job.last_error or "Falha sem detalhes registrados.",
                account_in_loop=bool(in_loop),
                error_category=job.error_category,
                loop_id=job.loop_id,
                account_status=account_status,
            )
            for job, loop_name, username, filename, account_status, in_loop in rows
        ]
    )


DAILY_TARGET_PER_ACCOUNT = 24
EXPIRY_WARNING_DAYS = 7
HIGH_FAILURE_RATE = 0.3


@router.post(
    "/failures/retry",
    response_model=InstagramRetryFailuresResponse,
    dependencies=[Depends(require_csrf)],
)
async def retry_publication_failures(
    payload: InstagramRetryFailuresRequest,
    access: LoopManagerAccess,
    db: DbSession,
) -> InstagramRetryFailuresResponse:
    job = InstagramPublicationJob
    query = (
        select(job)
        .join(InstagramAccount, InstagramAccount.id == job.account_id)
        .where(
            job.workspace_id == access.workspace.id,
            job.status == "failed",
            job.media_id.is_not(None),
            InstagramAccount.status == "connected",
        )
        .with_for_update(of=job)
    )
    if payload.job_ids:
        query = query.where(job.id.in_(payload.job_ids))
    if payload.loop_id:
        query = query.where(job.loop_id == payload.loop_id)
    if not payload.job_ids and not payload.loop_id:
        query = query.where(job.updated_at >= local_day_bounds_utc(utc_now())[0])
    jobs = (await db.scalars(query.limit(2000))).all()
    requeued = 0
    now = utc_now()
    handled: set[tuple] = set()
    for item in jobs:
        key = (item.loop_id, item.account_id)
        state = await db.get(InstagramLoopAccountState, key)
        if state is not None and state.blocked_reason == BLOCKED_NEEDS_REVIEW:
            # The owner checked Instagram and asked to try again.
            state.blocked_reason = None
            state.next_run_at = now
        if key in handled:
            await db.delete(item)
            continue
        active = await db.scalar(
            select(job.id)
            .where(
                job.loop_id == item.loop_id,
                job.account_id == item.account_id,
                job.status.in_(ACTIVE_JOB_STATUSES),
            )
            .limit(1)
        )
        handled.add(key)
        if active is not None:
            # A pending job already covers this account's next video.
            await db.delete(item)
            continue
        # The position never advanced on failure, so this job holds the
        # account's next video: requeue it rather than queue a new one.
        item.status = "queued"
        item.attempts = 0
        item.next_retry_at = None
        item.last_error = None
        item.error_category = None
        item.container_id = None
        item.publish_requested_at = None
        item.reconcile_attempts = 0
        item.scheduled_for = now
        requeued += 1
    await db.commit()
    return InstagramRetryFailuresResponse(requeued=requeued)


@router.post(
    "/jobs/{job_id}/confirm-published",
    response_model=InstagramRetryFailuresResponse,
    dependencies=[Depends(require_csrf)],
)
async def confirm_publication(
    job_id: uuid.UUID,
    access: LoopManagerAccess,
    db: DbSession,
) -> InstagramRetryFailuresResponse:
    """The owner saw the video on Instagram: count it and advance the account."""
    item = await db.scalar(
        select(InstagramPublicationJob)
        .where(
            InstagramPublicationJob.id == job_id,
            InstagramPublicationJob.workspace_id == access.workspace.id,
            InstagramPublicationJob.status == "failed",
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Publicação não encontrada.")
    await record_publication_confirmed(
        db, item, _utc_datetime(item.publish_requested_at or item.updated_at)
    )
    await db.commit()
    return InstagramRetryFailuresResponse(requeued=0)


@router.get("/alerts", response_model=InstagramAlertsResponse)
async def loop_alerts(
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> InstagramAlertsResponse:
    now = utc_now()
    expiring = (
        await db.scalars(
            select(InstagramAccount.username)
            .where(
                InstagramAccount.workspace_id == access.workspace.id,
                InstagramAccount.status == "connected",
                InstagramAccount.token_expires_at > now,
                InstagramAccount.token_expires_at
                <= now + timedelta(days=EXPIRY_WARNING_DAYS),
            )
            .order_by(InstagramAccount.token_expires_at)
            .limit(50)
        )
    ).all()
    disconnected = await db.scalar(
        select(func.count(InstagramAccount.id)).where(
            InstagramAccount.workspace_id == access.workspace.id,
            InstagramAccount.status == "error",
        )
    )
    inactive_rows = (
        await db.execute(
            select(InstagramAccount.username, InstagramAccount.status, InstagramAccount.status_reason).where(
                InstagramAccount.workspace_id == access.workspace.id,
                InstagramAccount.status == "error",
            )
        )
    ).all()
    restricted: list[str] = []
    suspended: list[str] = []
    for username, account_status, reason in inactive_rows:
        kind = classify_inactive_account(account_status, reason)
        if kind == "restricted":
            restricted.append(username)
        elif kind == "suspended":
            suspended.append(username)
    day_start, day_end = local_day_bounds_utc(now)
    job = InstagramPublicationJob
    published, failed = (
        await db.execute(
            select(
                func.count(job.id).filter(job.status == "published"),
                func.count(job.id).filter(job.status == "failed"),
            ).where(
                job.workspace_id == access.workspace.id,
                job.updated_at >= day_start,
                job.updated_at < day_end,
            )
        )
    ).one()
    total = published + failed
    rate = failed / total if total else 0.0
    return InstagramAlertsResponse(
        expiring_accounts=list(expiring),
        expiring_within_days=EXPIRY_WARNING_DAYS,
        disconnected_count=disconnected or 0,
        restricted_accounts=restricted[:50],
        suspended_accounts=suspended[:50],
        published_today=published,
        failed_today=failed,
        failure_rate=round(rate, 3),
        high_failure_rate=total >= 10 and rate >= HIGH_FAILURE_RATE,
    )


@router.get("/{loop_id}/health", response_model=InstagramLoopHealthResponse)
async def loop_health(
    loop_id: uuid.UUID,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> InstagramLoopHealthResponse:
    loop = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == access.workspace.id,
        )
    )
    if loop is None:
        raise HTTPException(status_code=404, detail="Loop não encontrado.")
    now = utc_now()
    return InstagramLoopHealthResponse(
        loop_id=loop.id,
        target_per_account=loop.daily_limit_per_account,
        accounts=await _account_loop_states(loop, db, now),
    )


async def _account_loop_states(
    loop: InstagramLoop, db: DbSession, now: datetime
) -> list[InstagramAccountDailyProgress]:
    """What each account is really doing in this loop, from persisted facts:
    connection, loop status, the account's own schedule/position, the job in
    flight, today's confirmed publications and the latest failure."""
    day_start, day_end = local_day_bounds_utc(now)
    job = InstagramPublicationJob
    member_ids = set(
        (
            await db.scalars(
                select(InstagramLoopAccount.account_id).where(InstagramLoopAccount.loop_id == loop.id)
            )
        ).all()
    )
    state_rows = {
        state.account_id: state
        for state in (
            await db.scalars(
                select(InstagramLoopAccountState).where(InstagramLoopAccountState.loop_id == loop.id)
            )
        ).all()
    }
    account_ids = member_ids | set(state_rows)
    if not account_ids:
        return []
    accounts = (
        await db.scalars(
            select(InstagramAccount)
            .where(
                InstagramAccount.id.in_(account_ids),
                InstagramAccount.workspace_id == loop.workspace_id,
            )
            .order_by(InstagramAccount.username)
        )
    ).all()
    pool = await loop_media_pool(db, loop)
    published_counts = dict(
        (
            await db.execute(
                select(job.account_id, func.count(job.id))
                .where(
                    job.loop_id == loop.id,
                    job.status == "published",
                    job.published_at >= day_start,
                    job.published_at < day_end,
                )
                .group_by(job.account_id)
            )
        ).all()
    )
    failed_counts = dict(
        (
            await db.execute(
                select(job.account_id, func.count(job.id))
                .where(
                    job.loop_id == loop.id,
                    job.status == "failed",
                    job.updated_at >= day_start,
                    job.updated_at < day_end,
                )
                .group_by(job.account_id)
            )
        ).all()
    )
    active_jobs = {
        item.account_id: item
        for item in (
            await db.scalars(
                select(job).where(job.loop_id == loop.id, job.status.in_(ACTIVE_JOB_STATUSES))
            )
        ).all()
    }
    result: list[InstagramAccountDailyProgress] = []
    for account in accounts:
        state = state_rows.get(account.id)
        in_loop = account.id in member_ids
        last_failure = await db.scalar(
            select(job)
            .where(job.loop_id == loop.id, job.account_id == account.id, job.status == "failed")
            .order_by(job.updated_at.desc(), job.id.desc())
            .limit(1)
        )
        last_published_at = (
            _utc_datetime(state.last_published_at)
            if state is not None and state.last_published_at
            else None
        )
        failure_is_latest = last_failure is not None and (
            last_published_at is None
            or _utc_datetime(last_failure.updated_at) > last_published_at
        )
        token_valid = (
            account.encrypted_access_token is not None
            and _utc_datetime(account.token_expires_at) > now
        )
        connection = account.status if account.status != "connected" or token_valid else "expired"
        active = active_jobs.get(account.id)
        next_run_at = (
            _utc_datetime(state.next_run_at) if state is not None and state.next_run_at else None
        )
        if connection != "connected" or not in_loop:
            state_name = "disconnected"
        elif state is not None and state.blocked_reason == BLOCKED_NEEDS_REVIEW:
            state_name = "needs_review"
        elif active is not None:
            state_name = "publishing" if active.status == "publishing" else "queued"
        elif loop.status != "active":
            state_name = "loop_paused"
        elif state is not None and state.blocked_reason in {"daily_limit", "no_media", "instagram_cap"}:
            state_name = state.blocked_reason
        elif failure_is_latest:
            state_name = "failing"
        elif next_run_at is not None and next_run_at > now:
            state_name = "scheduled"
        else:
            state_name = "due"
        position = next_media_index(state, pool) if state is not None and pool else 0
        result.append(
            InstagramAccountDailyProgress(
                account_id=account.id,
                username=account.username,
                published_today=published_counts.get(account.id, 0),
                failed_today=failed_counts.get(account.id, 0),
                target=loop.daily_limit_per_account,
                token_expires_at=_utc_datetime(account.token_expires_at),
                state=state_name,
                connection_status=connection,
                in_loop=in_loop,
                next_run_at=next_run_at,
                last_published_at=last_published_at,
                next_video_number=(position + 1) if pool else None,
                playlist_size=len(pool),
                cycles_completed=state.cycles_completed if state is not None else 0,
                last_error=last_failure.last_error if failure_is_latest and last_failure else (
                    account.status_reason if connection != "connected" else None
                ),
                last_error_at=(
                    _utc_datetime(last_failure.updated_at)
                    if failure_is_latest and last_failure
                    else (_utc_datetime(account.error_at) if account.error_at else None)
                ),
                review_job_id=(
                    last_failure.id
                    if state_name == "needs_review" and last_failure is not None
                    else None
                ),
            )
        )
    return result


async def _validate_selected_accounts(
    workspace_id: uuid.UUID,
    account_ids: list[uuid.UUID],
    db: DbSession,
) -> list[InstagramAccount]:
    accounts = await _workspace_accounts(workspace_id, db, account_ids)
    if len(accounts) != len(account_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select only connected Instagram accounts with unexpired tokens.",
        )
    return accounts


async def _selected_with_folders(
    workspace_id: uuid.UUID,
    account_ids: list[uuid.UUID],
    folder_ids: list[uuid.UUID],
    db: DbSession,
) -> tuple[list[InstagramAccount], list[str]]:
    """Chosen accounts plus every connected account of the watched folders."""
    from app.instagram.folder_automation import folder_accounts
    from app.models import InstagramProfileFolder

    valid_folders = set(
        (
            await db.scalars(
                select(InstagramProfileFolder.id).where(
                    InstagramProfileFolder.workspace_id == workspace_id,
                    InstagramProfileFolder.id.in_(folder_ids),
                )
            )
        ).all()
    ) if folder_ids else set()
    if valid_folders != set(folder_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uma ou mais pastas não pertencem a este workspace.",
        )
    accounts = await _validate_selected_accounts(workspace_id, account_ids, db)
    known = {account.id for account in accounts}
    extra = [
        account
        for account in await folder_accounts(db, workspace_id, [str(item) for item in folder_ids])
        if account.id not in known and account.token_expires_at and account.token_expires_at > utc_now()
    ]
    return [*accounts, *extra], [str(item) for item in folder_ids]


async def _validate_selected_media(
    workspace_id: uuid.UUID,
    media_ids: list[uuid.UUID] | None,
    post_type: str,
    db: DbSession,
    loop_id: uuid.UUID | None = None,
) -> list[InstagramMedia]:
    if not media_ids:
        return []
    query = select(InstagramMedia).where(
        InstagramMedia.workspace_id == workspace_id,
        InstagramMedia.id.in_(media_ids),
    )
    if post_type == "reels":
        query = query.where(InstagramMedia.media_type == "video")
    elif post_type == "images":
        query = query.where(InstagramMedia.media_type == "image")
    media = list((await db.scalars(query.order_by(InstagramMedia.created_at, InstagramMedia.id))).all())
    if len(media) != len(media_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select only media in this workspace that matches the loop publication type.",
        )
    assigned_media_ids = set(
        (
            await db.scalars(
                select(InstagramLoopMedia.media_id)
                .join(InstagramLoop, InstagramLoop.id == InstagramLoopMedia.loop_id)
                .where(
                    InstagramLoop.workspace_id == workspace_id,
                    InstagramLoopMedia.media_id.in_(media_ids),
                )
            )
        ).all()
    )
    current_loop_media_ids = set()
    if loop_id is not None:
        current_loop_media_ids = set(
            (
                await db.scalars(
                    select(InstagramLoopMedia.media_id).where(
                        InstagramLoopMedia.loop_id == loop_id,
                        InstagramLoopMedia.media_id.in_(media_ids),
                    )
                )
            ).all()
        )
    if assigned_media_ids - current_loop_media_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Uma ou mais mídias já estão em outro loop. Clone o loop para reutilizá-las.",
        )
    return media


def _save_loop_accounts(
    loop: InstagramLoop,
    accounts: list[InstagramAccount],
    db: DbSession,
) -> None:
    for account in accounts:
        db.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))


def _save_loop_media(
    loop: InstagramLoop,
    media: list[InstagramMedia],
    db: DbSession,
) -> None:
    for item in media:
        db.add(InstagramLoopMedia(loop_id=loop.id, media_id=item.id))


@router.post(
    "",
    response_model=InstagramLoopResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_loop(
    payload: InstagramLoopCreateRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramLoopResponse:
    accounts, auto_folders = await _selected_with_folders(
        access.workspace.id, payload.account_ids, payload.auto_folder_ids, db
    )
    media = await _validate_selected_media(
        access.workspace.id,
        payload.media_ids,
        payload.post_type,
        db,
    )
    now = utc_now()
    loop = InstagramLoop(
        auto_folder_ids=auto_folders,
        workspace_id=access.workspace.id,
        name=payload.name,
        interval_min_minutes=payload.interval_min_minutes,
        interval_max_minutes=payload.interval_max_minutes,
        daily_limit_per_account=payload.daily_limit_per_account,
        post_type=payload.post_type,
        repeat_media=True,
        status="active",
        next_run_at=now,
    )
    db.add(loop)
    await db.flush()
    _save_loop_accounts(loop, accounts, db)
    _save_loop_media(loop, media, db)
    await db.flush()
    await enqueue_loop_publications_now(db, loop, accounts, now=now)
    await db.commit()
    await db.refresh(loop)
    return await _loop_response(loop, db, now)


@router.post(
    "/{loop_id}/clone",
    response_model=InstagramLoopResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def clone_loop(
    loop_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramLoopResponse:
    source = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == access.workspace.id,
        )
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loop not found.")

    now = utc_now()
    clone_suffix = " (cópia)"
    clone = InstagramLoop(
        workspace_id=source.workspace_id,
        auto_folder_ids=list(source.auto_folder_ids or []),
        name=f"{source.name[:120 - len(clone_suffix)]}{clone_suffix}",
        interval_min_minutes=source.interval_min_minutes,
        interval_max_minutes=source.interval_max_minutes,
        daily_limit_per_account=source.daily_limit_per_account,
        post_type=source.post_type,
        repeat_media=True,
        status="paused",
        next_run_at=None,
    )
    db.add(clone)
    await db.flush()

    account_ids = (
        await db.scalars(
            select(InstagramLoopAccount.account_id).where(
                InstagramLoopAccount.loop_id == source.id
            )
        )
    ).all()
    media_ids = (
        await db.scalars(
            select(InstagramLoopMedia.media_id).where(
                InstagramLoopMedia.loop_id == source.id
            )
        )
    ).all()
    for account_id in account_ids:
        db.add(InstagramLoopAccount(loop_id=clone.id, account_id=account_id))
    for media_id in media_ids:
        db.add(InstagramLoopMedia(loop_id=clone.id, media_id=media_id))

    await db.commit()
    await db.refresh(clone)
    return await _loop_response(clone, db, now)


@router.put(
    "/{loop_id}",
    response_model=InstagramLoopResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_loop(
    loop_id: uuid.UUID,
    payload: InstagramLoopCreateRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramLoopResponse:
    loop = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == access.workspace.id,
        )
    )
    if loop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loop not found.")
    previous_account_ids = set(
        (
            await db.scalars(
                select(InstagramLoopAccount.account_id).where(
                    InstagramLoopAccount.loop_id == loop.id
                )
            )
        ).all()
    )
    accounts, auto_folders = await _selected_with_folders(
        access.workspace.id, payload.account_ids, payload.auto_folder_ids, db
    )
    loop.auto_folder_ids = auto_folders
    media = (
        await _validate_selected_media(
            access.workspace.id,
            payload.media_ids,
            payload.post_type,
            db,
            loop_id=loop.id,
        )
        if payload.media_ids is not None
        else None
    )
    loop.name = payload.name
    now = utc_now()
    loop.interval_min_minutes = payload.interval_min_minutes
    loop.interval_max_minutes = payload.interval_max_minutes
    loop.daily_limit_per_account = payload.daily_limit_per_account
    loop.post_type = payload.post_type
    loop.repeat_media = True
    await db.execute(
        InstagramLoopAccount.__table__.delete().where(
            InstagramLoopAccount.loop_id == loop.id
        )
    )
    _save_loop_accounts(loop, accounts, db)
    selected_account_ids = [account.id for account in accounts]
    if media is not None:
        await db.execute(
            InstagramLoopMedia.__table__.delete().where(
                InstagramLoopMedia.loop_id == loop.id
            )
        )
        _save_loop_media(loop, media, db)
    await db.flush()
    # Jobs that have not started carry no progress: drop the ones for removed
    # accounts and, when the playlist changed, the rest too so each account is
    # re-queued with its own next video. Jobs already publishing are kept.
    pending = InstagramPublicationJob.__table__.delete().where(
        InstagramPublicationJob.loop_id == loop.id,
        InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
    )
    if media is None:
        pending = pending.where(InstagramPublicationJob.account_id.not_in(selected_account_ids))
    await db.execute(pending)
    if loop.status == "active":
        await enqueue_loop_publications_now(db, loop, accounts, now=now)
    await db.commit()
    await db.refresh(loop)
    return await _loop_response(loop, db, utc_now())


@router.put(
    "/{loop_id}/accounts",
    response_model=InstagramLoopResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_loop_accounts(
    loop_id: uuid.UUID,
    payload: InstagramLoopAccountsUpdateRequest,
    access: LoopManagerAccess,
    db: DbSession,
) -> InstagramLoopResponse:
    loop = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == access.workspace.id,
        )
    )
    if loop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loop not found.")

    previous_account_ids = set(
        (
            await db.scalars(
                select(InstagramLoopAccount.account_id).where(
                    InstagramLoopAccount.loop_id == loop.id
                )
            )
        ).all()
    )
    accounts = await _validate_selected_accounts(
        access.workspace.id,
        payload.account_ids,
        db,
    )
    await db.execute(
        InstagramLoopAccount.__table__.delete().where(
            InstagramLoopAccount.loop_id == loop.id
        )
    )
    _save_loop_accounts(loop, accounts, db)
    await db.flush()

    selected_account_ids = [account.id for account in accounts]
    await db.execute(
        InstagramPublicationJob.__table__.delete().where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
            InstagramPublicationJob.account_id.not_in(selected_account_ids),
        )
    )
    new_accounts = [account for account in accounts if account.id not in previous_account_ids]
    if loop.status == "active" and new_accounts:
        await enqueue_loop_publications_now(db, loop, new_accounts, now=utc_now())
    await db.commit()
    await db.refresh(loop)
    return await _loop_response(loop, db, utc_now())


@router.patch(
    "/{loop_id}/status",
    response_model=InstagramLoopResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_loop_status(
    loop_id: uuid.UUID,
    payload: InstagramLoopStatusRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramLoopResponse:
    loop = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == access.workspace.id,
        )
    )
    if loop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loop not found.")
    restarting = payload.enabled and loop.status != "active"
    loop.status = "active" if payload.enabled else "paused"
    now = utc_now()
    if payload.enabled:
        if restarting:
            # Clear the old failure history, except failures that still need a
            # human to confirm whether the video went out.
            await db.execute(
                InstagramPublicationJob.__table__.delete().where(
                    InstagramPublicationJob.loop_id == loop.id,
                    InstagramPublicationJob.status == "failed",
                    func.coalesce(InstagramPublicationJob.error_category, "") != "uncertain",
                )
            )
        accounts = (
            await db.scalars(
                select(InstagramAccount)
                .join(
                    InstagramLoopAccount,
                    InstagramLoopAccount.account_id == InstagramAccount.id,
                )
                .where(
                    InstagramLoopAccount.loop_id == loop.id,
                    InstagramAccount.workspace_id == loop.workspace_id,
                    InstagramAccount.status == "connected",
                    InstagramAccount.encrypted_access_token.is_not(None),
                    InstagramAccount.token_expires_at > now,
                )
            )
        ).all()
        await enqueue_loop_publications_now(db, loop, list(accounts), now=now)
    else:
        loop.next_run_at = None
        # Not-started jobs are dropped; each account keeps its position.
        await db.execute(
            InstagramPublicationJob.__table__.delete().where(
                InstagramPublicationJob.loop_id == loop.id,
                InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
            )
        )
    await db.commit()
    await db.refresh(loop)
    return await _loop_response(loop, db, utc_now())


@router.delete(
    "/{loop_id}/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def remove_loop_media(
    loop_id: uuid.UUID,
    media_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> None:
    loop = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == access.workspace.id,
        )
    )
    if loop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loop not found.")
    loop_media = await db.get(InstagramLoopMedia, (loop.id, media_id))
    if loop_media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loop media not found.")

    publishing_job = await db.scalar(
        select(InstagramPublicationJob.id)
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.media_id == media_id,
            InstagramPublicationJob.status == "publishing",
        )
        .limit(1)
    )
    if publishing_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A publication using this media is already in progress.",
        )

    await db.execute(
        InstagramPublicationJob.__table__.delete().where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.media_id == media_id,
            InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
        )
    )
    await db.delete(loop_media)
    await db.commit()


@router.delete(
    "/{loop_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_loop(
    loop_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> None:
    loop = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == access.workspace.id,
        )
    )
    if loop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loop not found.")
    active_publication = await db.scalar(
        select(InstagramPublicationJob.id)
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status == "publishing",
        )
        .limit(1)
    )
    if active_publication is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A publication is already in progress for this loop.",
        )
    await db.delete(loop)
    await db.commit()
