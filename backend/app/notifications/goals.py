"""Daily views goals: progress from Meta Insights and one push per goal/day."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.core.security import WorkspaceRole
from app.instagram.oauth import (
    InstagramInsightsPermissionError,
    InstagramOAuthError,
    fetch_instagram_views,
    instagram_api_error_detail,
)
from app.models import (
    DailyViewsGoal,
    DailyViewsGoalNotification,
    InstagramAccount,
    PushSubscription,
    WorkspaceMember,
)
from app.notifications.webpush import VapidKeys, WebPushError, get_vapid_keys, send_web_push

logger = logging.getLogger(__name__)
DEFAULT_TIME_ZONE = "America/Sao_Paulo"
_ACCOUNT_CONCURRENCY = 5


def resolve_time_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIME_ZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIME_ZONE)


def is_valid_time_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def local_day_window(now: datetime, zone: ZoneInfo) -> tuple[date, datetime, datetime]:
    """Local calendar day for ``now`` in ``zone`` and its UTC start/end."""
    local_now = now.astimezone(zone)
    day = local_now.date()
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    return day, start, end


def format_views(value: int) -> str:
    return f"{value:,}".replace(",", ".")


async def goal_scope_accounts(
    db: AsyncSession, goal: DailyViewsGoal, now: datetime
) -> list[InstagramAccount] | None:
    """Accounts whose views count toward the goal; None if the member is inactive.

    Owners are measured on every active account of the workspace; collaborators
    only on the accounts they connected.
    """
    membership = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == goal.workspace_id,
            WorkspaceMember.user_id == goal.user_id,
            WorkspaceMember.status == "ACTIVE",
        )
    )
    if membership is None:
        return None
    query = select(InstagramAccount).where(
        InstagramAccount.workspace_id == goal.workspace_id,
        InstagramAccount.status == "connected",
        InstagramAccount.token_expires_at > now,
        InstagramAccount.encrypted_access_token.is_not(None),
    )
    if membership.role != WorkspaceRole.OWNER.value:
        query = query.where(InstagramAccount.connected_by_user_id == goal.user_id)
    return list((await db.scalars(query.order_by(InstagramAccount.id))).all())


async def _account_views_today(
    account: InstagramAccount, since: datetime, until: datetime
) -> tuple[int | None, str | None]:
    try:
        token = decrypt_value(account.encrypted_access_token or "")
    except (RuntimeError, ValueError):
        return None, "token ilegível"
    try:
        return await fetch_instagram_views(account.instagram_user_id, token, since, until), None
    except InstagramInsightsPermissionError:
        return None, "permissão de Insights ausente"
    except (httpx.HTTPError, InstagramOAuthError, RuntimeError, ValueError) as exc:
        return None, instagram_api_error_detail(exc)


async def measure_goal_progress(
    db: AsyncSession,
    goal: DailyViewsGoal,
    now: datetime,
    views_cache: dict[tuple[uuid.UUID, datetime], tuple[int | None, str | None]],
) -> tuple[date, int | None, int, str | None]:
    """Return (local_day, views, accounts_measured, error) and cache it on the goal.

    ``views`` is the sum over accounts that answered. When some accounts fail it
    is a lower bound: reaching the target with it is still a real achievement,
    but the error explains that the number may be incomplete.
    """
    zone = resolve_time_zone(goal.timezone)
    day, start, _end = local_day_window(now, zone)
    accounts = await goal_scope_accounts(db, goal, now)
    if accounts is None:
        return day, None, 0, "Membro inativo neste workspace."
    if not accounts:
        result: tuple[int | None, int, str | None] = (None, 0, "Nenhuma conta ativa para medir.")
    elif now <= start:
        result = (0, len(accounts), None)
    else:
        semaphore = asyncio.Semaphore(_ACCOUNT_CONCURRENCY)

        async def load(account: InstagramAccount) -> tuple[int | None, str | None]:
            key = (account.id, start)
            if key not in views_cache:
                async with semaphore:
                    views_cache[key] = await _account_views_today(account, start, now)
            return views_cache[key]

        outcomes = await asyncio.gather(*(load(account) for account in accounts))
        values = [views for views, _error in outcomes if views is not None]
        failures = [error for views, error in outcomes if views is None]
        if not values:
            first_error = failures[0] if failures else "sem resposta"
            result = (None, len(accounts), f"A Meta não retornou visualizações ({first_error}).")
        else:
            error = (
                f"{len(failures)} de {len(accounts)} contas sem dados; total parcial."
                if failures
                else None
            )
            result = (sum(values), len(accounts), error)
    views, measured, error = result
    goal.progress_date = day
    goal.progress_views = views
    goal.progress_accounts = measured
    goal.progress_error = error[:500] if error else None
    goal.progress_checked_at = now
    return day, views, measured, error


async def notify_goal_reached(
    db: AsyncSession,
    goal: DailyViewsGoal,
    day: date,
    views: int,
    client: httpx.AsyncClient,
    keys: VapidKeys,
) -> int:
    """Send the "goal reached" push once per goal, local day and target.

    The unique row is inserted (and committed) before sending so concurrent
    workers cannot both notify. If no device accepted the message because of a
    transient failure, the row is removed so the next run retries.
    """
    subscriptions = (
        await db.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == goal.user_id,
                PushSubscription.workspace_id == goal.workspace_id,
            )
        )
    ).all()
    if not subscriptions:
        return 0
    marker = DailyViewsGoalNotification(
        goal_id=goal.id,
        workspace_id=goal.workspace_id,
        user_id=goal.user_id,
        local_date=day,
        target_views=goal.target_views,
        views=views,
    )
    try:
        # Savepoint only: a full rollback would expire every loaded object.
        async with db.begin_nested():
            db.add(marker)
            await db.flush()
    except IntegrityError:
        return 0
    await db.commit()

    payload = {
        "title": "Meta diária atingida",
        "body": (
            f"Você alcançou {format_views(views)} visualizações hoje "
            f"(meta: {format_views(goal.target_views)})."
        ),
        "url": "/dashboard",
        "tag": f"views-goal-{day.isoformat()}",
    }
    delivered = 0
    transient_failures = 0
    for subscription in subscriptions:
        result = await send_web_push(
            client,
            endpoint=subscription.endpoint,
            p256dh=subscription.p256dh,
            auth=subscription.auth,
            payload=payload,
            keys=keys,
            topic=f"goal{day.strftime('%Y%m%d')}",
        )
        if result.ok:
            delivered += 1
            subscription.failure_count = 0
            subscription.last_success_at = datetime.now(timezone.utc)
        elif result.gone:
            await db.delete(subscription)
        else:
            transient_failures += 1
            subscription.failure_count += 1
    if delivered == 0 and transient_failures:
        await db.execute(
            delete(DailyViewsGoalNotification).where(DailyViewsGoalNotification.id == marker.id)
        )
    else:
        marker.delivered = delivered
    await db.commit()
    return delivered


async def run_daily_views_goal_tick(db: AsyncSession, now: datetime | None = None) -> int:
    """Check every enabled goal once. Returns how many pushes were delivered."""
    now = now or datetime.now(timezone.utc)
    goal_ids = (
        await db.scalars(
            select(DailyViewsGoal.id)
            .where(DailyViewsGoal.enabled.is_(True))
            .order_by(DailyViewsGoal.id)
        )
    ).all()
    if not goal_ids:
        return 0
    keys: VapidKeys | None = None
    views_cache: dict[tuple[uuid.UUID, datetime], tuple[int | None, str | None]] = {}
    delivered_total = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        for goal_id in goal_ids:
            # Fresh load each time: a rollback below expires loaded instances.
            goal = await db.scalar(
                select(DailyViewsGoal)
                .where(DailyViewsGoal.id == goal_id, DailyViewsGoal.enabled.is_(True))
                .execution_options(populate_existing=True)
            )
            if goal is None:
                continue
            zone = resolve_time_zone(goal.timezone)
            day, _start, _end = local_day_window(now, zone)
            already_notified = await db.scalar(
                select(DailyViewsGoalNotification.id).where(
                    DailyViewsGoalNotification.goal_id == goal.id,
                    DailyViewsGoalNotification.local_date == day,
                    DailyViewsGoalNotification.target_views == goal.target_views,
                )
            )
            try:
                day, views, _measured, _error = await measure_goal_progress(
                    db, goal, now, views_cache
                )
                await db.commit()
            except Exception as exc:  # one bad goal must not stop the others
                await db.rollback()
                logger.warning("Daily views goal %s check failed (%s).", goal.id, type(exc).__name__)
                continue
            if already_notified is not None or views is None or views < goal.target_views:
                continue
            if keys is None:
                try:
                    keys = await get_vapid_keys(db)
                except (WebPushError, RuntimeError, ValueError) as exc:
                    logger.error("Web Push keys unavailable (%s).", type(exc).__name__)
                    return delivered_total
            delivered_total += await notify_goal_reached(db, goal, day, views, client, keys)
    return delivered_total
