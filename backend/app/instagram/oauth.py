import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.time import BRAZIL_TIME_ZONE

INSTAGRAM_AUTHORIZATION_ENDPOINT = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN_ENDPOINT = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_GRAPH_ENDPOINT = "https://graph.instagram.com/v25.0"
INSTAGRAM_TOKEN_REFRESH_ENDPOINT = "https://graph.instagram.com/refresh_access_token"
INSTAGRAM_BASIC_PERMISSION = "instagram_business_basic"
INSTAGRAM_PUBLISH_PERMISSION = "instagram_business_content_publish"
INSTAGRAM_INSIGHTS_PERMISSION = "instagram_business_manage_insights"


class InstagramOAuthError(ValueError):
    pass


def build_authorization_url(
    app_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    parameters = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ",".join(
            (
                INSTAGRAM_BASIC_PERMISSION,
                INSTAGRAM_PUBLISH_PERMISSION,
                INSTAGRAM_INSIGHTS_PERMISSION,
            )
        ),
        "state": state,
        "enable_fb_login": "false",
    }
    return f"{INSTAGRAM_AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}"


def _object(payload: object, message: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise InstagramOAuthError(message)
    return payload


def _token_data(payload: object) -> dict[str, object]:
    body = _object(payload, "Meta returned an invalid token response.")
    data = body.get("data")
    if isinstance(data, list) and data:
        return _object(data[0], "Meta returned an invalid token response.")
    return body


def _profile_data(payload: object) -> dict[str, object]:
    body = _object(payload, "Meta returned an invalid profile response.")
    data = body.get("data")
    if isinstance(data, list) and data:
        return _object(data[0], "Meta returned an invalid profile response.")
    return body


async def exchange_instagram_authorization_code(
    code: str,
    redirect_uri: str,
    app_id: str,
    app_secret: str,
) -> tuple[str, str, str | None, int | None, int | None, str, datetime]:
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        short_lived_response = await client.post(
            INSTAGRAM_TOKEN_ENDPOINT,
            data={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        short_lived_response.raise_for_status()
        short_lived = _token_data(short_lived_response.json())
        short_token = short_lived.get("access_token")
        permissions = short_lived.get("permissions")
        if not isinstance(short_token, str) or not short_token:
            raise InstagramOAuthError("Meta did not return an Instagram access token.")
        if permissions is not None:
            if isinstance(permissions, str):
                granted_permissions = set(permissions.split(","))
            elif isinstance(permissions, list) and all(
                isinstance(permission, str) for permission in permissions
            ):
                granted_permissions = set(permissions)
            else:
                granted_permissions = set()
            if not {
                INSTAGRAM_BASIC_PERMISSION,
                INSTAGRAM_PUBLISH_PERMISSION,
            }.issubset(granted_permissions):
                raise InstagramOAuthError(
                    "The Instagram basic and content publishing permissions are required."
                )

        long_lived_response = await client.get(
            f"{INSTAGRAM_GRAPH_ENDPOINT}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": app_secret,
                "access_token": short_token,
            },
        )
        long_lived_response.raise_for_status()
        long_lived = _object(
            long_lived_response.json(),
            "Meta returned an invalid long-lived token response.",
        )
        access_token = long_lived.get("access_token")
        expires_in = long_lived.get("expires_in")
        if (
            not isinstance(access_token, str)
            or not access_token
            or isinstance(expires_in, bool)
            or not isinstance(expires_in, int)
            or expires_in <= 0
        ):
            raise InstagramOAuthError("Meta returned an invalid long-lived token.")

        profile_response = await client.get(
            f"{INSTAGRAM_GRAPH_ENDPOINT}/me",
            params={
                "fields": (
                    "user_id,username,profile_picture_url,followers_count,media_count"
                ),
                "access_token": access_token,
            },
        )
        profile_response.raise_for_status()
        profile = _profile_data(profile_response.json())
        instagram_user_id = profile.get("user_id")
        username = profile.get("username")
        profile_picture_url = profile.get("profile_picture_url")
        follower_count = profile.get("followers_count")
        media_count = profile.get("media_count")
        if (
            not isinstance(instagram_user_id, (str, int))
            or not str(instagram_user_id)
            or not isinstance(username, str)
            or not username.strip()
            or len(username) > 100
        ):
            raise InstagramOAuthError("Meta returned an invalid Instagram profile.")
        if (
            not isinstance(profile_picture_url, str)
            or not profile_picture_url.startswith("https://")
            or len(profile_picture_url) > 2048
        ):
            profile_picture_url = None
        if (
            isinstance(follower_count, bool)
            or not isinstance(follower_count, int)
            or follower_count < 0
        ):
            follower_count = None
        if (
            isinstance(media_count, bool)
            or not isinstance(media_count, int)
            or media_count < 0
        ):
            media_count = None

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return (
        str(instagram_user_id),
        username.strip(),
        profile_picture_url,
        follower_count,
        media_count,
        access_token,
        expires_at,
    )


async def refresh_instagram_long_lived_token(
    access_token: str,
) -> tuple[str, datetime]:
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            INSTAGRAM_TOKEN_REFRESH_ENDPOINT,
            params={
                "grant_type": "ig_refresh_token",
                "access_token": access_token,
            },
        )
        response.raise_for_status()
        payload = _object(
            response.json(),
            "Meta returned an invalid refreshed token response.",
        )

    refreshed_token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    if (
        not isinstance(refreshed_token, str)
        or not refreshed_token
        or isinstance(expires_in, bool)
        or not isinstance(expires_in, int)
        or expires_in <= 0
    ):
        raise InstagramOAuthError("Meta returned an invalid refreshed token.")
    return (
        refreshed_token,
        datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


async def fetch_instagram_profile_metrics(
    access_token: str,
) -> tuple[int | None, int | None, int | None]:
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{INSTAGRAM_GRAPH_ENDPOINT}/me",
            params={
                "fields": "user_id,followers_count,follows_count,media_count",
                "access_token": access_token,
            },
        )
        response.raise_for_status()
        profile = _object(
            response.json(),
            "Meta returned an invalid Instagram profile metrics response.",
        )

    followers_count = profile.get("followers_count")
    follows_count = profile.get("follows_count")
    media_count = profile.get("media_count")
    return (
        followers_count
        if isinstance(followers_count, int)
        and not isinstance(followers_count, bool)
        and followers_count >= 0
        else None,
        follows_count
        if isinstance(follows_count, int)
        and not isinstance(follows_count, bool)
        and follows_count >= 0
        else None,
        media_count
        if isinstance(media_count, int)
        and not isinstance(media_count, bool)
        and media_count >= 0
        else None,
    )


def instagram_api_error_detail(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        try:
            payload = error.response.json()
        except ValueError:
            payload = None
        meta_error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(meta_error, dict):
            code = meta_error.get("code")
            subcode = meta_error.get("error_subcode")
            message = next(
                (
                    meta_error[key].strip()
                    for key in ("error_user_msg", "error_user_title", "message")
                    if isinstance(meta_error.get(key), str)
                    and meta_error[key].strip()
                ),
                None,
            )
            details = [f"HTTP {error.response.status_code}"]
            if isinstance(code, int) and not isinstance(code, bool):
                details.append(f"Meta {code}")
            if isinstance(subcode, int) and not isinstance(subcode, bool):
                details.append(f"subcódigo {subcode}")
            if message:
                details.append(message[:350])
            return " · ".join(details)
        return f"Meta retornou HTTP {error.response.status_code}."
    if isinstance(error, InstagramInsightsPermissionError):
        return f"Permissão ausente: {INSTAGRAM_INSIGHTS_PERMISSION}."
    message = str(error).strip()
    return message[:500] if message else type(error).__name__


def _raise_for_insights_response(response: httpx.Response) -> None:
    if not response.is_error:
        return
    try:
        payload = response.json()
    except ValueError:
        payload = None
    error = payload.get("error") if isinstance(payload, dict) else None
    error_text = (
        " ".join(
            error[field]
            for field in ("message", "error_user_title", "error_user_msg")
            if isinstance(error.get(field), str)
        )
        if isinstance(error, dict)
        else ""
    )
    if INSTAGRAM_INSIGHTS_PERMISSION in error_text:
        raise InstagramInsightsPermissionError from None
    response.raise_for_status()


async def fetch_instagram_views(
    instagram_user_id: str,
    access_token: str,
    since: datetime,
    until: datetime,
) -> int:
    timeout = httpx.Timeout(15.0)
    start_timestamp = int(since.astimezone(timezone.utc).timestamp())
    end_timestamp = int(
        (until - timedelta(seconds=1)).astimezone(timezone.utc).timestamp()
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{INSTAGRAM_GRAPH_ENDPOINT}/{instagram_user_id}/insights",
            params={
                "metric": "views",
                "period": "day",
                "metric_type": "total_value",
                "since": str(start_timestamp),
                "until": str(end_timestamp),
                "access_token": access_token,
            },
        )
        _raise_for_insights_response(response)

        payload = _object(
            response.json(),
            "Meta returned an invalid Insights response.",
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise InstagramOAuthError("Meta returned an invalid Insights response.")
        metric = next(
            (
                item
                for item in data
                if isinstance(item, dict) and item.get("name") == "views"
            ),
            None,
        )
        total_value = metric.get("total_value") if isinstance(metric, dict) else None
        direct_value = total_value.get("value") if isinstance(total_value, dict) else None
        if isinstance(direct_value, int) and not isinstance(direct_value, bool) and direct_value >= 0:
            return direct_value
        raise InstagramOAuthError("Meta did not return a numeric views total.")


async def fetch_instagram_media_views(
    instagram_user_id: str,
    access_token: str,
    since: datetime,
    until: datetime,
) -> tuple[int, int, list[str]]:
    start = since.astimezone(timezone.utc)
    end = until.astimezone(timezone.utc)
    video_ids: list[str] = []
    seen_video_ids: set[str] = set()
    cursor: str | None = None
    seen_cursors: set[str] = set()
    timeout = httpx.Timeout(15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            params = {
                "fields": "id,media_type,timestamp",
                "limit": "100",
                "access_token": access_token,
            }
            if cursor:
                params["after"] = cursor
            response = await client.get(
                f"{INSTAGRAM_GRAPH_ENDPOINT}/{instagram_user_id}/media",
                params=params,
            )
            _raise_for_insights_response(response)
            payload = _object(response.json(), "Meta returned an invalid media response.")
            data = payload.get("data")
            if not isinstance(data, list):
                raise InstagramOAuthError("Meta returned an invalid media list.")

            oldest_timestamp: datetime | None = None
            for item in data:
                if not isinstance(item, dict):
                    raise InstagramOAuthError("Meta returned an invalid media record.")
                media_id = item.get("id")
                media_type = item.get("media_type")
                raw_timestamp = item.get("timestamp")
                if not isinstance(raw_timestamp, str):
                    continue
                try:
                    timestamp = datetime.fromisoformat(
                        raw_timestamp.replace("Z", "+00:00")
                    )
                except ValueError:
                    raise InstagramOAuthError(
                        "Meta returned an invalid video timestamp."
                    ) from None
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                timestamp = timestamp.astimezone(timezone.utc)
                oldest_timestamp = (
                    timestamp
                    if oldest_timestamp is None
                    else min(oldest_timestamp, timestamp)
                )
                if media_type != "VIDEO" or not (start <= timestamp < end):
                    continue
                if not isinstance(media_id, str):
                    raise InstagramOAuthError("Meta returned incomplete video metadata.")
                if media_id not in seen_video_ids:
                    video_ids.append(media_id)
                    seen_video_ids.add(media_id)

            paging = payload.get("paging")
            cursors = paging.get("cursors") if isinstance(paging, dict) else None
            next_cursor = cursors.get("after") if isinstance(cursors, dict) else None
            if (
                not data
                or (oldest_timestamp is not None and oldest_timestamp < start)
                or not isinstance(next_cursor, str)
                or not next_cursor
                or next_cursor in seen_cursors
            ):
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        semaphore = asyncio.Semaphore(5)

        async def media_views(media_id: str) -> tuple[int | None, str | None]:
            async with semaphore:
                try:
                    media_response = await client.get(
                        f"{INSTAGRAM_GRAPH_ENDPOINT}/{media_id}/insights",
                        params={
                            "metric": "views",
                            "access_token": access_token,
                        },
                    )
                    _raise_for_insights_response(media_response)
                    media_payload = _object(
                        media_response.json(),
                        "Meta returned an invalid media Insights response.",
                    )
                    metrics = media_payload.get("data")
                    if not isinstance(metrics, list):
                        raise InstagramOAuthError(
                            "Meta returned an invalid media views metric."
                        )
                    metric = next(
                        (
                            value
                            for value in metrics
                            if isinstance(value, dict) and value.get("name") == "views"
                        ),
                        None,
                    )
                    if not isinstance(metric, dict):
                        raise InstagramOAuthError(
                            "Meta did not return a views metric for this video."
                        )
                    total_value = metric.get("total_value")
                    raw_value = (
                        total_value.get("value")
                        if isinstance(total_value, dict)
                        else metric.get("value")
                    )
                    if raw_value is None:
                        values = metric.get("values")
                        raw_value = (
                            values[0].get("value")
                            if isinstance(values, list)
                            and values
                            and isinstance(values[0], dict)
                            else None
                        )
                    if (
                        isinstance(raw_value, int)
                        and not isinstance(raw_value, bool)
                        and raw_value >= 0
                    ):
                        return raw_value, None
                    raise InstagramOAuthError(
                        "Meta did not return a numeric views total for this video."
                    )
                except (
                    httpx.HTTPError,
                    InstagramOAuthError,
                    RuntimeError,
                    ValueError,
                ) as exc:
                    return None, instagram_api_error_detail(exc)

        results = await asyncio.gather(*(media_views(media_id) for media_id in video_ids))
    successful_values = [
        value for value, error in results if error is None and value is not None
    ]
    errors = [error for _value, error in results if error is not None]
    return (
        sum(successful_values),
        len(video_ids),
        errors,
    )


async def fetch_instagram_account_insights(
    instagram_user_id: str,
    access_token: str,
    since: datetime,
    until: datetime,
) -> tuple[dict[str, int | None], dict[str, str]]:
    supported_metric_names = (
        "reach",
        "accounts_engaged",
        "total_interactions",
        "likes",
        "comments",
        "shares",
        "saves",
        "profile_links_taps",
        "replies",
        "reposts",
    )
    unsupported_metrics = {
        "impressions": "A Meta descontinuou esta métrica; use Visualizações.",
        "profile_views": "A Meta não oferece esta métrica neste endpoint.",
        "website_clicks": "A Meta não oferece esta métrica neste endpoint.",
    }
    start_timestamp = int(since.astimezone(timezone.utc).timestamp())
    end_timestamp = int(
        (until - timedelta(seconds=1)).astimezone(timezone.utc).timestamp()
    )
    metrics: dict[str, int | None] = {
        **{metric_name: None for metric_name in supported_metric_names},
        "views": None,
        **{metric_name: None for metric_name in unsupported_metrics},
    }
    errors: dict[str, str] = dict(unsupported_metrics)
    permission_missing = False
    semaphore = asyncio.Semaphore(4)
    timeout = httpx.Timeout(15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async def fetch_metric(
            metric_name: str,
        ) -> tuple[str, int | None, str | None, bool]:
            async with semaphore:
                try:
                    response = await client.get(
                        f"{INSTAGRAM_GRAPH_ENDPOINT}/{instagram_user_id}/insights",
                        params={
                            "metric": metric_name,
                            "period": "day",
                            "metric_type": "total_value",
                            "since": str(start_timestamp),
                            "until": str(end_timestamp),
                            "access_token": access_token,
                        },
                    )
                    response.raise_for_status()
                    payload = _object(
                        response.json(),
                        "Meta returned an invalid Instagram Insights response.",
                    )
                    data = payload.get("data")
                    metric = next(
                        (
                            item
                            for item in data
                            if isinstance(item, dict)
                            and item.get("name") == metric_name
                        ),
                        None,
                    ) if isinstance(data, list) else None
                    if metric is None:
                        return (
                            metric_name,
                            None,
                            "A Meta não retornou esta métrica para o período.",
                            False,
                        )

                    total_value = metric.get("total_value")
                    direct_value = (
                        total_value.get("value")
                        if isinstance(total_value, dict)
                        else None
                    )
                    if (
                        isinstance(direct_value, int)
                        and not isinstance(direct_value, bool)
                        and direct_value >= 0
                    ):
                        return metric_name, direct_value, None, False

                    values = metric.get("values")
                    if not isinstance(values, list):
                        return (
                            metric_name,
                            None,
                            "A Meta não retornou valores para esta métrica.",
                            False,
                        )
                    total = 0
                    found_value = False
                    for item in values:
                        value = item.get("value") if isinstance(item, dict) else None
                        if (
                            isinstance(value, int)
                            and not isinstance(value, bool)
                            and value >= 0
                        ):
                            total += value
                            found_value = True
                    if not found_value:
                        return (
                            metric_name,
                            None,
                            "A Meta não retornou valores numéricos para esta métrica.",
                            False,
                        )
                    return metric_name, total, None, False
                except httpx.HTTPError as exc:
                    detail = instagram_api_error_detail(exc)
                    permission_error = INSTAGRAM_INSIGHTS_PERMISSION in detail
                    if isinstance(exc, httpx.HTTPStatusError):
                        try:
                            payload = exc.response.json()
                        except ValueError:
                            payload = None
                        meta_error = (
                            payload.get("error")
                            if isinstance(payload, dict)
                            else None
                        )
                        code = (
                            meta_error.get("code")
                            if isinstance(meta_error, dict)
                            else None
                        )
                        message = (
                            meta_error.get("message")
                            if isinstance(meta_error, dict)
                            else None
                        )
                        permission_error = permission_error or (
                            code in {10, 200}
                            and isinstance(message, str)
                            and "permission" in message.casefold()
                        )
                    return metric_name, None, detail, permission_error
                except (InstagramOAuthError, ValueError) as exc:
                    return metric_name, None, instagram_api_error_detail(exc), False

        results = await asyncio.gather(
            *(fetch_metric(metric_name) for metric_name in supported_metric_names)
        )

    for metric_name, value, error, missing_permission in results:
        metrics[metric_name] = value
        permission_missing = permission_missing or missing_permission
        if error:
            errors[metric_name] = error
    if permission_missing:
        raise InstagramInsightsPermissionError
    return metrics, errors


class InstagramInsightsPermissionError(InstagramOAuthError):
    def __init__(self) -> None:
        super().__init__(
            f"Missing Meta permission: {INSTAGRAM_INSIGHTS_PERMISSION}."
        )


async def revoke_instagram_permissions(access_token: str) -> bool:
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.delete(
            f"{INSTAGRAM_GRAPH_ENDPOINT}/me/permissions",
            params={"access_token": access_token},
        )
        response.raise_for_status()
        payload = response.json()
    return isinstance(payload, dict) and payload.get("success") is True
