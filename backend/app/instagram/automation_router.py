"""CRUD for the ManyChat-style Instagram automations (keyword -> reply + DM)."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.dependencies import DbSession, OwnerAccess, SuperAdminUser, require_csrf
from app.core.security import PlatformRole
from app.instagram.automation import AUTOMATIONS_ENABLED_KEY, automations_live
from app.models import (
    InstagramAccount,
    InstagramAutomationEvent,
    InstagramCommentAutomation,
    InstagramProfileFolder,
    SystemSetting,
    User,
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
    # Scope by isolated profiles and/or profile folders. Both empty = every account.
    account_ids: Annotated[list[uuid.UUID], Field(max_length=200)] = []
    folder_ids: Annotated[list[uuid.UUID], Field(max_length=50)] = []
    keywords: Annotated[list[Annotated[str, Field(max_length=80)]], Field(max_length=30)] = []
    match_mode: Literal["any", "exact"] = "any"
    media_id: Annotated[str | None, Field(max_length=191)] = None
    public_reply_enabled: bool = False
    public_replies: Annotated[list[Annotated[str, Field(max_length=900)]], Field(max_length=10)] = []
    dm_enabled: bool = True
    dm_text: Annotated[str | None, Field(max_length=1000)] = None
    # DM variations (one picked at random per fire); spintax {a|b} works in each.
    dm_texts: Annotated[list[Annotated[str, Field(max_length=1000)]], Field(max_length=10)] = []
    dm_buttons: Annotated[list[LinkButton], Field(max_length=3)] = []


def _out(rule: InstagramCommentAutomation) -> dict:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "enabled": rule.enabled,
        "trigger_type": rule.trigger_type,
        "instagram_account_id": str(rule.instagram_account_id) if rule.instagram_account_id else None,
        "account_ids": [str(a) for a in (rule.scope_account_ids or [])],
        "folder_ids": [str(f) for f in (rule.scope_folder_ids or [])],
        "keywords": rule.keywords or [],
        "match_mode": rule.match_mode,
        "media_id": rule.media_id,
        "public_reply_enabled": rule.public_reply_enabled,
        "public_replies": rule.public_replies or [],
        "dm_enabled": rule.dm_enabled,
        "dm_text": rule.dm_text,
        "dm_texts": rule.dm_texts or [],
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


async def _check_scope(db, access, payload: AutomationPayload) -> None:
    """Every scoped account/folder must belong to the caller's workspace."""
    if payload.account_ids:
        found = set(
            await db.scalars(
                select(InstagramAccount.id).where(
                    InstagramAccount.id.in_(payload.account_ids),
                    InstagramAccount.workspace_id == access.workspace.id,
                )
            )
        )
        if len(found) != len(set(payload.account_ids)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta do Instagram não encontrada.")
    if payload.folder_ids:
        found = set(
            await db.scalars(
                select(InstagramProfileFolder.id).where(
                    InstagramProfileFolder.id.in_(payload.folder_ids),
                    InstagramProfileFolder.workspace_id == access.workspace.id,
                )
            )
        )
        if len(found) != len(set(payload.folder_ids)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta de perfis não encontrada.")


def _apply(rule: InstagramCommentAutomation, payload: AutomationPayload) -> None:
    rule.name = payload.name.strip()
    rule.enabled = payload.enabled
    rule.trigger_type = payload.trigger_type
    # New scope lists win; keep the legacy single-account field only when neither
    # list is used (so an old single-account rule still round-trips).
    rule.scope_account_ids = [str(a) for a in payload.account_ids]
    rule.scope_folder_ids = [str(f) for f in payload.folder_ids]
    if payload.account_ids or payload.folder_ids:
        rule.instagram_account_id = None
    else:
        rule.instagram_account_id = payload.instagram_account_id
    rule.keywords = [kw.strip() for kw in payload.keywords if kw.strip()]
    rule.match_mode = payload.match_mode
    rule.media_id = (payload.media_id or "").strip() or None if payload.trigger_type == "comment" else None
    rule.public_reply_enabled = payload.public_reply_enabled
    rule.public_replies = [r for r in payload.public_replies if r.strip()]
    rule.dm_enabled = payload.dm_enabled
    rule.dm_text = payload.dm_text
    rule.dm_texts = [t for t in payload.dm_texts if t.strip()]
    rule.dm_buttons = [b.model_dump() for b in payload.dm_buttons]


@router.get("")
async def list_automations(access: OwnerAccess, db: DbSession) -> dict:
    rows = await db.scalars(
        select(InstagramCommentAutomation)
        .where(InstagramCommentAutomation.workspace_id == access.workspace.id)
        .order_by(InstagramCommentAutomation.created_at.desc())
    )
    role = await db.scalar(select(User.platform_role).where(User.id == access.membership.user_id))
    return {
        "automations": [_out(rule) for rule in rows],
        # When off, rules still match but the engine only logs what it would send.
        "live": await automations_live(db),
        "can_toggle": role == PlatformRole.SUPER_ADMIN.value,
    }


class LiveFlag(BaseModel):
    enabled: bool


@router.put("/live", dependencies=csrf)
async def set_live(payload: LiveFlag, admin: SuperAdminUser, db: DbSession) -> dict:
    """Super Admin turns real sending on/off (after Meta App Review approval)."""
    row = await db.get(SystemSetting, AUTOMATIONS_ENABLED_KEY)
    value = {"enabled": bool(payload.enabled)}
    if row is None:
        db.add(SystemSetting(key=AUTOMATIONS_ENABLED_KEY, value=value, updated_by_user_id=admin.id))
    else:
        row.value, row.updated_by_user_id = value, admin.id
    await db.commit()
    return {"live": await automations_live(db)}


@router.post("", dependencies=csrf, status_code=status.HTTP_201_CREATED)
async def create_automation(payload: AutomationPayload, access: OwnerAccess, db: DbSession) -> dict:
    await _check_account(db, access, payload.instagram_account_id)
    await _check_scope(db, access, payload)
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
    await _check_scope(db, access, payload)
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
