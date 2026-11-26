from datetime import datetime, timedelta, timezone
import csv
import io
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from app.auth.dependencies import (
    DbSession,
    SuperAdminUser,
    WorkspaceMemberAccess,
    require_csrf,
)
from app.core.time import utc_now
from app.diagnostics.service import resolve_account_diagnostics
from app.models import DiagnosticsEvent, InstagramAccount, InstagramLoop, Workspace

# Window of history shown in the per-account health panel (matches DIAGNOSTICS_RETENTION).
HEALTH_WINDOW_DAYS = 14
# Operational problems worth surfacing to the owner (browser/client_api noise excluded).
HEALTH_SOURCE = "server"

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"])
MAX_EVENTS_PER_WORKSPACE = 1000


class DiagnosticsEventCreate(BaseModel):
    source: Literal["browser", "client_api"] = "browser"
    level: Literal["error", "warning"] = "error"
    message: str = Field(min_length=1, max_length=2000)
    stack: str | None = Field(default=None, max_length=8000)
    path: str = Field(min_length=1, max_length=500)


class DiagnosticsEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    level: str
    message: str
    stack: str | None
    path: str
    account_id: UUID | None = None
    loop_id: UUID | None = None
    job_id: UUID | None = None
    category: str | None = None
    meta_code: int | None = None
    status: str = "pending"
    resolved_at: datetime | None = None
    created_at: datetime
    workspace_id: UUID | None = None
    workspace_name: str | None = None


class DiagnosticsEventsResponse(BaseModel):
    events: list[DiagnosticsEventResponse]


def _filtered_events_query(
    workspace_id: UUID | None,
    source: str | None,
    account_id: UUID | None,
    loop_id: UUID | None,
    category: str | None,
    q: str | None,
    since: datetime | None,
):
    query = select(DiagnosticsEvent)
    if workspace_id is not None:  # None = every workspace (the Super Admin's platform log)
        query = query.where(DiagnosticsEvent.workspace_id == workspace_id)
    if source:
        query = query.where(DiagnosticsEvent.source == source)
    if account_id:
        query = query.where(DiagnosticsEvent.account_id == account_id)
    if loop_id:
        query = query.where(DiagnosticsEvent.loop_id == loop_id)
    if category:
        query = query.where(DiagnosticsEvent.category == category)
    if q:
        query = query.where(DiagnosticsEvent.message.ilike(f"%{q[:100]}%"))
    if since:
        query = query.where(DiagnosticsEvent.created_at >= since)
    return query.order_by(DiagnosticsEvent.created_at.desc(), DiagnosticsEvent.id.desc())


# Reading the error log is for the Super Admin only (every workspace, or one); every member
# still reports errors.
@router.get("/events", response_model=DiagnosticsEventsResponse)
async def list_diagnostics_events(
    _admin: SuperAdminUser,
    db: DbSession,
    workspace_id: UUID | None = None,
    limit: int = Query(default=300, ge=1, le=1000),
    source: str | None = None,
    account_id: UUID | None = None,
    loop_id: UUID | None = None,
    category: str | None = None,
    q: str | None = None,
    since: datetime | None = None,
) -> DiagnosticsEventsResponse:
    events = (
        await db.scalars(
            _filtered_events_query(
                workspace_id, source, account_id, loop_id, category, q, since
            ).limit(limit)
        )
    ).all()
    ids = {event.workspace_id for event in events}
    names = dict((await db.execute(select(Workspace.id, Workspace.name).where(Workspace.id.in_(ids)))).all()) if ids else {}
    return DiagnosticsEventsResponse(
        events=[
            DiagnosticsEventResponse.model_validate(event).model_copy(update={"workspace_name": names.get(event.workspace_id)})
            for event in events
        ]
    )


