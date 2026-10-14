"""Store, per account and local day, the views Meta reports for that day.

This is the "views received on the day" series. It is NOT cumulative and is
not tied to when the videos were published (that is the other series, built
from per-publication Insights). Days older than ``FINAL_AFTER_DAYS`` are read
once and kept; recent days are refreshed on every sync because Meta can lag.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.core.time import day_bounds_utc, local_date
from app.instagram.oauth import (
    InstagramInsightsPermissionError,
    InstagramOAuthError,
    fetch_instagram_views,
    instagram_api_error_detail,
)
from app.models import InstagramAccount, InstagramAccountDailyViews

logger = logging.getLogger(__name__)
LOOKBACK_DAYS = 30
FINAL_AFTER_DAYS = 3
MAX_CALLS_PER_RUN = 31


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def sync_account_daily_views(
    db: AsyncSession, account: InstagramAccount, now: datetime | None = None
) -> int:
    """Returns how many days were (re)written. Failures are recorded, never raised."""
    current = now or datetime.now(timezone.utc)
    if account.encrypted_access_token is None:
        return 0
    try:
        token = decrypt_value(account.encrypted_access_token)
    except (RuntimeError, ValueError):
        return 0
    today = local_date(current)
    first_day = max(local_date(_utc(account.connected_at)), today - timedelta(days=LOOKBACK_DAYS - 1))
    existing = {
        row.day: row
        for row in (
            await db.scalars(
                select(InstagramAccountDailyViews).where(
                    InstagramAccountDailyViews.account_id == account.id,
                    InstagramAccountDailyViews.day >= first_day,
                )
            )
        ).all()
    }
    written = calls = 0
    day: date = first_day
    while day <= today and calls < MAX_CALLS_PER_RUN:
        row = existing.get(day)
        final = row is not None and day < today - timedelta(days=FINAL_AFTER_DAYS)
        if not final:
            start, end = day_bounds_utc(day)
            end = min(end, current)
            if start < end:
                calls += 1
                try:
                    views = await fetch_instagram_views(account.instagram_user_id, token, start, end)
                except InstagramInsightsPermissionError:
                    account.insights_sync_error = instagram_api_error_detail(InstagramInsightsPermissionError())
                    break
                except (httpx.HTTPError, InstagramOAuthError, RuntimeError, ValueError) as exc:
                    account.insights_sync_error = instagram_api_error_detail(exc)[:500]
                    logger.info("Daily views unavailable for account %s on %s.", account.id, day)
                    day += timedelta(days=1)
                    continue
                if row is None:
                    db.add(
                        InstagramAccountDailyViews(
                            workspace_id=account.workspace_id,
                            account_id=account.id,
                            day=day,
                            views=views,
                            fetched_at=current,
                        )
                    )
                else:
                    row.views, row.fetched_at = views, current
                written += 1
        day += timedelta(days=1)
    await db.commit()
    return written
