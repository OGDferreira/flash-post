"""Server-side helpers for the per-account health log.

The browser reports its own errors through the ``/api/diagnostics/events`` POST; these
helpers are for the worker and OAuth flow, which record operational problems (a send that
failed, a token that expired, a loop that fell behind) and clear them when the account is
healthy again.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DiagnosticsEvent

# Categories that a reconnect makes irrelevant: once the account is back online the
# expired/revoked-token warnings no longer need the owner's attention.
TOKEN_CATEGORIES = ("token", "account_disconnected")


def build_event(
    *,
    workspace_id: UUID,
    message: str,
    path: str,
    category: str,
    level: str = "error",
    account_id: UUID | None = None,
    loop_id: UUID | None = None,
    job_id: UUID | None = None,
    meta_code: int | None = None,
    stack: str | None = None,
    source: str = "server",
) -> DiagnosticsEvent:
    """A pending server diagnostics event, ready to ``db.add(...)``."""
    return DiagnosticsEvent(
        workspace_id=workspace_id,
        source=source,
        level=level,
        message=message[:2000],
        stack=stack[-8000:] if stack else None,
        path=path[:500],
        account_id=account_id,
        loop_id=loop_id,
        job_id=job_id,
        category=category,
        meta_code=meta_code,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )


async def resolve_account_diagnostics(
    db: AsyncSession,
    account_id: UUID,
    *,
    categories: tuple[str, ...] | None = TOKEN_CATEGORIES,
) -> int:
    """Mark the account's pending events resolved (default: only token/connection ones).

    Called when an account reconnects. Returns how many events were closed. The caller
    owns the transaction (no commit here).
    """
    stmt = (
        update(DiagnosticsEvent)
        .where(
            DiagnosticsEvent.account_id == account_id,
            DiagnosticsEvent.status == "pending",
        )
        .values(status="resolved", resolved_at=datetime.now(timezone.utc))
    )
    if categories is not None:
        stmt = stmt.where(DiagnosticsEvent.category.in_(categories))
    result = await db.execute(stmt)
    return result.rowcount or 0
