from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

INSTAGRAM_AUTHORIZATION_ENDPOINT = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN_ENDPOINT = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_GRAPH_ENDPOINT = "https://graph.instagram.com/v25.0"
INSTAGRAM_TOKEN_REFRESH_ENDPOINT = "https://graph.instagram.com/refresh_access_token"
INSTAGRAM_BASIC_PERMISSION = "instagram_business_basic"
INSTAGRAM_PUBLISH_PERMISSION = "instagram_business_content_publish"
INSTAGRAM_INSIGHTS_PERMISSION = "instagram_business_manage_insights"


class InstagramOAuthError(ValueError):
    pass


async def fetch_meta_app_info(
    app_id: str,
    app_secret: str,
) -> tuple[str, str | None, str | None]:
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"https://graph.facebook.com/v25.0/{app_id}",
            params={
                "fields": "id,name,category,link",
                "access_token": f"{app_id}|{app_secret}",
            },
        )
        response.raise_for_status()
        payload = _object(response.json(), "Meta returned an invalid app response.")

    returned_id = payload.get("id")
    name = payload.get("name")
    category = payload.get("category")
    link = payload.get("link")
    if str(returned_id) != app_id or not isinstance(name, str) or not name.strip():
        raise InstagramOAuthError("Meta did not return a valid app name for this App ID.")
    return (
        name.strip()[:160],
        category.strip()[:120] if isinstance(category, str) and category.strip() else None,
        link.strip()[:2048] if isinstance(link, str) and link.strip() else None,
    )


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
        if isinstance(permissions, str):
            granted_permissions = set(permissions.split(","))
        elif isinstance(permissions, list) and all(
            isinstance(permission, str) for permission in permissions
        ):
            granted_permissions = set(permissions)
        else:
            granted_permissions = set()
        if (
            not isinstance(short_token, str)
            or not short_token
            or not {
                INSTAGRAM_BASIC_PERMISSION,
                INSTAGRAM_PUBLISH_PERMISSION,
            }.issubset(granted_permissions)
        ):
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


async def fetch_instagram_views(
    instagram_user_id: str,
    access_token: str,
    since: datetime,
    until: datetime,
) -> int:
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{INSTAGRAM_GRAPH_ENDPOINT}/{instagram_user_id}/insights",
            params={
                "metric": "views",
                "period": "day",
                "since": int(since.timestamp()),
                "until": int(until.timestamp()),
                "access_token": access_token,
            },
        )
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            error = payload.get("error") if isinstance(payload, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            if code in {10, 200} or (
                isinstance(message, str)
                and INSTAGRAM_INSIGHTS_PERMISSION in message
            ):
                raise InstagramInsightsPermissionError from None
            response.raise_for_status()
        payload = _object(response.json(), "Meta returned an invalid Insights response.")

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
    values = metric.get("values") if isinstance(metric, dict) else None
    if not isinstance(values, list):
        raise InstagramOAuthError("Meta did not return the requested views metric.")
    total = 0
    for item in values:
        value = item.get("value") if isinstance(item, dict) else None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            total += value
    total_value = metric.get("total_value") if isinstance(metric, dict) else None
    direct_value = total_value.get("value") if isinstance(total_value, dict) else None
    if isinstance(direct_value, int) and not isinstance(direct_value, bool) and direct_value >= 0:
        total = direct_value
    return total


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
