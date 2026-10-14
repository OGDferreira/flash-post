import json
import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.config import get_settings
from app.models import InstagramAccount, Workspace
from app.shark.ingest import (
    event_batches,
    log_event,
    parse_event,
    upsert_lead,
    upsert_transaction,
)

router = APIRouter(prefix="/api/sharkbot", tags=["Sharkbot"])
logger = logging.getLogger(__name__)
_MAX_WEBHOOK_BYTES = 1_048_576


class SharkbotAccountWebhook(BaseModel):
    account_id: UUID
    username: str
    webhook_url: str


class SharkbotWebhookSettings(BaseModel):
    # One URL per workspace. Several bots/flows may use it: events are told
    # apart by bot.id / flow.id. Use an account URL only to attribute a bot's
    # sales to a specific Instagram account.
    webhook_url: str
    account_webhooks: list[SharkbotAccountWebhook] = []


class SharkbotWebhookResponse(BaseModel):
    accepted: int
    duplicates: int
    ignored: int = 0


async def _settings_response(db: DbSession, workspace: Workspace) -> SharkbotWebhookSettings:
    base_url = f"{get_settings().public_base_url.rstrip('/')}/api/sharkbot/webhook/{workspace.sharkbot_webhook_token}"
    accounts = (
        await db.execute(
            select(InstagramAccount.id, InstagramAccount.username)
            .where(InstagramAccount.workspace_id == workspace.id)
            .order_by(InstagramAccount.username)
        )
    ).all()
    return SharkbotWebhookSettings(
        webhook_url=base_url,
        account_webhooks=[
            SharkbotAccountWebhook(
                account_id=account_id, username=username, webhook_url=f"{base_url}?account={account_id}"
            )
            for account_id, username in accounts
        ],
    )


@router.get("/webhook/config", response_model=SharkbotWebhookSettings)
async def get_webhook_settings(
    access: OwnerAccess,
    db: DbSession,
) -> SharkbotWebhookSettings:
    workspace = await db.get(Workspace, access.workspace.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if not workspace.sharkbot_webhook_token:
        workspace.sharkbot_webhook_token = secrets.token_urlsafe(32)
        await db.commit()
    return await _settings_response(db, workspace)


@router.post(
    "/webhook/rotate",
    response_model=SharkbotWebhookSettings,
    dependencies=[Depends(require_csrf)],
)
async def rotate_webhook_settings(
    access: OwnerAccess,
    db: DbSession,
) -> SharkbotWebhookSettings:
    workspace = await db.get(Workspace, access.workspace.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    workspace.sharkbot_webhook_token = secrets.token_urlsafe(32)
    await db.commit()
    return await _settings_response(db, workspace)


@router.post(
    "/webhook/{webhook_token}",
    response_model=SharkbotWebhookResponse,
)
async def receive_sharkbot_webhook(
    webhook_token: str,
    request: Request,
    db: DbSession,
    account: UUID | None = Query(default=None),
) -> SharkbotWebhookResponse:
    # Authentication: SharkBot sends no signature, so the secret token in the
    # URL is the credential. It is checked before the body is read.
    if not 16 <= len(webhook_token) <= 128:
        raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")
    workspace = await db.scalar(
        select(Workspace).where(Workspace.sharkbot_webhook_token == webhook_token)
    )
    if workspace is None or not secrets.compare_digest(
        workspace.sharkbot_webhook_token or "", webhook_token
    ):
        raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")
    account_id: UUID | None = None
    if account is not None:
        # Only accounts of this workspace; otherwise the URL is misconfigured.
        account_id = await db.scalar(
            select(InstagramAccount.id).where(
                InstagramAccount.id == account,
                InstagramAccount.workspace_id == workspace.id,
            )
        )
        if account_id is None:
            raise HTTPException(status_code=404, detail="Sharkbot webhook not found.")

    chunks: list[bytes] = []
    content_size = 0
    async for chunk in request.stream():
        content_size += len(chunk)
        if content_size > _MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="Sharkbot payload is too large.")
        chunks.append(chunk)
    try:
        payload = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Sharkbot payload must be valid JSON.") from None
    events = event_batches(payload)
    if not events:
        raise HTTPException(status_code=422, detail="No recognizable Sharkbot events found.")

    now = datetime.now(timezone.utc)
    accepted = duplicates = ignored = 0
    for raw_event in events:
        parsed = parse_event(raw_event)
        if parsed is None:
            ignored += 1
            continue
        if parsed.event_type == "lead_initiated":
            changed = await upsert_lead(db, workspace.id, parsed, account_id, now)
        elif parsed.transaction_key is not None:
            changed = await upsert_transaction(db, workspace.id, parsed, account_id, now)
        else:  # link_click: logged only
            changed = False
        await log_event(db, workspace.id, parsed, account_id)
        if changed:
            accepted += 1
        else:
            duplicates += 1
    await db.commit()
    # Unknown event types are acknowledged (200) so SharkBot does not retry
    # them forever; they are reported as ignored.
    return SharkbotWebhookResponse(accepted=accepted, duplicates=duplicates, ignored=ignored)
