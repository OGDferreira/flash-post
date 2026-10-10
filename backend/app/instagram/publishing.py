import asyncio
import logging
from collections.abc import Mapping

import httpx

from app.instagram.storage import SupabaseStorage
from app.models import InstagramAccount, InstagramMedia

GRAPH_ENDPOINT = "https://graph.instagram.com/v25.0"
VIDEO_PROCESSING_INTERVAL_SECONDS = 5
VIDEO_PROCESSING_MAX_ATTEMPTS = 180
RETRY_DELAYS_SECONDS = (3, 10, 30)
logger = logging.getLogger(__name__)


class InstagramPublishingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        meta_error_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.meta_error_code = meta_error_code


def _meta_error_code(response: httpx.Response) -> int | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error") if isinstance(payload, Mapping) else None
    code = error.get("code") if isinstance(error, Mapping) else None
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def _is_transient_response(response: httpx.Response) -> bool:
    if response.status_code >= 500 or response.status_code == 429:
        return True
    return response.status_code == 400 and _meta_error_code(response) in {1, 2, 4, 17, 100}


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    """Retry transient Meta rejections before giving up on the account."""
    for delay in (*RETRY_DELAYS_SECONDS, None):
        try:
            response = await getattr(client, method.lower())(url, **kwargs)
        except httpx.TransportError:
            if delay is None:
                raise
            await asyncio.sleep(delay)
            continue
        if (
            getattr(response, "status_code", 200) < 400
            or delay is None
            or not _is_transient_response(response)
        ):
            response.raise_for_status()
            return response
        await asyncio.sleep(delay)
    raise InstagramPublishingError("Instagram request retries were exhausted.")


def _instagram_user_identity(payload: object) -> tuple[str, str]:
    profile: object = payload
    if isinstance(payload, Mapping):
        data = payload.get("data")
        if isinstance(data, list) and data:
            profile = data[0]
    if isinstance(profile, Mapping):
        user_id = profile.get("user_id") or profile.get("id")
        username = profile.get("username")
        if (
            isinstance(user_id, (int, str))
            and str(user_id)
            and isinstance(username, str)
            and username.strip()
        ):
            return str(user_id), username.strip()
    raise InstagramPublishingError(
        "Instagram did not return a valid user identity for this access token."
    )


def _publication_error_detail(
    response: httpx.Response,
    stage: str,
    access_token: str,
    signed_url: str,
) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    error = payload.get("error") if isinstance(payload, Mapping) else None
    code = error.get("code") if isinstance(error, Mapping) else None
    subcode = error.get("error_subcode") if isinstance(error, Mapping) else None
    error_type = error.get("type") if isinstance(error, Mapping) else None
    trace_id = payload.get("fbtrace_id") if isinstance(payload, Mapping) else None
    message = error.get("message") if isinstance(error, Mapping) else None

    details = []
    if isinstance(error_type, str) and error_type:
        details.append(error_type[:80])
    if isinstance(code, (str, int)):
        details.append(f"code {code}")
    if isinstance(subcode, (str, int)):
        details.append(f"subcode {subcode}")
    if isinstance(trace_id, str) and trace_id:
        details.append(f"trace {trace_id[:80]}")

    safe_message = message.strip() if isinstance(message, str) else ""
    if access_token:
        safe_message = safe_message.replace(access_token, "[redacted]")
    if signed_url:
        safe_message = safe_message.replace(signed_url, "[media URL]")
    safe_message = " ".join(safe_message.split())

    description = f"Instagram rejected {stage} (HTTP {response.status_code}"
    if details:
        description += f", {', '.join(details)}"
    description += ")."
    if safe_message:
        description += f" {safe_message}"
    return description[:500]


def _response_id(payload: object) -> str:
    if isinstance(payload, Mapping):
        value = payload.get("id")
        if isinstance(value, (str, int)) and str(value):
            return str(value)
    raise InstagramPublishingError("Instagram returned an invalid publication response.")


