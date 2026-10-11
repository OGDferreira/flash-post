from datetime import datetime, timezone
import csv
import io
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from app.auth.dependencies import (
    DbSession,
    WorkspaceMemberAccess,
    require_csrf,
)
from app.core.time import utc_now
from app.models import DiagnosticsEvent

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
    created_at: datetime


class DiagnosticsEventsResponse(BaseModel):
    events: list[DiagnosticsEventResponse]


def _filtered_events_query(
    workspace_id: UUID,
    source: str | None,
    account_id: UUID | None,
    loop_id: UUID | None,
    category: str | None,
    q: str | None,
    since: datetime | None,
):
    query = select(DiagnosticsEvent).where(DiagnosticsEvent.workspace_id == workspace_id)
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


@router.get("/events", response_model=DiagnosticsEventsResponse)
async def list_diagnostics_events(
    access: WorkspaceMemberAccess,
    db: DbSession,
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
                access.workspace.id, source, account_id, loop_id, category, q, since
            ).limit(limit)
        )
    ).all()
    return DiagnosticsEventsResponse(
        events=[DiagnosticsEventResponse.model_validate(event) for event in events]
    )


@router.get("/events.csv")
async def export_diagnostics_events(
    access: WorkspaceMemberAccess,
    db: DbSession,
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
                access.workspace.id, source, account_id, loop_id, category, q, since
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
