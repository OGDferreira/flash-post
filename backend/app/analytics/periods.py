"""Period filter shared by the metrics endpoints (application time zone)."""

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import APP_TIME_ZONE, day_bounds_utc, local_date
from app.models import DailyViewsGoal

AnalyticsPeriod = Literal["today", "yesterday", "7d", "30d", "all", "custom"]


def period_bounds(
    period: AnalyticsPeriod,
    start_date: date | None,
    end_date: date | None,
    now: datetime,
    zone: ZoneInfo | None = None,
) -> tuple[datetime | None, datetime | None]:
    """[start, end) in UTC for whole local days; None means unbounded."""
    today = local_date(now, zone)
    if period == "custom":
        if start_date is None or end_date is None or end_date < start_date:
            raise HTTPException(
                status_code=422,
                detail="Período personalizado inválido. Informe datas inicial e final válidas.",
            )
        if (end_date - start_date).days > 366:
            raise HTTPException(status_code=422, detail="O período máximo é de 1 ano.")
        return day_bounds_utc(start_date, zone)[0], day_bounds_utc(end_date, zone)[1]
    if period == "today":
        return day_bounds_utc(today, zone)
    if period == "yesterday":
        return day_bounds_utc(today - timedelta(days=1), zone)
    if period == "7d":
        return day_bounds_utc(today - timedelta(days=6), zone)[0], day_bounds_utc(today, zone)[1]
    if period == "30d":
        return day_bounds_utc(today - timedelta(days=29), zone)[0], day_bounds_utc(today, zone)[1]
    return None, None


def period_label(start: datetime | None, end: datetime | None, zone: ZoneInfo | None = None) -> str:
    if start is None or end is None:
        return "Todo o histórico"
    first = start.astimezone(zone or APP_TIME_ZONE).date()
    last = (end - timedelta(microseconds=1)).astimezone(zone or APP_TIME_ZONE).date()
    return first.strftime("%d/%m/%Y") if first == last else (
        f"{first.strftime('%d/%m/%Y')} a {last.strftime('%d/%m/%Y')}"
    )


async def user_time_zone(db: AsyncSession, workspace_id: UUID, user_id: UUID) -> ZoneInfo:
    """Reuse the user's configured calendar (daily goal); default to São Paulo."""
    name = await db.scalar(select(DailyViewsGoal.timezone).where(
        DailyViewsGoal.workspace_id == workspace_id, DailyViewsGoal.user_id == user_id,
    ))
    try:
        return ZoneInfo(name or "America/Sao_Paulo")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/Sao_Paulo")
