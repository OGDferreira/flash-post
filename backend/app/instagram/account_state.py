from datetime import datetime, timezone

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InstagramAccount, InstagramLoopAccount, InstagramPublicationJob


async def isolate_inactive_account(
    db: AsyncSession,
    account: InstagramAccount,
    status: str,
    reason: str,
) -> None:
    if status not in {"error", "disconnected"}:
        raise ValueError("Inactive Instagram account status must be error or disconnected.")

    account.status = status
    account.status_reason = reason[:500]
    account.profile_folder_id = None
    if account.error_at is None:
        account.error_at = datetime.now(timezone.utc)

    await db.execute(
        delete(InstagramLoopAccount).where(
            InstagramLoopAccount.account_id == account.id
        )
    )
    await db.execute(
        delete(InstagramPublicationJob).where(
            InstagramPublicationJob.account_id == account.id,
            InstagramPublicationJob.status.in_(("waiting_for_media", "queued")),
        )
    )
    await db.execute(
        update(InstagramPublicationJob)
        .where(
            InstagramPublicationJob.account_id == account.id,
            InstagramPublicationJob.status == "publishing",
        )
        .values(status="failed", last_error=reason[:500])
    )
