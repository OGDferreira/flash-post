from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

INSTAGRAM_AUTHORIZATION_ENDPOINT = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN_ENDPOINT = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_GRAPH_ENDPOINT = "https://graph.instagram.com/v25.0"
INSTAGRAM_BASIC_PERMISSION = "instagram_business_basic"


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
        "scope": INSTAGRAM_BASIC_PERMISSION,
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
) -> tuple[str, str, str, datetime]:
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
        if (
            not isinstance(short_token, str)
            or not short_token
            or not isinstance(permissions, str)
            or INSTAGRAM_BASIC_PERMISSION not in permissions.split(",")
        ):
            raise InstagramOAuthError("The required Instagram permission was not granted.")

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
                "fields": "user_id,username",
                "access_token": access_token,
            },
        )
        profile_response.raise_for_status()
        profile = _profile_data(profile_response.json())
        instagram_user_id = profile.get("user_id")
        username = profile.get("username")
        if (
            not isinstance(instagram_user_id, (str, int))
            or not str(instagram_user_id)
            or not isinstance(username, str)
            or not username.strip()
            or len(username) > 100
        ):
            raise InstagramOAuthError("Meta returned an invalid Instagram profile.")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return str(instagram_user_id), username.strip(), access_token, expires_at


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
