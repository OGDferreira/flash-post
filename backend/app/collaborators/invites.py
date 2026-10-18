"""Invite links: the owner generates one, the collaborator self-registers,
and the owner approves the access (INVITED -> ACTIVE) before anything opens."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.auth.router import _nickname_in_use, _request_host
from app.core.nickname import nickname_key
from app.core.security import WorkspaceRole, hash_password
from app.models import CollaboratorInvite, User, Workspace, WorkspaceMember
from app.schemas.auth import MessageResponse, RegisterRequest

router = APIRouter(tags=["Collaborator invites"])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class InviteSettings(BaseModel):
    rate_per_connection: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    daily_connection_goal: int = Field(ge=0, le=100000)
    monthly_connection_goal: int = Field(ge=0, le=1000000)
    monthly_bonus: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class InviteCreateRequest(InviteSettings):
    expires_in_days: int = Field(default=7, ge=1, le=30)
    max_uses: int = Field(default=1, ge=1, le=50)


class InviteItem(InviteSettings):
    id: uuid.UUID
    status: str  # active | expired | used | revoked
    uses: int
    max_uses: int
    expires_at: datetime
    created_at: datetime


class InviteCreated(InviteItem):
    # Returned once: only the hash is stored, so the link cannot be shown again.
    token: str


class InviteDefaults(InviteSettings):
    from_last_invite: bool


class InvitesResponse(BaseModel):
    invites: list[InviteItem]


class InvitePublicInfo(BaseModel):
    workspace_name: str
    expires_at: datetime


def _status(invite: CollaboratorInvite, now: datetime) -> str:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.uses >= invite.max_uses:
        return "used"
    if _utc(invite.expires_at) <= now:
        return "expired"
    return "active"


def _item(invite: CollaboratorInvite, now: datetime) -> dict:
    return dict(
        id=invite.id,
        status=_status(invite, now),
        uses=invite.uses,
        max_uses=invite.max_uses,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        rate_per_connection=invite.rate_per_connection,
        daily_connection_goal=invite.daily_connection_goal,
        monthly_connection_goal=invite.monthly_connection_goal,
        monthly_bonus=invite.monthly_bonus,
    )


@router.get("/api/collaborators/invites/defaults", response_model=InviteDefaults)
async def invite_defaults(access: OwnerAccess, db: DbSession) -> InviteDefaults:
    """"Last used settings": the values of the owner's most recent invite."""
    last = await db.scalar(
        select(CollaboratorInvite)
        .where(CollaboratorInvite.workspace_id == access.workspace.id)
        .order_by(CollaboratorInvite.created_at.desc(), CollaboratorInvite.id)
        .limit(1)
    )
    if last is None:
        return InviteDefaults(
            rate_per_connection=Decimal("0.00"),
            daily_connection_goal=0,
            monthly_connection_goal=0,
            monthly_bonus=Decimal("0.00"),
            from_last_invite=False,
        )
    return InviteDefaults(
        rate_per_connection=last.rate_per_connection,
        daily_connection_goal=last.daily_connection_goal,
        monthly_connection_goal=last.monthly_connection_goal,
        monthly_bonus=last.monthly_bonus,
        from_last_invite=True,
    )


@router.get("/api/collaborators/invites", response_model=InvitesResponse)
async def list_invites(access: OwnerAccess, db: DbSession) -> InvitesResponse:
    now = datetime.now(timezone.utc)
    rows = (
        await db.scalars(
            select(CollaboratorInvite)
            .where(CollaboratorInvite.workspace_id == access.workspace.id)
            .order_by(CollaboratorInvite.created_at.desc(), CollaboratorInvite.id)
            .limit(30)
        )
    ).all()
    return InvitesResponse(invites=[InviteItem(**_item(row, now)) for row in rows])


