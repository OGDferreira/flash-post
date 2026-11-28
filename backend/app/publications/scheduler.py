"""Background worker for one-off scheduled publications (feed posts and stories).

Each tick claims one due per-account target, publishes it through the same
publishing engine the loops use, and records the result. One account failing
never blocks the others; a target retries a few times before it is marked failed.
When every target of a post reaches a terminal state the post is marked done.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.core.crypto import decrypt_value
from app.core.database import get_session_factory
from app.instagram.publishing import InstagramPublishingError, publish_media
from app.instagram.storage import SupabaseStorage
from app.loops.scheduler import workspaces_allowed_to_post
from app.models import (
    InstagramAccount,
    InstagramCommentAutomation,
    InstagramMedia,
    InstagramScheduledPost,
    InstagramScheduledPostTarget,
)
from app.models.instagram_scheduled_post import (
    KIND_STORY,
    POST_DONE,
    POST_PUBLISHING,
    TARGET_FAILED,
    TARGET_PUBLISHED,
    TARGET_PUBLISHING,
    TARGET_QUEUED,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# How many due targets one tick drains before yielding.
MAX_PER_TICK = 20


async def _arm_automation(db, template_id, account_id, published_media_id: str) -> None:
    """Clone the chosen ManyChat rule, scoped to the just-published post+account.

    Best-effort: a per-post copy means the keyword automation answers comments on
    exactly this post, without touching the owner's template rule. Idempotent on
    (template, published media)."""
    template = await db.get(InstagramCommentAutomation, template_id)
    if template is None or template.trigger_type != "comment":
        return
    # Published media ids are unique per account+post, so this is a clean dedupe
    # against a retried publish arming the same post twice.
    exists = await db.scalar(
        select(InstagramCommentAutomation.id).where(
            InstagramCommentAutomation.workspace_id == template.workspace_id,
            InstagramCommentAutomation.media_id == published_media_id[:191],
        )
    )
    if exists is not None:
        return
    clone = InstagramCommentAutomation(
        workspace_id=template.workspace_id,
        created_by_user_id=template.created_by_user_id,
        name=f"{template.name} · post"[:120],
        enabled=True,
        trigger_type="comment",
        instagram_account_id=account_id,
        scope_account_ids=[str(account_id)],
        scope_folder_ids=[],
        keywords=list(template.keywords or []),
        match_mode=template.match_mode,
        media_id=published_media_id[:191],
        public_reply_enabled=template.public_reply_enabled,
        public_replies=list(template.public_replies or []),
        dm_enabled=template.dm_enabled,
        dm_text=template.dm_text,
        dm_texts=list(template.dm_texts or []),
        dm_buttons=list(template.dm_buttons or []),
    )
    db.add(clone)


async def _refresh_post_status(db, post_id) -> None:
    """Mark the post done once no target is still queued/publishing."""
    pending = await db.scalar(
        select(InstagramScheduledPostTarget.id).where(
            InstagramScheduledPostTarget.post_id == post_id,
            InstagramScheduledPostTarget.status.in_((TARGET_QUEUED, TARGET_PUBLISHING)),
        ).limit(1)
    )
    post = await db.get(InstagramScheduledPost, post_id)
    if post is None or post.status == POST_DONE:
        return
    post.status = POST_DONE if pending is None else POST_PUBLISHING


async def process_one_due_scheduled_target(now: datetime | None = None) -> bool:
    """Publish one due target. Returns True if one was handled (so the caller loops)."""
    current = now or datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        row = await db.execute(
            select(InstagramScheduledPostTarget, InstagramScheduledPost)
            .join(InstagramScheduledPost, InstagramScheduledPost.id == InstagramScheduledPostTarget.post_id)
            .where(
                InstagramScheduledPostTarget.status == TARGET_QUEUED,
                InstagramScheduledPost.scheduled_for <= current,
                InstagramScheduledPost.status.in_(("scheduled", "publishing")),
                InstagramScheduledPostTarget.workspace_id.in_(workspaces_allowed_to_post()),
            )
            .order_by(InstagramScheduledPost.scheduled_for, InstagramScheduledPostTarget.id)
            .with_for_update(skip_locked=True, of=InstagramScheduledPostTarget)
            .limit(1)
        )
        found = row.first()
        if found is None:
            return False
        target, post = found
        account = await db.scalar(
            select(InstagramAccount).where(
                InstagramAccount.id == target.account_id,
                InstagramAccount.workspace_id == target.workspace_id,
            )
        )
        media = await db.scalar(
            select(InstagramMedia).where(InstagramMedia.id == post.media_id)
        )
        cover = None
        if post.thumbnail_media_id is not None:
            cover = await db.scalar(
                select(InstagramMedia).where(InstagramMedia.id == post.thumbnail_media_id)
            )
        if account is None or media is None:
            target.status = TARGET_FAILED
            target.last_error = "Conta conectada ou mídia não está mais disponível."
            await _refresh_post_status(db, post.id)
            await db.commit()
            return True
        try:
            access_token = decrypt_value(account.encrypted_access_token or "")
        except (RuntimeError, ValueError):
            target.status = TARGET_FAILED
            target.last_error = "Não foi possível ler o token da conta; reconecte-a."
            await _refresh_post_status(db, post.id)
            await db.commit()
            return True
        try:
            storage = SupabaseStorage.from_settings()
        except (RuntimeError, ValueError):
            # Storage misconfigured: leave queued, try again next tick.
            logger.error("Scheduled target %s: media storage unavailable.", target.id)
            return False

        target.status = TARGET_PUBLISHING
        target.attempts += 1
        target.last_error = None
        if post.status == "scheduled":
            post.status = POST_PUBLISHING
        await db.commit()
        target_id = target.id
        post_id = post.id
        is_story = post.kind == KIND_STORY
        caption = post.caption if not is_story else None
        # Stories take no cover; only feed posts arm a per-post automation.
        cover_media = cover if not is_story else None
        automation_id = post.automation_id if not is_story else None
        account_id = account.id
        attempts = target.attempts

    try:
        published_media_id = await publish_media(
            account, media, access_token, storage, caption=caption, cover=cover_media, story=is_story,
        )
    except Exception as exc:  # noqa: BLE001 - one target never stops the rest
        async with get_session_factory()() as db:
            target = await db.get(InstagramScheduledPostTarget, target_id)
            if target is not None:
                definitive = isinstance(exc, InstagramPublishingError)
                if attempts >= MAX_ATTEMPTS or definitive:
                    target.status = TARGET_FAILED
                    target.last_error = str(exc)[:500]
                else:
                    target.status = TARGET_QUEUED  # retry next tick
                    target.last_error = str(exc)[:500]
                await _refresh_post_status(db, target.post_id)
                await db.commit()
        logger.warning("Scheduled target %s publish failed (attempt %s): %s", target_id, attempts, exc)
        return True

    async with get_session_factory()() as db:
        target = await db.get(InstagramScheduledPostTarget, target_id)
        if target is not None:
            target.status = TARGET_PUBLISHED
            target.published_media_id = str(published_media_id)[:191]
            target.published_at = datetime.now(timezone.utc)
            await _refresh_post_status(db, post_id)
            if automation_id is not None:
                await _arm_automation(db, automation_id, account_id, str(published_media_id))
            await db.commit()
    logger.info(
        "Scheduled %s published to account %s (media %s -> %s).",
        "story" if is_story else "post", account.username, media.id, published_media_id,
    )
    return True


async def run_due_scheduled_posts(now: datetime | None = None) -> int:
    """Drain up to MAX_PER_TICK due targets. Returns how many were handled."""
    handled = 0
    for _ in range(MAX_PER_TICK):
        if not await process_one_due_scheduled_target(now):
            break
        handled += 1
    return handled
