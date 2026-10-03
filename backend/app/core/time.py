from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BRAZIL_TIME_ZONE = ZoneInfo("America/Sao_Paulo")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_date(value: datetime) -> date:
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(BRAZIL_TIME_ZONE).date()


def local_day_bounds_utc(value: datetime) -> tuple[datetime, datetime]:
    day = local_date(value)
    start = datetime.combine(day, time.min, tzinfo=BRAZIL_TIME_ZONE)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=BRAZIL_TIME_ZONE)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
