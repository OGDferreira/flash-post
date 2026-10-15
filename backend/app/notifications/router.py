import asyncio
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select

from app.auth.dependencies import DbSession, OwnerAccess, WorkspaceMemberAccess, require_csrf
from app.core.config import get_settings
from app.models import (
    DailyViewsGoal,
    DailyViewsGoalNotification,
    PushSubscription,
    User,
    WorkspaceMember,
)
from app.notifications.goals import (
    DEFAULT_TIME_ZONE,
    is_valid_time_zone,
    local_day_window,
    measure_goal_progress,
    resolve_time_zone,
)
from app.notifications.webpush import (
    WebPushError,
    b64url_decode,
    get_vapid_keys,
    is_allowed_push_endpoint,
    send_web_push,
)
from app.schemas.notifications import (
    DailyViewsGoalResponse,
    DailyViewsGoalsResponse,
    DailyViewsGoalUpdate,
    PushConfigResponse,
    PushSubscriptionRequest,
    PushTestResponse,
    PushUnsubscribeRequest,
)

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])
_MAX_DEVICES_PER_USER = 10
_TEST_COOLDOWN_SECONDS = 30
_REFRESH_COOLDOWN_SECONDS = 60
_last_test_push: dict[uuid.UUID, float] = {}
_refresh_locks: dict[uuid.UUID, asyncio.Lock] = {}


def _push_supported() -> bool:
    settings = get_settings()
    return settings.vapid_private_key is not None or settings.master_encryption_key is not None


async def _device_count(db: DbSession, user_id: uuid.UUID, workspace_id: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(func.count(PushSubscription.id)).where(
                PushSubscription.user_id == user_id,
                PushSubscription.workspace_id == workspace_id,
            )
        )
        or 0
    )


@router.get("/push/config", response_model=PushConfigResponse)
async def push_config(access: WorkspaceMemberAccess, db: DbSession) -> PushConfigResponse:
    devices = await _device_count(db, access.membership.user_id, access.workspace.id)
    if not _push_supported():
        return PushConfigResponse(supported=False, public_key=None, devices=devices)
    try:
        keys = await get_vapid_keys(db)
    except (WebPushError, RuntimeError, ValueError):
        return PushConfigResponse(supported=False, public_key=None, devices=devices)
    return PushConfigResponse(supported=True, public_key=keys.public_key_b64, devices=devices)


@router.post(
    "/push/subscriptions",
    response_model=PushConfigResponse,
    dependencies=[Depends(require_csrf)],
)
async def subscribe_push(
    payload: PushSubscriptionRequest,
    request: Request,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> PushConfigResponse:
    if not is_allowed_push_endpoint(payload.endpoint):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Serviço de push não reconhecido.",
        )
    try:
        public_key = b64url_decode(payload.keys.p256dh)
        auth_secret = b64url_decode(payload.keys.auth)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Chaves da inscrição inválidas.") from None
    if len(public_key) != 65 or public_key[0] != 4 or len(auth_secret) != 16:
        raise HTTPException(status_code=422, detail="Chaves da inscrição inválidas.")

    user_id = access.membership.user_id
    existing = await db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    user_agent = (request.headers.get("user-agent") or "")[:300] or None
    if existing is None:
        db.add(
            PushSubscription(
                user_id=user_id,
                workspace_id=access.workspace.id,
                endpoint=payload.endpoint,
                p256dh=payload.keys.p256dh,
                auth=payload.keys.auth,
                user_agent=user_agent,
            )
        )
    else:
        # Same browser, possibly another login: the device follows whoever
        # subscribed it last, so it never receives someone else's goals.
        existing.user_id = user_id
        existing.workspace_id = access.workspace.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
        existing.user_agent = user_agent
        existing.failure_count = 0
    await db.flush()
    stale = (
        await db.scalars(
            select(PushSubscription.id)
            .where(
                PushSubscription.user_id == user_id,
                PushSubscription.workspace_id == access.workspace.id,
            )
            .order_by(PushSubscription.created_at.desc(), PushSubscription.id.desc())
            .offset(_MAX_DEVICES_PER_USER)
        )
    ).all()
    if stale:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(stale)))
    await db.commit()
    return await push_config(access, db)


