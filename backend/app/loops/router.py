from datetime import datetime, timedelta, timezone
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select

from app.instagram.storage import SupabaseStorage, SupabaseStorageError

logger = logging.getLogger(__name__)

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
    reschedule_loop_accounts,
)
from app.core.security import WorkspaceRole
from app.partners.service import linked_loop_available
from app.schemas.loops import (
    InstagramAccountDailyProgress,
    InstagramAlertsResponse,
    InstagramLoopHealthResponse,
    InstagramRetryFailuresRequest,
    InstagramRetryFailuresResponse,
    InstagramPublicationFailureResponse,
    InstagramPublicationFailuresResponse,
    InstagramLoopAccountResponse,
    InstagramLoopAccountsPage,
    InstagramLoopAccountsUpdateRequest,
    InstagramLoopCreateRequest,
    InstagramLoopResponse,
    InstagramLoopStatusRequest,
    InstagramLoopsResponse,
)

router = APIRouter(prefix="/api/loops", tags=["Instagram loops"])
LINKED_LOOP_LOCKED = (
    "Este loop é compartilhado pelo seu sócio: mídias e horários vêm do loop dele. "
    "Aqui você só escolhe as suas contas."
)


def _reject_linked(loop: InstagramLoop) -> None:
    """A partner's linked copy follows the chief's loop; only its accounts and status change here."""
    if loop.linked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=LINKED_LOOP_LOCKED)


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
    include_accounts: bool = True,
) -> InstagramLoopResponse:
    accounts_query = (
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
    if include_accounts:
        accounts = (
            await db.scalars(accounts_query.order_by(InstagramAccount.username))
        ).all()
        account_count = len(accounts)
    else:
        accounts = []
        account_count = await db.scalar(
            select(func.count()).select_from(accounts_query.subquery())
        ) or 0
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
        shared=bool(loop.shared),
        shared_with=(
            [uuid.UUID(str(item)) for item in loop.shared_with]
            if loop.shared and loop.shared_with is not None
            else None
        ),
        from_template=loop.template_loop_id is not None,
        linked=loop.linked,
        customized=loop.customized_at is not None,
        linked_available=await linked_loop_available(db, loop) if loop.linked or loop.customized_at else False,
        auto_folder_ids=[uuid.UUID(str(item)) for item in (loop.auto_folder_ids or [])],
        interval_min_minutes=loop.interval_min_minutes,
        interval_max_minutes=loop.interval_max_minutes,
        daily_limit_per_account=loop.daily_limit_per_account,
        post_type=loop.post_type,
        repeat_media=loop.repeat_media,
        caption_mode=loop.caption_mode or "per_media",
        caption=loop.caption,
        cover_mode=loop.cover_mode or "auto",
        cover_media_id=loop.cover_media_id,
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
        accounts_count=account_count,
        active_accounts_count=account_count,
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
    include_accounts: bool = True,
) -> InstagramLoopsResponse:
    now = utc_now()
    loops = (
        await db.scalars(
            select(InstagramLoop)
            .where(InstagramLoop.workspace_id == access.workspace.id)
            .order_by(InstagramLoop.created_at.desc(), InstagramLoop.id)
        )
    ).all()
    accounts_count = await db.scalar(
        select(func.count()).select_from(
            select(InstagramAccount.id)
            .where(
                InstagramAccount.workspace_id == access.workspace.id,
                InstagramAccount.status == "connected",
                InstagramAccount.encrypted_access_token.is_not(None),
                InstagramAccount.token_expires_at > now,
            )
            .subquery()
        )
    ) or 0
    accounts = (
        await _workspace_accounts(access.workspace.id, db)
        if include_accounts
        else []
    )
    return InstagramLoopsResponse(
        can_manage=access.membership.role
        in {WorkspaceRole.OWNER.value, WorkspaceRole.COLLABORATOR.value},
        can_configure=access.membership.role == WorkspaceRole.OWNER.value,
        can_delete=access.membership.role == WorkspaceRole.OWNER.value,
        publishing_enabled=get_settings().instagram_publishing_enabled,
        loops=[
            await _loop_response(loop, db, now, include_accounts=include_accounts)
            for loop in loops
        ],
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
        available_accounts_count=accounts_count,
    )


