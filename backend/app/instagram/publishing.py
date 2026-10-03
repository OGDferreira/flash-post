import asyncio
from collections.abc import Mapping

import httpx

from app.instagram.storage import SupabaseStorage
from app.models import InstagramAccount, InstagramMedia

GRAPH_ENDPOINT = "https://graph.instagram.com/v25.0"
VIDEO_PROCESSING_INTERVAL_SECONDS = 10
VIDEO_PROCESSING_MAX_ATTEMPTS = 90


class InstagramPublishingError(RuntimeError):
    pass


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
    message = error.get("message") if isinstance(error, Mapping) else None

    details = []
    if isinstance(error_type, str) and error_type:
        details.append(error_type[:80])
    if isinstance(code, (str, int)):
        details.append(f"code {code}")
    if isinstance(subcode, (str, int)):
        details.append(f"subcode {subcode}")

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
    stage = "media container creation"
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            create_response = await client.post(
                f"{GRAPH_ENDPOINT}/{account.instagram_user_id}/media",
                data=create_payload,
            )
            create_response.raise_for_status()
            container_id = _response_id(create_response.json())

            if media.media_type == "video":
                stage = "video processing status check"
                for _ in range(VIDEO_PROCESSING_MAX_ATTEMPTS):
                    await asyncio.sleep(VIDEO_PROCESSING_INTERVAL_SECONDS)
                    status_response = await client.get(
                        f"{GRAPH_ENDPOINT}/{container_id}",
                        params={
                            "fields": "status_code",
                            "access_token": access_token,
                        },
                    )
                    status_response.raise_for_status()
                    status_payload = status_response.json()
                    status_code = (
                        status_payload.get("status_code")
                        if isinstance(status_payload, dict)
                        else None
                    )
                    if status_code == "FINISHED":
                        break
                    if status_code in {"ERROR", "EXPIRED"}:
                        raise InstagramPublishingError(
                            "Instagram could not process the video container."
                        )
                    if status_code != "IN_PROGRESS":
                        raise InstagramPublishingError(
                            "Instagram returned an unknown video processing status."
                        )
                else:
                    raise InstagramPublishingError(
                        "Instagram video processing exceeded the worker time limit."
                    )

            stage = "media publication"
            publish_response = await client.post(
                f"{GRAPH_ENDPOINT}/{account.instagram_user_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": access_token,
                },
            )
            publish_response.raise_for_status()
            return _response_id(publish_response.json())
        except httpx.HTTPStatusError as exc:
            raise InstagramPublishingError(
                _publication_error_detail(
                    exc.response,
                    stage,
                    access_token,
                    signed_url,
                )
            ) from None