@router.delete(
    "/push/subscriptions",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def unsubscribe_push(
    payload: PushUnsubscribeRequest,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> Response:
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.user_id == access.membership.user_id,
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/push/test",
    response_model=PushTestResponse,
    dependencies=[Depends(require_csrf)],
)
async def send_test_push(access: WorkspaceMemberAccess, db: DbSession) -> PushTestResponse:
    user_id = access.membership.user_id
    now = time.monotonic()
    if now - _last_test_push.get(user_id, 0.0) < _TEST_COOLDOWN_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Aguarde alguns segundos antes de enviar outro teste.",
        )
    _last_test_push[user_id] = now
    subscriptions = (
        await db.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.workspace_id == access.workspace.id,
            )
        )
    ).all()
    if not subscriptions:
        return PushTestResponse(delivered=0, devices=0)
    try:
        keys = await get_vapid_keys(db)
    except (WebPushError, RuntimeError, ValueError):
        raise HTTPException(status_code=503, detail="Notificações push indisponíveis.") from None
    delivered = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        for subscription in subscriptions:
            result = await send_web_push(
                client,
                endpoint=subscription.endpoint,
                p256dh=subscription.p256dh,
                auth=subscription.auth,
                payload={
                    "title": "FlashPost",
                    "body": "Notificações ativadas neste dispositivo.",
                    "url": "/profile",
                    "tag": "flashpost-test",
                },
                keys=keys,
                ttl_seconds=600,
            )
            if result.ok:
                delivered += 1
                subscription.last_success_at = datetime.now(timezone.utc)
                subscription.failure_count = 0
            elif result.gone:
                await db.delete(subscription)
            else:
                subscription.failure_count += 1
    await db.commit()
    return PushTestResponse(
        delivered=delivered,
        devices=await _device_count(db, user_id, access.workspace.id),
    )


async def _goal_response(
    db: DbSession,
    user_id: uuid.UUID,
    goal: DailyViewsGoal | None,
    *,
    full_name: str | None = None,
    role: str | None = None,
) -> DailyViewsGoalResponse:
    if goal is None:
        return DailyViewsGoalResponse(
            user_id=user_id,
            full_name=full_name,
            role=role,
            configured=False,
            target_views=None,
            enabled=False,
            timezone=DEFAULT_TIME_ZONE,
            progress_date=None,
            progress_views=None,
            progress_accounts=None,
            progress_checked_at=None,
            progress_error=None,
            notified_today=False,
        )
    today, _start, _end = local_day_window(datetime.now(timezone.utc), resolve_time_zone(goal.timezone))
    notified = await db.scalar(
        select(DailyViewsGoalNotification.id).where(
            DailyViewsGoalNotification.goal_id == goal.id,
            DailyViewsGoalNotification.local_date == today,
            DailyViewsGoalNotification.target_views == goal.target_views,
        )
    )
    is_today = goal.progress_date == today
    checked_at = goal.progress_checked_at
    if checked_at is not None and checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return DailyViewsGoalResponse(
        user_id=user_id,
        full_name=full_name,
        role=role,
        configured=True,
        target_views=goal.target_views,
        enabled=goal.enabled,
        timezone=goal.timezone,
        # Yesterday's cached number is not today's progress.
        progress_date=today,
        progress_views=goal.progress_views if is_today else None,
        progress_accounts=goal.progress_accounts if is_today else None,
        progress_checked_at=checked_at if is_today else None,
        progress_error=goal.progress_error if is_today else None,
        notified_today=notified is not None,
    )


async def _goal_for(db: DbSession, workspace_id: uuid.UUID, user_id: uuid.UUID) -> DailyViewsGoal | None:
    return await db.scalar(
        select(DailyViewsGoal).where(
            DailyViewsGoal.workspace_id == workspace_id,
            DailyViewsGoal.user_id == user_id,
        )
    )