@router.get("/accounts", response_model=InstagramLoopAccountsPage)
async def list_loop_accounts(
    access: WorkspaceMemberAccess,
    db: DbSession,
    loop_id: uuid.UUID | None = None,
    only_loop_accounts: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> InstagramLoopAccountsPage:
    now = utc_now()
    if loop_id is not None:
        loop = await db.scalar(
            select(InstagramLoop).where(
                InstagramLoop.id == loop_id,
                InstagramLoop.workspace_id == access.workspace.id,
            )
        )
        if loop is None:
            raise HTTPException(status_code=404, detail="Loop não encontrado.")

    query = select(InstagramAccount).where(
        InstagramAccount.workspace_id == access.workspace.id,
        InstagramAccount.status == "connected",
        InstagramAccount.encrypted_access_token.is_not(None),
        InstagramAccount.token_expires_at > now,
    )
    if only_loop_accounts:
        if loop_id is None:
            raise HTTPException(
                status_code=422,
                detail="Informe um loop para listar as contas associadas.",
            )
        query = query.join(
            InstagramLoopAccount,
            InstagramLoopAccount.account_id == InstagramAccount.id,
        ).where(InstagramLoopAccount.loop_id == loop_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    accounts = (
        await db.scalars(
            query.order_by(InstagramAccount.username)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    selected_ids: list[uuid.UUID] = []
    if loop_id is not None:
        selected_ids = list(
            (
                await db.scalars(
                    select(InstagramLoopAccount.account_id)
                    .join(
                        InstagramAccount,
                        InstagramAccount.id == InstagramLoopAccount.account_id,
                    )
                    .where(
                        InstagramLoopAccount.loop_id == loop_id,
                        InstagramAccount.workspace_id == access.workspace.id,
                        InstagramAccount.status == "connected",
                        InstagramAccount.encrypted_access_token.is_not(None),
                        InstagramAccount.token_expires_at > now,
                    )
                )
            ).all()
        )
    return InstagramLoopAccountsPage(
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
        total=total,
        offset=offset,
        limit=limit,
        selected_ids=selected_ids,
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
    editing: bool = False,
) -> list[InstagramAccount]:
    """Eligible accounts among ``account_ids``.

    When editing, an account of this workspace that dropped out of "connected"
    while the form was open (a publishing error flips it back and forth) is
    skipped instead of rejecting the whole save; ids from another workspace are
    always refused.
    """
    if account_ids:
        known = set(
            (
                await db.scalars(
                    select(InstagramAccount.id).where(
                        InstagramAccount.workspace_id == workspace_id,
                        InstagramAccount.id.in_(account_ids),
                    )
                )
            ).all()
        )
        if known != set(account_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Select only connected Instagram accounts with unexpired tokens.",
            )
    accounts = await _workspace_accounts(workspace_id, db, account_ids)
    if not editing and len(accounts) != len(account_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select only connected Instagram accounts with unexpired tokens.",
        )
    return accounts


async def _kept_unavailable_accounts(
    loop: InstagramLoop,
    previous_account_ids: set[uuid.UUID],
    selected: list[InstagramAccount],
    db: DbSession,
) -> list[uuid.UUID]:
    """Accounts of the loop the form never showed (not connected right now).

    The edit form lists only eligible accounts, so it cannot have unchecked
    these; dropping them on save would silently take an account out of the loop
    because of a temporary error.
    """
    eligible = {account.id for account in await _workspace_accounts(loop.workspace_id, db)}
    chosen = {account.id for account in selected}
    return [item for item in previous_account_ids if item not in eligible and item not in chosen]


async def _selected_with_folders(
    workspace_id: uuid.UUID,
    account_ids: list[uuid.UUID],
    folder_ids: list[uuid.UUID],
    db: DbSession,
    editing: bool = False,
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
    accounts = await _validate_selected_accounts(workspace_id, account_ids, db, editing)
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
        InstagramMedia.is_cover.is_(False),
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
    kept_account_ids: list[uuid.UUID] = (),
) -> None:
    for account in accounts:
        db.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
    for account_id in kept_account_ids:
        db.add(InstagramLoopAccount(loop_id=loop.id, account_id=account_id))


def _save_loop_media(
    loop: InstagramLoop,
    media: list[InstagramMedia],
    db: DbSession,
) -> None:
    for item in media:
        db.add(InstagramLoopMedia(loop_id=loop.id, media_id=item.id))


async def _save_media_captions(
    loop: InstagramLoop,
    captions: dict[uuid.UUID, str | None],
    db: DbSession,
) -> None:
    """Update the post caption of media in this loop (other media are ignored)."""
    in_loop = (
        await db.scalars(
            select(InstagramMedia)
            .join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
            .where(
                InstagramLoopMedia.loop_id == loop.id,
                InstagramMedia.workspace_id == loop.workspace_id,
                InstagramMedia.id.in_(list(captions)),
            )
        )
    ).all()
    for item in in_loop:
        item.caption = captions[item.id]


async def _workspace_covers(
    workspace_id: uuid.UUID, cover_ids: set[uuid.UUID], db: DbSession
) -> set[uuid.UUID]:
    """The cover images among ``cover_ids`` that are JPEGs of this workspace."""
    if not cover_ids:
        return set()
    found = set(
        (
            await db.scalars(
                select(InstagramMedia.id).where(
                    InstagramMedia.workspace_id == workspace_id,
                    InstagramMedia.id.in_(cover_ids),
                    InstagramMedia.media_type == "image",
                )
            )
        ).all()
    )
    if found != cover_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A capa precisa ser uma imagem JPEG enviada a este workspace.",
        )
    return found


async def _apply_post_settings(
    loop: InstagramLoop, payload: InstagramLoopCreateRequest, db: DbSession
) -> None:
    """Caption and Reels cover choices of the loop, plus each video's own cover."""
    covers = {payload.cover_media_id} if payload.cover_media_id else set()
    covers |= {cover for cover in (payload.media_covers or {}).values() if cover}
    await _workspace_covers(loop.workspace_id, covers, db)
    loop.caption_mode = payload.caption_mode
    loop.caption = payload.caption
    loop.cover_mode = payload.cover_mode
    loop.cover_media_id = payload.cover_media_id
    if not payload.media_covers:
        return
    await db.flush()
    in_loop = (
        await db.scalars(
            select(InstagramMedia)
            .join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
            .where(
                InstagramLoopMedia.loop_id == loop.id,
                InstagramMedia.workspace_id == loop.workspace_id,
                InstagramMedia.id.in_(list(payload.media_covers)),
            )
        )
    ).all()
    for item in in_loop:
        item.cover_media_id = payload.media_covers[item.id]


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
    if payload.media_captions:
        await _save_media_captions(loop, payload.media_captions, db)
    await _apply_post_settings(loop, payload, db)
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
    _reject_linked(source)

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
        caption_mode=source.caption_mode,
        caption=source.caption,
        cover_mode=source.cover_mode,
        cover_media_id=source.cover_media_id,
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
    _reject_linked(loop)
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
        access.workspace.id, payload.account_ids, payload.auto_folder_ids, db, editing=True
    )
    loop.auto_folder_ids = auto_folders
    kept_account_ids = await _kept_unavailable_accounts(loop, previous_account_ids, accounts, db)
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
    interval_changed = (loop.interval_min_minutes, loop.interval_max_minutes) != (
        payload.interval_min_minutes,
        payload.interval_max_minutes,
    )
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
    _save_loop_accounts(loop, accounts, db, kept_account_ids)
    selected_account_ids = [account.id for account in accounts] + kept_account_ids
    if media is not None:
        await db.execute(
            InstagramLoopMedia.__table__.delete().where(
                InstagramLoopMedia.loop_id == loop.id
            )
        )
        _save_loop_media(loop, media, db)
    if payload.media_captions:
        await _save_media_captions(loop, payload.media_captions, db)
    await _apply_post_settings(loop, payload, db)
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
    if interval_changed:
        await reschedule_loop_accounts(db, loop, now)
        await db.flush()
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
    if payload.auto_folder_ids is not None:
        # Folders whose accounts join this loop (also new ones filed there later).
        accounts, loop.auto_folder_ids = await _selected_with_folders(
            access.workspace.id, payload.account_ids, payload.auto_folder_ids, db, editing=True
        )
    else:
        accounts = await _validate_selected_accounts(
            access.workspace.id,
            payload.account_ids,
            db,
            editing=True,
        )
    kept_account_ids = await _kept_unavailable_accounts(loop, previous_account_ids, accounts, db)
    await db.execute(
        InstagramLoopAccount.__table__.delete().where(
            InstagramLoopAccount.loop_id == loop.id
        )
    )
    _save_loop_accounts(loop, accounts, db, kept_account_ids)
    await db.flush()

    selected_account_ids = [account.id for account in accounts] + kept_account_ids
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
    if payload.enabled and (loop.linked or loop.customized_at) and not await linked_loop_available(db, loop):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seu sócio parou de compartilhar este loop, então ele não pode ser ativado.",
        )
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
    _reject_linked(loop)
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
    if loop.linked and await linked_loop_available(db, loop):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este loop é compartilhado pelo seu sócio e só sai daqui quando ele parar de compartilhar. Você pode pausá-lo.",
        )
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

    # Gather the loop's media before deleting it: the pool items and any Reels covers.
    # These are removed from the database (and storage) when nothing else uses them.
    workspace_id = loop.workspace_id
    pool_ids = list(
        await db.scalars(select(InstagramLoopMedia.media_id).where(InstagramLoopMedia.loop_id == loop.id))
    )
    cover_ids: set[uuid.UUID] = set()
    if loop.cover_media_id is not None:
        cover_ids.add(loop.cover_media_id)
    if pool_ids:
        for media in await db.scalars(select(InstagramMedia).where(InstagramMedia.id.in_(pool_ids))):
            if media.cover_media_id is not None:
                cover_ids.add(media.cover_media_id)

    # Remove this loop's pool associations explicitly (don't rely on DB cascade) so the
    # orphan check below sees the media as unreferenced by this loop.
    await db.execute(delete(InstagramLoopMedia).where(InstagramLoopMedia.loop_id == loop.id))
    await db.delete(loop)
    await db.flush()

    # Delete pool media first (freeing their covers), then the covers now left unused.
    removed_paths: list[str] = []
    for media_id in [*pool_ids, *cover_ids]:
        path = await _delete_media_if_orphaned(db, workspace_id, media_id)
        if path is not None:
            removed_paths.append(path)
    await db.commit()

    if removed_paths:
        try:
            storage = SupabaseStorage.from_settings()
        except RuntimeError as exc:
            logger.warning("Loop media removed from the database but storage is not configured (%s).", type(exc).__name__)
            return
        for path in removed_paths:
            try:
                await storage.delete(path)
            except (SupabaseStorageError, httpx.HTTPError) as exc:
                logger.warning("Loop media %s removed from the database but not from storage (%s).", path, type(exc).__name__)


