"""CRUD for one-off scheduled publications (feed posts and stories).

An owner schedules a media to a set of accounts (picked directly or by folder),
at a chosen time, as a feed post or a story. Folders are expanded to their
accounts when the post is created.
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.models import (
    InstagramAccount,
    InstagramMedia,
    InstagramScheduledPost,
    InstagramScheduledPostTarget,
)
from app.models.instagram_scheduled_post import (
    KIND_POST,
    KIND_STORY,
    POST_CANCELED,
    POST_SCHEDULED,
    TARGET_CANCELED,
    TARGET_QUEUED,
)

router = APIRouter(prefix="/api/publications", tags=["Instagram publications"])
csrf = [Depends(require_csrf)]


class CreatePost(BaseModel):
    media_id: uuid.UUID
    kind: Literal["post", "story"] = "post"
    caption: Annotated[str | None, Field(max_length=2200)] = None
    scheduled_for: datetime
    account_ids: Annotated[list[uuid.UUID], Field(max_length=500)] = []
    folder_ids: Annotated[list[uuid.UUID], Field(max_length=100)] = []


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _resolve_accounts(db, workspace_id, body: CreatePost) -> list[uuid.UUID]:
    """Union of the directly-picked accounts and every account in the picked folders."""
    wanted: set[uuid.UUID] = set()
    conditions = []
    if body.account_ids:
        conditions.append(InstagramAccount.id.in_(body.account_ids))
    if body.folder_ids:
        conditions.append(InstagramAccount.profile_folder_id.in_(body.folder_ids))
    if not conditions:
        return []
    from sqlalchemy import or_

    rows = await db.scalars(
        select(InstagramAccount.id).where(
            InstagramAccount.workspace_id == workspace_id,
            or_(*conditions),
        )
    )
    wanted.update(rows)
    return list(wanted)


def _summary(post: InstagramScheduledPost, counts: dict[str, int]) -> dict:
    return {
        "id": str(post.id),
        "media_id": str(post.media_id) if post.media_id else None,
        "kind": post.kind,
        "caption": post.caption,
        "scheduled_for": _aware(post.scheduled_for).isoformat(),
        "status": post.status,
        "created_at": _aware(post.created_at).isoformat() if post.created_at else None,
        "targets": {
            "total": sum(counts.values()),
            "queued": counts.get(TARGET_QUEUED, 0),
            "publishing": counts.get("publishing", 0),
            "published": counts.get("published", 0),
            "failed": counts.get("failed", 0),
            "canceled": counts.get(TARGET_CANCELED, 0),
        },
    }


@router.get("")
async def list_posts(access: OwnerAccess, db: DbSession) -> dict:
    posts = list(
        await db.scalars(
            select(InstagramScheduledPost)
            .where(InstagramScheduledPost.workspace_id == access.workspace.id)
            .order_by(InstagramScheduledPost.scheduled_for.desc())
            .limit(100)
        )
    )
    counts_rows = await db.execute(
        select(
            InstagramScheduledPostTarget.post_id,
            InstagramScheduledPostTarget.status,
            func.count(),
        )
        .where(InstagramScheduledPostTarget.workspace_id == access.workspace.id)
        .group_by(InstagramScheduledPostTarget.post_id, InstagramScheduledPostTarget.status)
    )
    by_post: dict[uuid.UUID, dict[str, int]] = {}
    for post_id, st, n in counts_rows:
        by_post.setdefault(post_id, {})[st] = n
    return {"publications": [_summary(p, by_post.get(p.id, {})) for p in posts]}


@router.post("", dependencies=csrf, status_code=status.HTTP_201_CREATED)
async def create_post(body: CreatePost, access: OwnerAccess, db: DbSession) -> dict:
    media = await db.scalar(
        select(InstagramMedia).where(
            InstagramMedia.id == body.media_id,
            InstagramMedia.workspace_id == access.workspace.id,
        )
    )
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mídia não encontrada.")
    when = _aware(body.scheduled_for)
    if when < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A data precisa ser no futuro.")
    account_ids = await _resolve_accounts(db, access.workspace.id, body)
    if not account_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Escolha pelo menos uma conta ou pasta com contas.")

    post = InstagramScheduledPost(
        workspace_id=access.workspace.id,
        created_by_user_id=access.membership.user_id,
        media_id=media.id,
        kind=KIND_STORY if body.kind == "story" else KIND_POST,
        caption=(body.caption or "").strip() or None if body.kind == "post" else None,
        scheduled_for=when,
        status=POST_SCHEDULED,
    )
    db.add(post)
    await db.flush()
    for account_id in account_ids:
        db.add(InstagramScheduledPostTarget(
            post_id=post.id, workspace_id=access.workspace.id,
            account_id=account_id, status=TARGET_QUEUED,
        ))
    await db.commit()
    await db.refresh(post)
    return _summary(post, {TARGET_QUEUED: len(account_ids)})


@router.delete("/{post_id}", dependencies=csrf)
async def cancel_post(post_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    post = await db.get(InstagramScheduledPost, post_id)
    if post is None or post.workspace_id != access.workspace.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicação não encontrada.")
    post.status = POST_CANCELED
    # Cancel only targets that have not started/finished; leave published/failed as they are.
    for target in await db.scalars(
        select(InstagramScheduledPostTarget).where(
            InstagramScheduledPostTarget.post_id == post.id,
            InstagramScheduledPostTarget.status == TARGET_QUEUED,
        )
    ):
        target.status = TARGET_CANCELED
    await db.commit()
    return {"ok": True}