@router.get("/events.csv")
async def export_diagnostics_events(
    _admin: SuperAdminUser,
    db: DbSession,
    workspace_id: UUID | None = None,
    source: str | None = None,
    account_id: UUID | None = None,
    loop_id: UUID | None = None,
    category: str | None = None,
    q: str | None = None,
    since: datetime | None = None,
) -> Response:
    events = (
        await db.scalars(
            _filtered_events_query(
                workspace_id, source, account_id, loop_id, category, q, since
            ).limit(MAX_EVENTS_PER_WORKSPACE)
        )
    ).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["data", "origem", "nivel", "categoria", "codigo_meta", "conta", "loop", "caminho", "mensagem"]
    )
    for event in events:
        message = event.message
        if message[:1] in {"=", "+", "-", "@"}:
            message = "'" + message
        writer.writerow(
            [
                event.created_at.isoformat(),
                event.source,
                event.level,
                event.category or "",
                event.meta_code or "",
                event.account_id or "",
                event.loop_id or "",
                event.path,
                message,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="log-de-erros.csv"'},
    )


@router.post(
    "/events",
    response_model=DiagnosticsEventResponse,
    dependencies=[Depends(require_csrf)],
)
async def create_diagnostics_event(
    payload: DiagnosticsEventCreate,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> DiagnosticsEventResponse:
    event = DiagnosticsEvent(
        workspace_id=access.workspace.id,
        user_id=access.membership.user_id,
        source=payload.source,
        level=payload.level,
        message=payload.message,
        stack=payload.stack,
        path=payload.path,
        created_at=utc_now().astimezone(timezone.utc),
    )
    db.add(event)
    await db.flush()

    excess_ids = (
        select(DiagnosticsEvent.id)
        .where(DiagnosticsEvent.workspace_id == access.workspace.id)
        .order_by(DiagnosticsEvent.created_at.desc(), DiagnosticsEvent.id.desc())
        .offset(MAX_EVENTS_PER_WORKSPACE)
    )
    await db.execute(
        delete(DiagnosticsEvent).where(
            DiagnosticsEvent.workspace_id == access.workspace.id,
            DiagnosticsEvent.id.in_(excess_ids),
        )
    )
    await db.commit()
    await db.refresh(event)
    return DiagnosticsEventResponse(
        id=event.id,
        source=event.source,
        level=event.level,
        message=event.message,
        stack=event.stack,
        path=event.path,
        created_at=event.created_at,
    )


# ----------------------------------------------------------------------------------
# Per-account health panel (owner/member). The Super Admin uses the full log above;
# every member sees the operational errors of their own workspace, grouped per account.
# ----------------------------------------------------------------------------------

_MAX_HEALTH_EVENTS_SCAN = 2000
_MAX_EVENTS_PER_ACCOUNT = 20


class HealthEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    category: str | None = None
    level: str
    message: str
    status: str
    resolved_at: datetime | None = None


class AccountHealth(BaseModel):
    account_id: UUID
    username: str
    profile_picture_url: str | None = None
    status: str
    status_reason: str | None = None
    error_at: datetime | None = None
    token_expires_at: datetime | None = None
    pending_count: int
    last_event_at: datetime | None = None
    events: list[HealthEvent]


class LoopAlert(BaseModel):
    id: UUID
    loop_id: UUID
    loop_name: str | None = None
    created_at: datetime
    message: str
    status: str


class AccountHealthResponse(BaseModel):
    accounts: list[AccountHealth]
    loops: list[LoopAlert]
    pending_total: int


@router.get("/account-health", response_model=AccountHealthResponse)
async def account_health(
    access: WorkspaceMemberAccess,
    db: DbSession,
    include_resolved: bool = Query(default=True),
) -> AccountHealthResponse:
    workspace_id = access.workspace.id
    since = utc_now().astimezone(timezone.utc) - timedelta(days=HEALTH_WINDOW_DAYS)

    events = (
        await db.scalars(
            select(DiagnosticsEvent)
            .where(
                DiagnosticsEvent.workspace_id == workspace_id,
                DiagnosticsEvent.source == HEALTH_SOURCE,
                DiagnosticsEvent.created_at >= since,
            )
            .order_by(DiagnosticsEvent.created_at.desc(), DiagnosticsEvent.id.desc())
            .limit(_MAX_HEALTH_EVENTS_SCAN)
        )
    ).all()

    per_account: dict[UUID, list[DiagnosticsEvent]] = {}
    pending_by_account: dict[UUID, int] = {}
    loop_alerts_raw: list[DiagnosticsEvent] = []
    seen_loops: set[UUID] = set()
    pending_total = 0
    for event in events:
        if event.status == "pending":
            pending_total += 1
        if event.account_id is not None:
            bucket = per_account.setdefault(event.account_id, [])
            if len(bucket) < _MAX_EVENTS_PER_ACCOUNT:
                bucket.append(event)
            if event.status == "pending":
                pending_by_account[event.account_id] = (
                    pending_by_account.get(event.account_id, 0) + 1
                )
        elif event.category == "loop_stuck" and event.loop_id is not None:
            # Latest alert per loop only.
            if event.loop_id not in seen_loops:
                seen_loops.add(event.loop_id)
                loop_alerts_raw.append(event)

    # Accounts to show: those with events, plus any currently not connected.
    disconnected = (
        await db.scalars(
            select(InstagramAccount).where(
                InstagramAccount.workspace_id == workspace_id,
                InstagramAccount.status != "connected",
            )
        )
    ).all()
    account_ids = set(per_account) | {a.id for a in disconnected}
    accounts_by_id = {a.id: a for a in disconnected}
    missing = account_ids - set(accounts_by_id)
    if missing:
        rows = (
            await db.scalars(
                select(InstagramAccount).where(
                    InstagramAccount.workspace_id == workspace_id,
                    InstagramAccount.id.in_(missing),
                )
            )
        ).all()
        accounts_by_id.update({a.id: a for a in rows})

    accounts: list[AccountHealth] = []
    for account_id in account_ids:
        account = accounts_by_id.get(account_id)
        if account is None:
            continue  # account was deleted; its events are orphaned.
        bucket = per_account.get(account_id, [])
        if not include_resolved:
            bucket = [e for e in bucket if e.status == "pending"]
        accounts.append(
            AccountHealth(
                account_id=account.id,
                username=account.username,
                profile_picture_url=account.profile_picture_url,
                status=account.status,
                status_reason=account.status_reason,
                error_at=account.error_at,
                token_expires_at=account.token_expires_at,
                pending_count=pending_by_account.get(account_id, 0),
                last_event_at=bucket[0].created_at if bucket else account.error_at,
                events=[HealthEvent.model_validate(e) for e in bucket],
            )
        )
    # Worst first: not-connected and most pending at the top.
    accounts.sort(
        key=lambda a: (a.status == "connected", -a.pending_count, a.username.lower())
    )

    loop_names: dict[UUID, str] = {}
    if loop_alerts_raw:
        loop_ids = {e.loop_id for e in loop_alerts_raw if e.loop_id}
        loop_names = dict(
            (
                await db.execute(
                    select(InstagramLoop.id, InstagramLoop.name).where(
                        InstagramLoop.id.in_(loop_ids)
                    )
                )
            ).all()
        )
    loops = [
        LoopAlert(
            id=e.id,
            loop_id=e.loop_id,
            loop_name=loop_names.get(e.loop_id),
            created_at=e.created_at,
            message=e.message,
            status=e.status,
        )
        for e in loop_alerts_raw
    ]

    return AccountHealthResponse(
        accounts=accounts, loops=loops, pending_total=pending_total
    )


async def _owned_event(db, event_id: UUID, workspace_id: UUID) -> DiagnosticsEvent:
    event = await db.get(DiagnosticsEvent, event_id)
    if event is None or event.workspace_id != workspace_id:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Evento não encontrado.")
    return event


@router.post(
    "/events/{event_id}/resolve",
    response_model=DiagnosticsEventResponse,
    dependencies=[Depends(require_csrf)],
)
async def resolve_event(
    event_id: UUID,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> DiagnosticsEventResponse:
    event = await _owned_event(db, event_id, access.workspace.id)
    event.status = "resolved"
    event.resolved_at = utc_now().astimezone(timezone.utc)
    await db.commit()
    await db.refresh(event)
    return DiagnosticsEventResponse.model_validate(event)


@router.post(
    "/events/{event_id}/reopen",
    response_model=DiagnosticsEventResponse,
    dependencies=[Depends(require_csrf)],
)
async def reopen_event(
    event_id: UUID,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> DiagnosticsEventResponse:
    event = await _owned_event(db, event_id, access.workspace.id)
    event.status = "pending"
    event.resolved_at = None
    await db.commit()
    await db.refresh(event)
    return DiagnosticsEventResponse.model_validate(event)


@router.post(
    "/accounts/{account_id}/resolve",
    dependencies=[Depends(require_csrf)],
)
async def resolve_account(
    account_id: UUID,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> dict:
    account = await db.get(InstagramAccount, account_id)
    if account is None or account.workspace_id != access.workspace.id:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Conta não encontrada.")
    resolved = await resolve_account_diagnostics(db, account_id, categories=None)
    await db.commit()
    return {"resolved": resolved}