async def _delete_media_if_orphaned(db, workspace_id: uuid.UUID, media_id: uuid.UUID) -> str | None:
    """Delete a media row once no loop pool, cover, or partner copy references it.

    Returns its storage path (to delete after commit) when removed, else None.
    """
    still_in_a_pool = await db.scalar(
        select(InstagramLoopMedia.media_id).where(InstagramLoopMedia.media_id == media_id).limit(1)
    )
    if still_in_a_pool is not None:
        return None
    used_as_media_cover = await db.scalar(
        select(InstagramMedia.id).where(InstagramMedia.cover_media_id == media_id).limit(1)
    )
    used_as_loop_cover = await db.scalar(
        select(InstagramLoop.id).where(InstagramLoop.cover_media_id == media_id).limit(1)
    )
    if used_as_media_cover is not None or used_as_loop_cover is not None:
        return None
    # A chief's media that a partner copy still follows must stay.
    is_partner_source = await db.scalar(
        select(InstagramMedia.id).where(InstagramMedia.template_media_id == media_id).limit(1)
    )
    if is_partner_source is not None:
        return None
    media = await db.get(InstagramMedia, media_id)
    if media is None or media.workspace_id != workspace_id:
        return None
    path = media.storage_path
    await db.delete(media)
    await db.flush()
    return path