async def publish_media(
    account: InstagramAccount,
    media: InstagramMedia,
    access_token: str,
    storage: SupabaseStorage,
) -> str:
    logger.info(
        "Starting Instagram publication for account %s (Instagram user %s), media %s (%s).",
        account.username,
        account.instagram_user_id,
        media.id,
        media.media_type,
    )
    signed_url = await storage.create_signed_url(media.storage_path)
    create_payload: dict[str, str] = {
        "access_token": access_token,
        "image_url" if media.media_type == "image" else "video_url": signed_url,
    }
    if media.media_type == "video":
        create_payload["media_type"] = "REELS"
    if media.caption:
        create_payload["caption"] = media.caption

    timeout = httpx.Timeout(30.0)
    stage = "account identity verification"
    instagram_user_id = str(account.instagram_user_id)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            identity_response = await _request_with_retry(
                client,
                "GET",
                f"{GRAPH_ENDPOINT}/me",
                params={"fields": "user_id,username", "access_token": access_token},
            )
            instagram_user_id, token_username = _instagram_user_identity(
                identity_response.json()
            )
            if token_username.casefold() != str(account.username).casefold():
                raise InstagramPublishingError(
                    "The saved Instagram token belongs to a different account; reconnect it before publishing."
                )
            if instagram_user_id != str(account.instagram_user_id):
                logger.warning(
                    "Stored Instagram user ID does not match the token for account %s; "
                    "using the ID returned by /me.",
                    account.username,
                    )
            stage = "media container creation"
            logger.info(
                "Creating Instagram media container for account %s, media %s.",
                account.username,
                media.id,
            )
            create_response = await _request_with_retry(
                client,
                "POST",
                f"{GRAPH_ENDPOINT}/{instagram_user_id}/media",
                data=create_payload,
            )
            container_id = _response_id(create_response.json())
            logger.info(
                "Created Instagram container %s for account %s, media %s.",
                container_id,
                account.username,
                media.id,
            )

            if media.media_type == "video":
                stage = "video processing status check"
                for attempt in range(1, VIDEO_PROCESSING_MAX_ATTEMPTS + 1):
                    await asyncio.sleep(VIDEO_PROCESSING_INTERVAL_SECONDS)
                    status_response = await _request_with_retry(
                        client,
                        "GET",
                        f"{GRAPH_ENDPOINT}/{container_id}",
                        params={
                            "fields": "status_code,status",
                            "access_token": access_token,
                        },
                    )
                    status_payload = status_response.json()
                    status_code = (
                        status_payload.get("status_code")
                        if isinstance(status_payload, dict)
                        else None
                    )
                    status_detail = (
                        status_payload.get("status")
                        if isinstance(status_payload, dict)
                        else None
                    )
                    logger.info(
                        "Instagram container %s processing status for account %s: %s (check %s/%s).",
                        container_id,
                        account.username,
                        status_code,
                        attempt,
                        VIDEO_PROCESSING_MAX_ATTEMPTS,
                    )
                    if status_code == "FINISHED":
                        break
                    if status_code in {"ERROR", "EXPIRED"}:
                        detail_text = (
                            " ".join(status_detail.split())[:300]
                            if isinstance(status_detail, str)
                            else ""
                        ).replace(access_token, "[redacted]")
                        logger.error(
                            "Instagram container %s failed processing for account %s: %s %s.",
                            container_id,
                            account.username,
                            status_code,
                            detail_text,
                        )
                        message = (
                            f"Instagram could not process the video container (status {status_code})."
                        )
                        if detail_text:
                            message += (
                                f" {detail_text} (verifique formato, proporção e duração do vídeo)"
                            )
                        raise InstagramPublishingError(message[:500])
                    if status_code != "IN_PROGRESS":
                        raise InstagramPublishingError(
                            "Instagram returned an unknown video processing status."
                        )
                else:
                    raise InstagramPublishingError(
                        "Instagram video processing exceeded the worker time limit."
                    )

            stage = "media publication"
            logger.info(
                "Publishing Instagram container %s for account %s.",
                container_id,
                account.username,
            )
            publish_response = await client.post(
                f"{GRAPH_ENDPOINT}/{instagram_user_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": access_token,
                },
            )
            publish_response.raise_for_status()
            published_media_id = _response_id(publish_response.json())
            logger.info(
                "Published Instagram container %s as media %s for account %s.",
                container_id,
                published_media_id,
                account.username,
            )
            return published_media_id
        except httpx.HTTPStatusError as exc:
            detail = _publication_error_detail(
                exc.response,
                stage,
                access_token,
                signed_url,
            )
            logger.error(
                "Instagram publication failed for account %s at %s: %s",
                account.username,
                stage,
                detail,
            )
            raise InstagramPublishingError(
                detail,
                status_code=exc.response.status_code,
                meta_error_code=_meta_error_code(exc.response),
            ) from None
