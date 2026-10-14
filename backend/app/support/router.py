"""Questions and problem reports with a status the author can follow."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.auth.dependencies import AuthenticatedUser, DbSession, WorkspaceMemberAccess, require_csrf
from app.core.security import PlatformRole
from app.core.time import utc_now
from app.models import SupportTicket, User

router = APIRouter(prefix="/api/support", tags=["Support"])

Status = Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]
MAX_OPEN_PER_AUTHOR = 20


class TicketCreate(BaseModel):
    kind: Literal["QUESTION", "PROBLEM"] = "QUESTION"
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=5, max_length=5000)


class TicketUpdate(BaseModel):
    status: Status | None = None
    resolution_note: str | None = Field(default=None, max_length=5000)


class TicketResponse(BaseModel):
    id: UUID
    kind: str
    title: str
    description: str
    status: str
    resolution_note: str | None
    author_name: str
    is_mine: bool
    can_manage: bool
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class TicketListResponse(BaseModel):
    scope: str
    total: int
    counts: dict[str, int]
    items: list[TicketResponse]


def _is_admin(user: User) -> bool:
    return user.platform_role == PlatformRole.SUPER_ADMIN.value


def _can_manage(user: User, role: str | None, ticket: SupportTicket, workspace_id: UUID | None) -> bool:
    if _is_admin(user):
        return True
    # A workspace owner handles tickets of their collaborators, never their own.
    return role == "OWNER" and ticket.workspace_id == workspace_id and ticket.author_user_id != user.id


def _view(ticket: SupportTicket, author: str, user: User, role: str | None, workspace_id: UUID | None) -> TicketResponse:
    return TicketResponse(
        id=ticket.id,
        kind=ticket.kind,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        resolution_note=ticket.resolution_note,
        author_name=author,
        is_mine=ticket.author_user_id == user.id,
        can_manage=_can_manage(user, role, ticket, workspace_id),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
    )


@router.post("/tickets", response_model=TicketResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_ticket(
    payload: TicketCreate, access: WorkspaceMemberAccess, user: AuthenticatedUser, db: DbSession
) -> TicketResponse:
    open_count = await db.scalar(
        select(func.count(SupportTicket.id)).where(
            SupportTicket.author_user_id == user.id, SupportTicket.status.in_(("OPEN", "IN_PROGRESS"))
        )
    )
    if (open_count or 0) >= MAX_OPEN_PER_AUTHOR:
        raise HTTPException(status_code=429, detail="Você já tem muitos chamados abertos.")
    ticket = SupportTicket(
        workspace_id=access.workspace.id,
        author_user_id=user.id,
        kind=payload.kind,
        title=" ".join(payload.title.split()),
        description=payload.description.strip(),
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return _view(ticket, user.full_name, user, access.membership.role, access.workspace.id)


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    access: WorkspaceMemberAccess,
    user: AuthenticatedUser,
    db: DbSession,
    scope: Literal["mine", "workspace", "all"] = "mine",
    status: Status | None = None,
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=20, ge=5, le=100),
) -> TicketListResponse:
    role = access.membership.role
    conditions = []
    if scope == "all":
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
    elif scope == "workspace":
        if role != "OWNER":
            raise HTTPException(status_code=403, detail="Owner role required.")
        conditions.append(SupportTicket.workspace_id == access.workspace.id)
        conditions.append(SupportTicket.author_user_id != user.id)
    else:
        conditions.append(SupportTicket.author_user_id == user.id)
    counts = dict(
        (
            await db.execute(
                select(SupportTicket.status, func.count(SupportTicket.id)).where(*conditions).group_by(SupportTicket.status)
            )
        ).all()
    )
    filtered = [*conditions, *([SupportTicket.status == status] if status else [])]
    total = await db.scalar(select(func.count(SupportTicket.id)).where(*filtered)) or 0
    rows = (
        await db.execute(
            select(SupportTicket, User.full_name)
            .join(User, User.id == SupportTicket.author_user_id)
            .where(*filtered)
            .order_by(SupportTicket.created_at.desc(), SupportTicket.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    return TicketListResponse(
        scope=scope,
        total=total,
        counts={key: counts.get(key, 0) for key in ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED")},
        items=[_view(ticket, author, user, role, access.workspace.id) for ticket, author in rows],
    )


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse, dependencies=[Depends(require_csrf)])
async def update_ticket(
    ticket_id: UUID,
    payload: TicketUpdate,
    access: WorkspaceMemberAccess,
    user: AuthenticatedUser,
    db: DbSession,
) -> TicketResponse:
    ticket = await db.get(SupportTicket, ticket_id)
    role = access.membership.role
    manager = ticket is not None and _can_manage(user, role, ticket, access.workspace.id)
    author = ticket is not None and ticket.author_user_id == user.id
    if ticket is None or not (manager or author):
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    if not manager:
        # The author may only close their own ticket.
        if payload.resolution_note is not None or payload.status not in (None, "CLOSED"):
            raise HTTPException(status_code=403, detail="Você só pode encerrar o seu chamado.")
    if payload.status is not None:
        ticket.status = payload.status
        if payload.status in ("RESOLVED", "CLOSED"):
            ticket.resolved_at = utc_now()
            ticket.resolved_by_user_id = user.id
        else:
            ticket.resolved_at = None
            ticket.resolved_by_user_id = None
    if payload.resolution_note is not None:
        ticket.resolution_note = payload.resolution_note.strip() or None
    await db.commit()
    await db.refresh(ticket)
    author_name = await db.scalar(select(User.full_name).where(User.id == ticket.author_user_id)) or ""
    return _view(ticket, author_name, user, role, access.workspace.id)
