import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import DbSession
from app.core.config import get_settings
from app.core.crypto import decrypt_value
from app.models import InstagramAppCredential

router = APIRouter(prefix="/api/instagram", tags=["Instagram webhooks"])
logger = logging.getLogger(__name__)
_MAX_WEBHOOK_BODY_BYTES = 1_048_576


class InstagramWebhookReceipt(BaseModel):
    received: bool
    entry_count: int


@router.get("/webhook", include_in_schema=True)
async def verify_instagram_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    configured_token = get_settings().instagram_webhook_verify_token
    if configured_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Instagram webhook verification is not configured.",
        )
    if mode != "subscribe" or verify_token is None or challenge is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Instagram webhook verification request.",
        )
    if not hmac.compare_digest(
        verify_token,
        configured_token.get_secret_value(),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instagram webhook verification token did not match.",
        )
    return Response(content=challenge, media_type="text/plain")


async def _read_limited_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook content length.",
            ) from None
        if declared_length < 0 or declared_length > _MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Instagram webhook payload is too large.",
            )

    chunks: list[bytes] = []
    content_size = 0
    async for chunk in request.stream():
        content_size += len(chunk)
        if content_size > _MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Instagram webhook payload is too large.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _configured_app_secrets(db: DbSession) -> list[str]:
    credentials = (
        await db.scalars(
            select(InstagramAppCredential.encrypted_app_secret)
        )
    ).all()
    app_secrets: list[str] = []
    for encrypted_secret in credentials:
        try:
            app_secrets.append(decrypt_value(encrypted_secret))
        except (RuntimeError, ValueError) as exc:
            logger.error(
                "Could not decrypt a Meta app secret for webhook validation (%s).",
                type(exc).__name__,
            )
    return app_secrets


@router.post("/webhook", response_model=InstagramWebhookReceipt)
async def receive_instagram_webhook(
    request: Request,
    db: DbSession,
) -> InstagramWebhookReceipt:
    body = await _read_limited_body(request)
    signature = request.headers.get("x-hub-signature-256", "")
    if not signature.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Instagram webhook signature.",
        )

    app_secrets = await _configured_app_secrets(db)
    if not app_secrets:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Meta app is available to validate the webhook signature.",
        )
    supplied_signature = signature.removeprefix("sha256=")
    signature_valid = False
    for app_secret in app_secrets:
        expected_signature = hmac.new(
            app_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        signature_valid = hmac.compare_digest(
            supplied_signature,
            expected_signature,
        ) or signature_valid
    if not signature_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Instagram webhook signature did not match a configured Meta app.",
        )

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instagram webhook payload must be valid JSON.",
        ) from None
    if (
        not isinstance(payload, dict)
        or payload.get("object") != "instagram"
        or not isinstance(payload.get("entry"), list)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instagram webhook payload has an unsupported shape.",
        )

    event_count = sum(
        len(entry.get("changes", [])) + len(entry.get("messaging", []))
        for entry in payload["entry"]
        if isinstance(entry, dict)
        and isinstance(entry.get("changes", []), list)
        and isinstance(entry.get("messaging", []), list)
    )
    logger.info(
        "Received verified Instagram webhook with %s entries and %s events.",
        len(payload["entry"]),
        event_count,
    )
    return InstagramWebhookReceipt(received=True, entry_count=len(payload["entry"]))
