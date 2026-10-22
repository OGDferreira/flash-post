"""Application calendar helpers.

Every "day" in Falcon Post (daily limits, daily metrics, goals) is a calendar day
in the application time zone. It defaults to America/Sao_Paulo and can be set
with the APP_TIME_ZONE environment variable (an IANA name).
"""

import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _configured_time_zone() -> ZoneInfo:
    name = (os.environ.get("APP_TIME_ZONE") or "America/Sao_Paulo").strip()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/Sao_Paulo")


APP_TIME_ZONE = _configured_time_zone()
APP_TIME_ZONE_NAME = APP_TIME_ZONE.key
# Kept for existing imports; it is the configured application time zone.
BRAZIL_TIME_ZONE = APP_TIME_ZONE


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def local_date(value: datetime, zone: ZoneInfo | None = None) -> date:
    return as_utc(value).astimezone(zone or APP_TIME_ZONE).date()


def day_bounds_utc(day: date, zone: ZoneInfo | None = None) -> tuple[datetime, datetime]:
    tz = zone or APP_TIME_ZONE
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def local_day_bounds_utc(value: datetime, zone: ZoneInfo | None = None) -> tuple[datetime, datetime]:
    return day_bounds_utc(local_date(value, zone), zone)


def next_local_midnight_utc(value: datetime, zone: ZoneInfo | None = None) -> datetime:
    return local_day_bounds_utc(value, zone)[1]
