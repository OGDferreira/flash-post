from datetime import datetime, timezone
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
from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
)
from app.loops.scheduler import enqueue_loop_publications_now
from app.core.security import WorkspaceRole
from app.schemas.loops import (
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
    waiting_count = await db.scalar(
        select(func.count(InstagramPublicationJob.id)).where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status == "waiting_for_media",
        )
    )
    local_day_start, local_day_end = local_day_bounds_utc(now)
    published_count = await db.scalar(
        select(func.count(InstagramPublicationJob.id)).where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status == "published",
            InstagramPublicationJob.updated_at >= local_day_start,
            InstagramPublicationJob.updated_at < local_day_end,
        )
    )
    failed_count = await db.scalar(
        select(func.count(InstagramPublicationJob.id)).where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status == "failed",
        )
    )
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
        interval_min_minutes=loop.interval_min_minutes,
        interval_max_minutes=loop.interval_max_minutes,
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
        waiting_for_media_count=waiting_count or 0,
        published_today_count=published_count or 0,
        failed_count=failed_count or 0,
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
    limit: int = Query(default=100, ge=1, le=500),
) -> InstagramPublicationFailuresResponse:
    rows = (
        await db.execute(
            select(
                InstagramPublicationJob,
                InstagramLoop.name,
                InstagramAccount.username,
                InstagramMedia.filename,
            )
            .join(
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
                InstagramPublicationJob.last_error.is_not(None),
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
                loop_name=loop_name,
                account_username=username,
                media_filename=filename,
                scheduled_for=_utc_datetime(job.scheduled_for),
                updated_at=_utc_datetime(job.updated_at),
                attempts=job.attempts,
                error=job.last_error or "Falha sem detalhes registrados.",
            )
            for job, loop_name, username, filename in rows
        ]
    )


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
    accounts = await _validate_selected_accounts(
        access.workspace.id,
        payload.account_ids,
        db,
    )
    media = await _validate_selected_media(
        access.workspace.id,
        payload.media_ids,
        payload.post_type,
        db,
    )
    now = utc_now()
    loop = InstagramLoop(
        workspace_id=access.workspace.id,
        name=payload.name,
        interval_min_minutes=payload.interval_min_minutes,
        interval_max_minutes=payload.interval_max_minutes,
        post_type=payload.post_type,
        repeat_media=payload.repeat_media,
        status="active",
        next_run_at=now,
    )
    db.add(loop)
    await db.flush()
    _save_loop_accounts(loop, accounts, db)
    _save_loop_media(loop, media, db)
    await db.flush()
    if loop.status == "active":
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
        name=f"{source.name[:120 - len(clone_suffix)]}{clone_suffix}",
        interval_min_minutes=source.interval_min_minutes,
        interval_max_minutes=source.interval_max_minutes,
        post_type=source.post_type,
        repeat_media=source.repeat_media,
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
    accounts = await _validate_selected_accounts(
        access.workspace.id,
        payload.account_ids,
        db,
    )
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
    loop.post_type = payload.post_type
    loop.repeat_media = payload.repeat_media
    loop.next_run_at = now if loop.status == "active" else None
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
    await db.execute(
        InstagramPublicationJob.__table__.update()
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
            InstagramPublicationJob.account_id.in_(selected_account_ids),
        )
        .values(status="waiting_for_media", media_id=None, last_error=None)
    )
    await db.execute(
        InstagramPublicationJob.__table__.update()
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
            InstagramPublicationJob.account_id.not_in(selected_account_ids),
        )
        .values(
            status="failed",
            media_id=None,
            last_error="Loop configuration changed before this job started.",
        )
    )
    new_accounts = [account for account in accounts if account.id not in previous_account_ids]
    if loop.status == "active":
        await enqueue_loop_publications_now(
            db,
            loop,
            accounts if media is not None else new_accounts,
            now=now,
        )
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
    pending_jobs = InstagramPublicationJob.__table__.update().where(
        InstagramPublicationJob.loop_id == loop.id,
        InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
    )
    await db.execute(
        pending_jobs.where(
            InstagramPublicationJob.account_id.in_(selected_account_ids)
        ).values(status="waiting_for_media", media_id=None, last_error=None)
    )
    await db.execute(
        pending_jobs.where(
            InstagramPublicationJob.account_id.not_in(selected_account_ids)
        ).values(
            status="failed",
            media_id=None,
            last_error="Loop account configuration changed before this job started.",
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
    loop.next_run_at = now if payload.enabled else None
    if payload.enabled:
        if restarting:
            failed_account_ids = set(
                (
                    await db.scalars(
                        select(InstagramPublicationJob.account_id).where(
                            InstagramPublicationJob.loop_id == loop.id,
                            InstagramPublicationJob.status == "failed",
                        )
                    )
                ).all()
            )
            if failed_account_ids:
                await db.execute(
                    InstagramLoopAccount.__table__.delete().where(
                        InstagramLoopAccount.loop_id == loop.id,
                        InstagramLoopAccount.account_id.in_(failed_account_ids),
                    )
                )
                await db.execute(
                    InstagramPublicationJob.__table__.delete().where(
                        InstagramPublicationJob.loop_id == loop.id,
                        InstagramPublicationJob.account_id.in_(failed_account_ids),
                        InstagramPublicationJob.status.in_(
                            ("waiting_for_media", "queued")
                        ),
                    )
                )
            await db.execute(
                InstagramPublicationJob.__table__.delete().where(
                    InstagramPublicationJob.loop_id == loop.id,
                    InstagramPublicationJob.status == "failed",
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
        await db.execute(
            InstagramPublicationJob.__table__.update()
            .where(
                InstagramPublicationJob.loop_id == loop.id,
                InstagramPublicationJob.status == "queued",
            )
            .values(status="waiting_for_media", media_id=None)
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
        InstagramPublicationJob.__table__.update()
        .where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.media_id == media_id,
            InstagramPublicationJob.status == "queued",
        )
        .values(status="waiting_for_media", media_id=None)
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
