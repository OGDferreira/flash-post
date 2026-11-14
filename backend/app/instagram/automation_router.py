"""CRUD for the ManyChat-style Instagram automations (keyword -> reply + DM)."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.config import get_settings
from app.models import (
    InstagramAccount,
    InstagramAutomationEvent,
    InstagramCommentAutomation,
)

router = APIRouter(prefix="/api/instagram/automations", tags=["Instagram automations"])
csrf = [Depends(require_csrf)]


class LinkButton(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=40)]
    url: Annotated[str, Field(min_length=1, max_length=2048)]


class AutomationPayload(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    enabled: bool = True
    trigger_type: Literal["comment", "dm"] = "comment"
    instagram_account_id: uuid.UUID | None = None
    keywords: Annotated[list[Annotated[str, Field(max_length=80)]], Field(max_length=30)] = []
    match_mode: Literal["any", "exact"] = "any"
    media_id: Annotated[str | None, Field(max_length=191)] = None
    public_reply_enabled: bool = False
    public_replies: Annotated[list[Annotated[str, Field(max_length=900)]], Field(max_length=10)] = []
    dm_enabled: bool = True
    dm_text: Annotated[str | None, Field(max_length=1000)] = None
    dm_buttons: Annotated[list[LinkButton], Field(max_length=3)] = []


def _out(rule: InstagramCommentAutomation) -> dict:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "enabled": rule.enabled,
        "trigger_type": rule.trigger_type,
        "instagram_account_id": str(rule.instagram_account_id) if rule.instagram_account_id else None,
        "keywords": rule.keywords or [],
        "match_mode": rule.match_mode,
        "media_id": rule.media_id,
        "public_reply_enabled": rule.public_reply_enabled,
        "public_replies": rule.public_replies or [],
        "dm_enabled": rule.dm_enabled,
        "dm_text": rule.dm_text,
        "dm_buttons": rule.dm_buttons or [],
        "fired_count": rule.fired_count,
        "last_fired_at": rule.last_fired_at.isoformat() if rule.last_fired_at else None,
    }


async def _owned(db, access, rule_id: uuid.UUID) -> InstagramCommentAutomation:
    rule = await db.get(InstagramCommentAutomation, rule_id)
    if rule is None or rule.workspace_id != access.workspace.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automação não encontrada.")
    return rule


async def _check_account(db, access, account_id: uuid.UUID | None) -> None:
    if account_id is None:
        return
    exists = await db.scalar(
        select(InstagramAccount.id).where(
            InstagramAccount.id == account_id,
            InstagramAccount.workspace_id == access.workspace.id,
        )
    )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta do Instagram não encontrada.")


def _apply(rule: InstagramCommentAutomation, payload: AutomationPayload) -> None:
    rule.name = payload.name.strip()
    rule.enabled = payload.enabled
    rule.trigger_type = payload.trigger_type
    rule.instagram_account_id = payload.instagram_account_id
    rule.keywords = [kw.strip() for kw in payload.keywords if kw.strip()]
    rule.match_mode = payload.match_mode
    rule.media_id = (payload.media_id or "").strip() or None if payload.trigger_type == "comment" else None
    rule.public_reply_enabled = payload.public_reply_enabled
    rule.public_replies = [r for r in payload.public_replies if r.strip()]
    rule.dm_enabled = payload.dm_enabled
    rule.dm_text = payload.dm_text
    rule.dm_buttons = [b.model_dump() for b in payload.dm_buttons]


@router.get("")
async def list_automations(access: OwnerAccess, db: DbSession) -> dict:
    rows = await db.scalars(
        select(InstagramCommentAutomation)
        .where(InstagramCommentAutomation.workspace_id == access.workspace.id)
        .order_by(InstagramCommentAutomation.created_at.desc())
    )
    return {
        "automations": [_out(rule) for rule in rows],
        # When off, rules still match but the engine only logs what it would send.
        "live": get_settings().instagram_automation_enabled,
    }


@router.post("", dependencies=csrf, status_code=status.HTTP_201_CREATED)
async def create_automation(payload: AutomationPayload, access: OwnerAccess, db: DbSession) -> dict:
    await _check_account(db, access, payload.instagram_account_id)
    rule = InstagramCommentAutomation(
        workspace_id=access.workspace.id, created_by_user_id=access.membership.user_id
    )
    _apply(rule, payload)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _out(rule)


@router.put("/{rule_id}", dependencies=csrf)
async def update_automation(
    rule_id: uuid.UUID, payload: AutomationPayload, access: OwnerAccess, db: DbSession
) -> dict:
    rule = await _owned(db, access, rule_id)
    await _check_account(db, access, payload.instagram_account_id)
    _apply(rule, payload)
    await db.commit()
    await db.refresh(rule)
    return _out(rule)


@router.delete("/{rule_id}", dependencies=csrf)
async def delete_automation(rule_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    rule = await _owned(db, access, rule_id)
    await db.delete(rule)
    await db.commit()
    return {"ok": True}


@router.get("/{rule_id}/events")
async def automation_events(rule_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    await _owned(db, access, rule_id)
    rows = await db.scalars(
        select(InstagramAutomationEvent)
        .where(InstagramAutomationEvent.automation_id == rule_id)
        .order_by(InstagramAutomationEvent.created_at.desc())
        .limit(50)
    )
    return {
        "events": [
            {
                "id": str(event.id),
                "object_id": event.object_id,
                "status": event.status,
                "detail": event.detail,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in rows
        ]
    }
