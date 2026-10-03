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
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            create_response = await client.post(
                f"{GRAPH_ENDPOINT}/{account.instagram_user_id}/media",
                data=create_payload,
            )
            create_response.raise_for_status()
            container_id = _response_id(create_response.json())

            if media.media_type == "video":
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
                f"Instagram rejected the publication request (HTTP {exc.response.status_code})."
            ) from None