async def _save_goal(
    db: DbSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: DailyViewsGoalUpdate,
    updated_by: uuid.UUID,
) -> DailyViewsGoal:
    if not is_valid_time_zone(payload.timezone):
        raise HTTPException(status_code=422, detail="Fuso horário inválido.")
    goal = await _goal_for(db, workspace_id, user_id)
    if goal is None:
        goal = DailyViewsGoal(workspace_id=workspace_id, user_id=user_id, target_views=payload.target_views)
        db.add(goal)
    goal.target_views = payload.target_views
    goal.enabled = payload.enabled
    if goal.timezone != payload.timezone:
        goal.progress_date = None
        goal.progress_views = None
    goal.timezone = payload.timezone
    goal.updated_by_user_id = updated_by
    await db.commit()
    return goal


@router.get("/goals/me", response_model=DailyViewsGoalResponse)
async def get_my_goal(access: WorkspaceMemberAccess, db: DbSession) -> DailyViewsGoalResponse:
    user_id = access.membership.user_id
    return await _goal_response(db, user_id, await _goal_for(db, access.workspace.id, user_id))


@router.put(
    "/goals/me",
    response_model=DailyViewsGoalResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_my_goal(
    payload: DailyViewsGoalUpdate,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> DailyViewsGoalResponse:
    user_id = access.membership.user_id
    goal = await _save_goal(db, access.workspace.id, user_id, payload, user_id)
    return await _goal_response(db, user_id, goal)


@router.post(
    "/goals/me/refresh",
    response_model=DailyViewsGoalResponse,
    dependencies=[Depends(require_csrf)],
)
async def refresh_my_goal(access: WorkspaceMemberAccess, db: DbSession) -> DailyViewsGoalResponse:
    """Measure today's views now (at most once a minute per user)."""
    user_id = access.membership.user_id
    goal = await _goal_for(db, access.workspace.id, user_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Configure uma meta primeiro.")
    lock = _refresh_locks.setdefault(goal.id, asyncio.Lock())
    async with lock:
        now = datetime.now(timezone.utc)
        checked_at = goal.progress_checked_at
        if checked_at is not None and checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        if checked_at is None or (now - checked_at).total_seconds() >= _REFRESH_COOLDOWN_SECONDS:
            await measure_goal_progress(db, goal, now, {})
            await db.commit()
    return await _goal_response(db, user_id, goal)


@router.get("/goals", response_model=DailyViewsGoalsResponse)
async def list_member_goals(access: OwnerAccess, db: DbSession) -> DailyViewsGoalsResponse:
    rows = (
        await db.execute(
            select(User.id, User.full_name, WorkspaceMember.role, DailyViewsGoal)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .outerjoin(
                DailyViewsGoal,
                (DailyViewsGoal.user_id == User.id)
                & (DailyViewsGoal.workspace_id == access.workspace.id),
            )
            .where(
                WorkspaceMember.workspace_id == access.workspace.id,
                WorkspaceMember.status == "ACTIVE",
            )
            .order_by(WorkspaceMember.role.desc(), User.full_name, User.id)
        )
    ).all()
    return DailyViewsGoalsResponse(
        goals=[
            await _goal_response(db, user_id, goal, full_name=full_name, role=role)
            for user_id, full_name, role, goal in rows
        ]
    )


@router.put(
    "/goals/{user_id}",
    response_model=DailyViewsGoalResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_member_goal(
    user_id: uuid.UUID,
    payload: DailyViewsGoalUpdate,
    access: OwnerAccess,
    db: DbSession,
) -> DailyViewsGoalResponse:
    member = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == access.workspace.id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.status == "ACTIVE",
        )
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Membro não encontrado neste workspace.")
    goal = await _save_goal(db, access.workspace.id, user_id, payload, access.membership.user_id)
    return await _goal_response(db, user_id, goal, role=member.role)


@router.get("/engagement/me")
async def my_engagement(access: WorkspaceMemberAccess, db: DbSession) -> dict:
    """Streak and personal record for the dashboard (real connection data)."""
    from app.notifications.engagement import user_stats

    stats = await user_stats(db, access.workspace.id, access.membership.user_id, datetime.now(timezone.utc))
    return {
        "today": stats.today,
        "goal": stats.goal,
        "streak": stats.streak,
        "streak_before_today": stats.streak_before_today,
        "met_today": stats.met_today,
        "missing_today": stats.missing_today,
        "best_previous": stats.best_previous,
        "best_previous_date": stats.best_previous_date.isoformat() if stats.best_previous_date else None,
        "is_record_today": stats.is_record_today,
    }
