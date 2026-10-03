from datetime import datetime, timedelta, timezone
import random
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.auth.dependencies import DbSession, OwnerAccess, WorkspaceMemberAccess, require_csrf
from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramPublicationJob,
)
from app.core.security import WorkspaceRole
from app.schemas.loops import (
    InstagramLoopAccountResponse,
    InstagramLoopCreateRequest,
    InstagramLoopResponse,
    InstagramLoopStatusRequest,
    InstagramLoopsResponse,
)

router = APIRouter(prefix="/api/loops", tags=["Instagram loops"])
_PENDING_JOB_STATUSES = ("waiting_for_media", "queued", "publishing")


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
        InstagramAccount.token_expires_at > datetime.now(timezone.utc),
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
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    published_count = await db.scalar(
        select(func.count(InstagramPublicationJob.id)).where(
            InstagramPublicationJob.loop_id == loop.id,
            InstagramPublicationJob.status == "published",
            InstagramPublicationJob.scheduled_for >= midnight,
            InstagramPublicationJob.scheduled_for < midnight + timedelta(days=1),
        )
    )
    return InstagramLoopResponse(
        id=loop.id,
        name=loop.name,
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
                username=account.username,
                token_expires_at=_utc_datetime(account.token_expires_at),
            )
            for account in accounts
        ],
        waiting_for_media_count=waiting_count or 0,
        published_today_count=published_count or 0,
    )


@router.get("", response_model=InstagramLoopsResponse)
async def list_loops(
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> InstagramLoopsResponse:
    now = datetime.now(timezone.utc)
    loops = (
        await db.scalars(
            select(InstagramLoop)
            .where(InstagramLoop.workspace_id == access.workspace.id)
            .order_by(InstagramLoop.created_at.desc(), InstagramLoop.id)
        )
    ).all()
    accounts = await _workspace_accounts(access.workspace.id, db)
    return InstagramLoopsResponse(
        can_manage=access.membership.role == WorkspaceRole.OWNER.value,
        loops=[await _loop_response(loop, db, now) for loop in loops],
        available_accounts=[
            InstagramLoopAccountResponse(
                id=account.id,
                username=account.username,
                token_expires_at=_utc_datetime(account.token_expires_at),
            )
            for account in accounts
        ],
    )


async def _validate_selected_accounts(
    workspace_id: uuid.UUID,
    account_ids: list[uuid.UUID],
    db: DbSession,
) -> list[InstagramAccount]:
    accounts = await _workspace_accounts(workspace_id, db, account_ids)
    if len(accounts) != len(account_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Select only connected Instagram accounts with unexpired tokens.",
        )
    return accounts


def _next_run_at(loop: InstagramLoop, now: datetime) -> datetime:
    interval = random.randint(loop.interval_min_minutes, loop.interval_max_minutes)
    return now + timedelta(minutes=interval)


def _save_loop_accounts(
    loop: InstagramLoop,
    accounts: list[InstagramAccount],
    db: DbSession,
) -> None:
    for account in accounts:
        db.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))


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
    now = datetime.now(timezone.utc)
    loop = InstagramLoop(
        workspace_id=access.workspace.id,
        name=payload.name,
        interval_min_minutes=payload.interval_min_minutes,
        interval_max_minutes=payload.interval_max_minutes,
        daily_limit_per_account=payload.daily_limit_per_account,
        post_type=payload.post_type,
        repeat_media=payload.repeat_media,
        status="active",
        next_run_at=now + timedelta(
            minutes=random.randint(
                payload.interval_min_minutes,
                payload.interval_max_minutes,
            )
        ),
    )
    db.add(loop)
    await db.flush()
    _save_loop_accounts(loop, accounts, db)
    await db.commit()
    await db.refresh(loop)
    return await _loop_response(loop, db, now)


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
    accounts = await _validate_selected_accounts(
        access.workspace.id,
        payload.account_ids,
        db,
    )
    loop.name = payload.name
    loop.interval_min_minutes = payload.interval_min_minutes
    loop.interval_max_minutes = payload.interval_max_minutes
    loop.daily_limit_per_account = payload.daily_limit_per_account
    loop.post_type = payload.post_type
    loop.repeat_media = payload.repeat_media
    loop.next_run_at = _next_run_at(loop, datetime.now(timezone.utc)) if loop.status == "active" else None
    await db.execute(
        InstagramLoopAccount.__table__.delete().where(
            InstagramLoopAccount.loop_id == loop.id
        )
    )
    _save_loop_accounts(loop, accounts, db)
    await db.commit()
    await db.refresh(loop)
    return await _loop_response(loop, db, datetime.now(timezone.utc))


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
    loop.status = "active" if payload.enabled else "paused"
    loop.next_run_at = (
        _next_run_at(loop, datetime.now(timezone.utc)) if payload.enabled else None
    )
    await db.commit()
    await db.refresh(loop)
    return await _loop_response(loop, db, datetime.now(timezone.utc))


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
    await db.delete(loop)
    await db.commit()
