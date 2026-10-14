"""Sync per-publication Insights from Meta into instagram_media_insights.

Metrics are lifetime totals of each publication, refreshed on every sync
(Meta may update them for days and can lag up to 48 h). The sync covers
publications from the last ``SYNC_LOOKBACK_DAYS`` days, paginating
``/{ig-user}/media`` until older items or ``SYNC_MAX_MEDIA`` is reached.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.instagram.oauth import (
    INSTAGRAM_GRAPH_ENDPOINT,
    INSTAGRAM_INSIGHTS_PERMISSION,
    instagram_api_error_detail,
)
from app.models import InstagramAccount, InstagramMediaInsight

logger = logging.getLogger(__name__)
SYNC_LOOKBACK_DAYS = 45
SYNC_MAX_MEDIA = 80
_MEDIA_CONCURRENCY = 4
# Meta metric name -> column
_METRICS = {
    "views": "views",
    "reach": "reach",
    "likes": "likes",
    "comments": "comments",
    "shares": "shares",
    "saved": "saves",
}


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _metric_values(payload: object) -> dict[str, int | None]:
    values: dict[str, int | None] = {}
    data = payload.get("data") if isinstance(payload, dict) else None
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        total = item.get("total_value")
        raw = total.get("value") if isinstance(total, dict) else None
        if raw is None:
            series = item.get("values")
            if isinstance(series, list) and series and isinstance(series[0], dict):
                raw = series[0].get("value")
        if isinstance(name, str):
            values[name] = _int(raw)
    return values


async def _media_metrics(
    client: httpx.AsyncClient, media_id: str, token: str
) -> tuple[dict[str, int | None], str | None]:
    """All metrics in one call; if Meta rejects the set (a metric unsupported
    for this media type), ask for each metric separately."""
    response = await client.get(
        f"{INSTAGRAM_GRAPH_ENDPOINT}/{media_id}/insights",
        params={"metric": ",".join(_METRICS), "access_token": token},
    )
    if response.status_code == 200:
        return _metric_values(response.json()), None
    if response.status_code in (401, 403):
        return {}, instagram_api_error_detail(httpx.HTTPStatusError("", request=response.request, response=response))
    values: dict[str, int | None] = {}
    errors: list[str] = []
    for metric in _METRICS:
        single = await client.get(
            f"{INSTAGRAM_GRAPH_ENDPOINT}/{media_id}/insights",
            params={"metric": metric, "access_token": token},
        )
        if single.status_code == 200:
            values.update(_metric_values(single.json()))
        else:
            errors.append(metric)
    error = f"Métricas indisponíveis para esta publicação: {', '.join(errors)}." if errors else None
    return values, error


async def sync_account_media_insights(
    db: AsyncSession, account: InstagramAccount, now: datetime | None = None
) -> int:
    """Refresh stored Insights for one account. Returns publications synced."""
    current = now or datetime.now(timezone.utc)
    if account.encrypted_access_token is None:
        account.insights_sync_error = "Conta sem token válido. Reconecte a conta."
        await db.commit()
        return 0
    try:
        token = decrypt_value(account.encrypted_access_token)
    except (RuntimeError, ValueError):
        account.insights_sync_error = "Não foi possível ler o token salvo. Reconecte a conta."
        await db.commit()
        return 0

    cutoff = current - timedelta(days=SYNC_LOOKBACK_DAYS)
    items: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            after: str | None = None
            seen_cursors: set[str] = set()
            while len(items) < SYNC_MAX_MEDIA:
                params = {
                    "fields": "id,media_type,media_product_type,timestamp,permalink,thumbnail_url,"
                              "media_url,caption,like_count,comments_count",
                    "limit": "50",
                    "access_token": token,
                }
                if after:
                    params["after"] = after
                response = await client.get(
                    f"{INSTAGRAM_GRAPH_ENDPOINT}/{account.instagram_user_id}/media", params=params
                )
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, list) or not data:
                    break
                reached_cutoff = False
                for item in data:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                        continue
                    try:
                        posted = datetime.fromisoformat(str(item.get("timestamp")).replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=timezone.utc)
                    if posted < cutoff:
                        reached_cutoff = True
                        continue
                    item["_posted_at"] = posted
                    items.append(item)
                paging = payload.get("paging") if isinstance(payload, dict) else None
                cursors = paging.get("cursors") if isinstance(paging, dict) else None
                next_cursor = cursors.get("after") if isinstance(cursors, dict) else None
                has_next = isinstance(paging, dict) and paging.get("next")
                if reached_cutoff or not has_next or not next_cursor or next_cursor in seen_cursors:
                    break
                seen_cursors.add(next_cursor)
                after = next_cursor

            semaphore = asyncio.Semaphore(_MEDIA_CONCURRENCY)

            async def load(item: dict):
                async with semaphore:
                    try:
                        return item, *await _media_metrics(client, item["id"], token)
                    except httpx.HTTPError as exc:
                        return item, {}, instagram_api_error_detail(exc)

            results = await asyncio.gather(*(load(item) for item in items[:SYNC_MAX_MEDIA]))
    except (httpx.HTTPError, ValueError) as exc:
        detail = instagram_api_error_detail(exc) if isinstance(exc, httpx.HTTPError) else str(exc)
        if INSTAGRAM_INSIGHTS_PERMISSION in detail:
            detail = f"Permissão necessária: {INSTAGRAM_INSIGHTS_PERMISSION}."
        account.insights_sync_error = detail[:500]
        await db.commit()
        logger.warning("Insights sync failed for account %s: %s", account.id, detail)
        return 0

    synced = 0
    for item, metrics, error in results:
        row = await db.scalar(
            select(InstagramMediaInsight).where(
                InstagramMediaInsight.account_id == account.id,
                InstagramMediaInsight.ig_media_id == item["id"],
            )
        )
        if row is None:
            row = InstagramMediaInsight(
                workspace_id=account.workspace_id,
                account_id=account.id,
                ig_media_id=item["id"][:64],
                posted_at=item["_posted_at"],
                synced_at=current,
            )
            db.add(row)
        row.media_type = str(item.get("media_type") or "")[:32] or None
        row.media_product_type = str(item.get("media_product_type") or "")[:32] or None
        row.permalink = str(item.get("permalink") or "")[:500] or None
        thumbnail = item.get("thumbnail_url") or (
            item.get("media_url") if item.get("media_type") == "IMAGE" else None
        )
        row.thumbnail_url = str(thumbnail)[:2048] if thumbnail else None
        caption = item.get("caption")
        row.caption = " ".join(str(caption).split())[:300] if caption else None
        row.posted_at = item["_posted_at"]
        for meta_name, column in _METRICS.items():
            value = metrics.get(meta_name)
            if value is None and meta_name == "likes":
                value = _int(item.get("like_count"))
            if value is None and meta_name == "comments":
                value = _int(item.get("comments_count"))
            setattr(row, column, value)
        row.metrics_error = error[:300] if error else None
        row.synced_at = current
        synced += 1
    account.insights_synced_at = current
    account.insights_sync_error = None
    try:
        await db.commit()
    except IntegrityError:  # concurrent sync of the same account
        await db.rollback()
        return 0
    return synced


async def sync_workspace_accounts(db: AsyncSession, account_ids: list, now: datetime | None = None) -> int:
    total = 0
    for account_id in account_ids:
        account = await db.get(InstagramAccount, account_id)
        if account is None or account.status != "connected":
            continue
        total += await sync_account_media_insights(db, account, now)
        # Imported here to keep this module free of a circular import.
        from app.instagram.daily_views_sync import sync_account_daily_views

        await sync_account_daily_views(db, account, now)
    return total
