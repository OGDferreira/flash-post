"""Period filter shared by the metrics endpoints (application time zone)."""

from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import HTTPException

from app.core.time import APP_TIME_ZONE, day_bounds_utc, local_date

AnalyticsPeriod = Literal["today", "yesterday", "7d", "30d", "all", "custom"]


def period_bounds(
    period: AnalyticsPeriod,
    start_date: date | None,
    end_date: date | None,
    now: datetime,
) -> tuple[datetime | None, datetime | None]:
    """[start, end) in UTC for whole local days; None means unbounded."""
    today = local_date(now)
    if period == "custom":
        if start_date is None or end_date is None or end_date < start_date:
            raise HTTPException(
                status_code=422,
                detail="Período personalizado inválido. Informe datas inicial e final válidas.",
            )
        if (end_date - start_date).days > 366:
            raise HTTPException(status_code=422, detail="O período máximo é de 1 ano.")
        return day_bounds_utc(start_date)[0], day_bounds_utc(end_date)[1]
    if period == "today":
        return day_bounds_utc(today)
    if period == "yesterday":
        return day_bounds_utc(today - timedelta(days=1))
    if period == "7d":
        return day_bounds_utc(today - timedelta(days=6))[0], day_bounds_utc(today)[1]
    if period == "30d":
        return day_bounds_utc(today - timedelta(days=29))[0], day_bounds_utc(today)[1]
    return None, None


def period_label(start: datetime | None, end: datetime | None) -> str:
    if start is None or end is None:
        return "Todo o histórico"
    first = start.astimezone(APP_TIME_ZONE).date()
    last = (end - timedelta(microseconds=1)).astimezone(APP_TIME_ZONE).date()
    return first.strftime("%d/%m/%Y") if first == last else (
        f"{first.strftime('%d/%m/%Y')} a {last.strftime('%d/%m/%Y')}"
    )
