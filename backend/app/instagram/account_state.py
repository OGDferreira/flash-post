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
            # Jobs that already called media_publish keep "publishing" so the
            # reconciler can still confirm whether the video went out.
            InstagramPublicationJob.publish_requested_at.is_(None),
        )
        .values(status="failed", last_error=reason[:500])
    )


_SUSPENDED_MARKERS = ("suspend", "disabled", "checkpoint", "log in to www.instagram.com")
_RESTRICTED_MARKERS = ("restrict",)
_MANUAL_REASON = "desconectada manualmente"


def classify_inactive_account(status: str, reason: str | None) -> str:
    """Why an account is not connected: manual | suspended | restricted | expired.

    Token-invalid accounts are now stored as ``disconnected`` too (same state as a manual
    removal), so the badge is derived from the reason text rather than the status: only a
    real manual disconnect carries the manual reason; everything else keeps its suspended/
    restricted/expired badge.
    """
    text = (reason or "").casefold()
    if _MANUAL_REASON in text:
        return "manual"
    if any(marker in text for marker in _SUSPENDED_MARKERS):
        return "suspended"
    if any(marker in text for marker in _RESTRICTED_MARKERS):
        return "restricted"
    if status == "disconnected" and not text:
        return "manual"
    return "expired"
