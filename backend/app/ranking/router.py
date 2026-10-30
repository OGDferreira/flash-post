"""Platform rankings: who had the most Instagram views (everyone sees it) and who billed the
most (Super Admin only). Each user is ranked by their own operation (the workspace they own)."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, SuperAdminUser, WorkspaceMemberAccess
from app.core.time import local_date, utc_now
from app.models import InstagramAccountDailyViews, TgOrder, User, Workspace
from app.models.sharkbot import SharkTransaction

router = APIRouter(prefix="/api/rankings", tags=["Rankings"])


async def _users(db: AsyncSession, owner_ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not owner_ids:
        return {}
    rows = await db.scalars(select(User).where(User.id.in_(owner_ids)))
    return {user.id: user for user in rows}


def _entry(user: User, position: int, **values) -> dict:
    return {
        "position": position,
        "user_id": str(user.id),
        "full_name": user.full_name,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        **values,
    }


@router.get("/views")
async def views_ranking(
    _access: WorkspaceMemberAccess,
    db: DbSession,
    period: AnalyticsPeriod = "today",
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Users with the most views in the period (Meta's daily views of their accounts)."""
    start, end = period_bounds(period, start_date, end_date, utc_now())
    total = func.sum(InstagramAccountDailyViews.views)
    query = (
        select(Workspace.owner_id, total)
        .join(Workspace, Workspace.id == InstagramAccountDailyViews.workspace_id)
        .group_by(Workspace.owner_id)
        .having(total > 0)
        .order_by(total.desc())
        .limit(limit)
    )
    if start is not None:
        query = query.where(InstagramAccountDailyViews.day >= local_date(start))
    if end is not None:
        query = query.where(InstagramAccountDailyViews.day < local_date(end))
    rows = (await db.execute(query)).all()
    users = await _users(db, [owner for owner, _views in rows])
    ranking, position = [], 0
    for owner, views in rows:
        user = users.get(owner)
        if user is None:
            continue
        position += 1
        ranking.append(_entry(user, position, views=int(views or 0)))
    return {"period_label": period_label(start, end), "ranking": ranking}


@router.get("/revenue")
async def revenue_ranking(
    _admin: SuperAdminUser,
    db: DbSession,
    period: AnalyticsPeriod = "today",
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Users who billed the most in the period (Flash Bot + SharkBot paid sales, gross)."""
    start, end = period_bounds(period, start_date, end_date, utc_now())
    by_workspace: dict[uuid.UUID, list[Decimal | int]] = {}

    flash = select(TgOrder.workspace_id, func.sum(TgOrder.amount), func.count(TgOrder.id)).where(TgOrder.status == "paid")
    shark = select(SharkTransaction.workspace_id, func.sum(SharkTransaction.amount), func.count(SharkTransaction.id)).where(
        SharkTransaction.status == "paid", SharkTransaction.amount.is_not(None)
    )
    if start is not None:
        flash = flash.where(TgOrder.paid_at >= start)
        shark = shark.where(SharkTransaction.paid_at >= start)
    if end is not None:
        flash = flash.where(TgOrder.paid_at < end)
        shark = shark.where(SharkTransaction.paid_at < end)
    for query, column in ((flash, TgOrder.workspace_id), (shark, SharkTransaction.workspace_id)):
        for workspace_id, amount, sales in (await db.execute(query.group_by(column))).all():
            entry = by_workspace.setdefault(workspace_id, [Decimal("0.00"), 0])
            entry[0] += Decimal(amount or 0)
            entry[1] += int(sales or 0)

    owners = dict((await db.execute(select(Workspace.id, Workspace.owner_id).where(Workspace.id.in_(list(by_workspace))))).all()) if by_workspace else {}
    by_owner: dict[uuid.UUID, list[Decimal | int]] = {}
    for workspace_id, (amount, sales) in by_workspace.items():
        owner = owners.get(workspace_id)
        if owner is None:
            continue
        entry = by_owner.setdefault(owner, [Decimal("0.00"), 0])
        entry[0] += amount
        entry[1] += sales
    ordered = sorted(((o, v) for o, v in by_owner.items() if v[0] > 0), key=lambda item: item[1][0], reverse=True)[:limit]
    users = await _users(db, [owner for owner, _ in ordered])
    ranking, position = [], 0
    for owner, (amount, sales) in ordered:
        user = users.get(owner)
        if user is None:
            continue
        position += 1
        ranking.append(_entry(user, position, revenue=float(Decimal(amount).quantize(Decimal("0.01"))), sales=int(sales)))
    return {"period_label": period_label(start, end), "ranking": ranking}