async def _partner_copy(db, access, loop_id: uuid.UUID) -> InstagramLoop:
    loop = await db.scalar(
        select(InstagramLoop).where(InstagramLoop.id == loop_id, InstagramLoop.workspace_id == access.workspace.id)
    )
    if loop is None or loop.template_loop_id is None or not (loop.linked or loop.customized_at):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loop compartilhado não encontrado.")
    if not await linked_loop_available(db, loop):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seu sócio parou de compartilhar este loop.")
    return loop


@router.post("/{loop_id}/customize", response_model=InstagramLoopResponse, dependencies=[Depends(require_csrf)])
async def customize_shared_loop(loop_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> InstagramLoopResponse:
    """Turned off: a partner only picks the accounts and folders that post a shared loop;
    its schedule, limits and media stay the chief's."""
    await _partner_copy(db, access, loop_id)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="O loop compartilhado é do seu sócio: você escolhe só as contas e pastas que postam nele.",
    )


@router.post("/{loop_id}/follow-owner", response_model=InstagramLoopResponse, dependencies=[Depends(require_csrf)])
async def follow_shared_loop_again(loop_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> InstagramLoopResponse:
    """Undo the customization: the copy follows the chief's loop again (its schedule and
    media come back from the chief's; the partner's accounts stay)."""
    from app.partners.service import sync_linked_loop

    loop = await _partner_copy(db, access, loop_id)
    if not loop.linked:
        source = await db.get(InstagramLoop, loop.template_loop_id)
        loop.linked = True
        loop.customized_at = None
        await sync_linked_loop(db, source, loop)
        await db.commit()
        await db.refresh(loop)
    return await _loop_response(loop, db, utc_now())