@router.post(
    "/api/collaborators/invites",
    response_model=InviteCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_invite(payload: InviteCreateRequest, access: OwnerAccess, db: DbSession) -> InviteCreated:
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    invite = CollaboratorInvite(
        workspace_id=access.workspace.id,
        created_by_user_id=access.membership.user_id,
        token_hash=_hash(token),
        rate_per_connection=payload.rate_per_connection,
        daily_connection_goal=payload.daily_connection_goal,
        monthly_connection_goal=payload.monthly_connection_goal,
        monthly_bonus=payload.monthly_bonus,
        max_uses=payload.max_uses,
        uses=0,
        expires_at=now + timedelta(days=payload.expires_in_days),
        created_at=now,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return InviteCreated(**_item(invite, now), token=token)


@router.delete(
    "/api/collaborators/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def revoke_invite(invite_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> None:
    invite = await db.scalar(
        select(CollaboratorInvite).where(
            CollaboratorInvite.id == invite_id,
            CollaboratorInvite.workspace_id == access.workspace.id,
        )
    )
    if invite is None:
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    invite.revoked_at = invite.revoked_at or datetime.now(timezone.utc)
    await db.commit()


async def _usable_invite(db: DbSession, token: str) -> CollaboratorInvite:
    invite = await db.scalar(
        select(CollaboratorInvite).where(CollaboratorInvite.token_hash == _hash(token))
    )
    if invite is None or _status(invite, datetime.now(timezone.utc)) != "active":
        raise HTTPException(status_code=404, detail="Este convite não é válido ou expirou.")
    return invite


@router.get("/api/auth/collaborator-invites/{token}", response_model=InvitePublicInfo)
async def invite_info(token: str, db: DbSession) -> InvitePublicInfo:
    invite = await _usable_invite(db, token)
    workspace = await db.get(Workspace, invite.workspace_id)
    return InvitePublicInfo(
        workspace_name=workspace.name if workspace else "FlashPost",
        expires_at=invite.expires_at,
    )


@router.post(
    "/api/auth/collaborator-invites/{token}/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def register_with_invite(
    token: str, payload: RegisterRequest, request: Request, db: DbSession
) -> MessageResponse:
    limiter = request.app.state.registration_rate_limiter
    rate_key = limiter.key(_request_host(request), "collaborator-invite")
    if await limiter.is_limited(rate_key):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente mais tarde.")
    await limiter.record_failure(rate_key)

    invite = await _usable_invite(db, token)
    if await db.scalar(select(User.id).where(func.lower(User.email) == str(payload.email))):
        raise HTTPException(status_code=409, detail="Este e-mail já possui cadastro.")
    if await _nickname_in_use(db, payload.nickname):
        raise HTTPException(status_code=409, detail="Este apelido já está em uso.")

    user = User(
        email=str(payload.email),
        nickname=payload.nickname,
        nickname_normalized=nickname_key(payload.nickname),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        is_active=True,
        is_verified=True,
        # Two releases: the owner (membership INVITED -> ACTIVE) and the Super Admin.
        is_approved=False,
    )
    db.add(user)
    try:
        await db.flush()
        db.add(
            WorkspaceMember(
                workspace_id=invite.workspace_id,
                user_id=user.id,
                role=WorkspaceRole.COLLABORATOR.value,
                status="INVITED",
                rate_per_connection=invite.rate_per_connection,
                daily_connection_goal=invite.daily_connection_goal,
                monthly_connection_goal=invite.monthly_connection_goal,
                monthly_bonus=invite.monthly_bonus,
            )
        )
        invite.uses += 1
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="E-mail ou apelido já em uso.") from None
    return MessageResponse(message="Cadastro enviado. Aguarde a aprovação do chefe e do administrador.")


@router.post(
    "/api/collaborators/{member_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def approve_pending(member_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> None:
    member = await _pending_member(db, access, member_id)
    member.status = "ACTIVE"
    await db.commit()


@router.post(
    "/api/collaborators/{member_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def reject_pending(member_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> None:
    member = await _pending_member(db, access, member_id)
    user_id = member.user_id
    await db.execute(delete(WorkspaceMember).where(WorkspaceMember.id == member.id))
    other = await db.scalar(select(WorkspaceMember.id).where(WorkspaceMember.user_id == user_id).limit(1))
    if other is None:
        await db.execute(delete(User).where(User.id == user_id))
    await db.commit()


async def _pending_member(db: DbSession, access: OwnerAccess, member_id: uuid.UUID) -> WorkspaceMember:
    member = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == access.workspace.id,
            WorkspaceMember.role == WorkspaceRole.COLLABORATOR.value,
            WorkspaceMember.status == "INVITED",
        )
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Cadastro pendente não encontrado.")
    return member
