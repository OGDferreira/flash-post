"""Folder auto-detect and loop auto-join.

Two rules, both opt-out:
* A folder may list name prefixes; a newly connected account whose @username
  starts with one of them is filed in that folder (unless the folder's switch
  is off). Existing accounts and accounts already in a folder are not touched.
* A loop may list folders; every account that is in one of them joins the loop
  (and is queued if the loop is active). Accounts are never removed
  automatically.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramProfileFolder,
)

MAX_PREFIXES = 30
MAX_PREFIX_LENGTH = 40


def normalize_prefixes(values: list[str] | None) -> list[str]:
    """Lower-case, trimmed, without '@', unique, in the given order."""
    clean: list[str] = []
    for raw in values or []:
        item = re.sub(r"^@+", "", str(raw).strip().lower())[:MAX_PREFIX_LENGTH]
        if item and item not in clean:
            clean.append(item)
    return clean[:MAX_PREFIXES]


def matches(username: str, prefixes: list[str]) -> bool:
    name = username.strip().lower().lstrip("@")
    return any(prefix and name.startswith(prefix) for prefix in prefixes)


async def file_new_account(db: AsyncSession, account: InstagramAccount) -> InstagramProfileFolder | None:
    """Put a folderless account in the first folder whose rule matches."""
    if account.profile_folder_id is not None:
        return None
    folders = (
        await db.scalars(
            select(InstagramProfileFolder)
            .where(
                InstagramProfileFolder.workspace_id == account.workspace_id,
                InstagramProfileFolder.auto_enabled.is_(True),
            )
            .order_by(InstagramProfileFolder.name)
        )
    ).all()
    for folder in folders:
        if matches(account.username, normalize_prefixes(folder.auto_prefixes)):
            account.profile_folder_id = folder.id
            return folder
    return None


async def join_auto_loops(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    folder_id: uuid.UUID,
    accounts: list[InstagramAccount],
    now: datetime,
) -> int:
    """Add the given accounts (all in `folder_id`) to loops that watch it."""
    from app.loops.scheduler import enqueue_loop_publications_now

    if not accounts:
        return 0
    loops = (
        await db.scalars(select(InstagramLoop).where(InstagramLoop.workspace_id == workspace_id))
    ).all()
    joined = 0
    for loop in loops:
        if str(folder_id) not in {str(item) for item in (loop.auto_folder_ids or [])}:
            continue
        existing = set(
            (
                await db.scalars(
                    select(InstagramLoopAccount.account_id).where(InstagramLoopAccount.loop_id == loop.id)
                )
            ).all()
        )
        fresh = [account for account in accounts if account.id not in existing]
        for account in fresh:
            db.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
        if fresh:
            await db.flush()
            joined += len(fresh)
            if loop.status == "active":
                await enqueue_loop_publications_now(db, loop, fresh, now=now)
    return joined


async def folder_accounts(
    db: AsyncSession, workspace_id: uuid.UUID, folder_ids: list
) -> list[InstagramAccount]:
    """Connected accounts that sit in any of the given folders."""
    ids = [uuid.UUID(str(item)) for item in folder_ids or []]
    if not ids:
        return []
    return list(
        (
            await db.scalars(
                select(InstagramAccount).where(
                    InstagramAccount.workspace_id == workspace_id,
                    InstagramAccount.profile_folder_id.in_(ids),
                    InstagramAccount.status == "connected",
                    InstagramAccount.encrypted_access_token.is_not(None),
                )
            )
        ).all()
    )


async def automate_account(db: AsyncSession, account: InstagramAccount, now: datetime) -> None:
    """Run both rules for one account (call after it was created or filed)."""
    await file_new_account(db, account)
    if account.profile_folder_id is not None:
        await join_auto_loops(db, account.workspace_id, account.profile_folder_id, [account], now)
