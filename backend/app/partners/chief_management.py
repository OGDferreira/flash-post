"""Chief management service: allows chief to manage partners' folders and loops."""

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Affiliation,
    InstagramAccount,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramProfileFolder,
    User,
    Workspace,
    WorkspaceMember,
)
from app.partners.service import owner_workspace, partner_link


async def is_chief_of_partner(
    db: AsyncSession, chief_user_id: uuid.UUID, partner_user_id: uuid.UUID
) -> bool:
    """Check if chief_user_id is the chief of partner_user_id."""
    link = await db.scalar(
        select(Affiliation).where(
            Affiliation.chief_user_id == chief_user_id,
            Affiliation.affiliate_user_id == partner_user_id,
            Affiliation.status == "ACTIVE",
        )
    )
    return link is not None


async def get_partner_workspace(
    db: AsyncSession, partner_user_id: uuid.UUID
) -> Workspace | None:
    """Get the workspace of a partner."""
    return await owner_workspace(db, partner_user_id)


async def can_chief_manage_partner(
    db: AsyncSession, chief_user_id: uuid.UUID, partner_workspace_id: uuid.UUID
) -> bool:
    """Check if chief can manage a specific partner workspace."""
    # Get the partner workspace
    workspace = await db.scalar(
        select(Workspace).where(Workspace.id == partner_workspace_id)
    )
    if not workspace:
        return False

    # Check if chief is the chief of the workspace owner
    return await is_chief_of_partner(db, chief_user_id, workspace.owner_id)


async def get_chief_partners(db: AsyncSession, chief_user_id: uuid.UUID) -> list[dict]:
    """Get all active partners of a chief with their workspace info."""
    affiliations = await db.scalars(
        select(Affiliation).where(
            Affiliation.chief_user_id == chief_user_id,
            Affiliation.status == "ACTIVE",
        )
    )

    partners = []
    for aff in affiliations:
        partner_user = await db.scalar(
            select(User).where(User.id == aff.affiliate_user_id)
        )
        if not partner_user:
            continue

        workspace = await owner_workspace(db, partner_user.id)
        if not workspace:
            continue

        # Count accounts
        account_count = await db.scalar(
            select(select(InstagramAccount).where(
                InstagramAccount.workspace_id == workspace.id,
                InstagramAccount.status == "connected",
            ).count())
        ) or 0

        # Count folders
        folder_count = await db.scalar(
            select(select(InstagramProfileFolder).where(
                InstagramProfileFolder.workspace_id == workspace.id
            ).count())
        ) or 0

        # Count loops
        loop_count = await db.scalar(
            select(select(InstagramLoop).where(
                InstagramLoop.workspace_id == workspace.id
            ).count())
        ) or 0

        partners.append({
            "user_id": str(partner_user.id),
            "user_name": partner_user.full_name,
            "user_email": partner_user.email,
            "user_nickname": partner_user.nickname,
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
            "account_count": account_count,
            "folder_count": folder_count,
            "loop_count": loop_count,
            "since": aff.created_at.isoformat(),
        })

    return partners


async def get_partner_folders(
    db: AsyncSession, partner_workspace_id: uuid.UUID
) -> list[InstagramProfileFolder]:
    """Get all folders of a partner workspace."""
    folders = await db.scalars(
        select(InstagramProfileFolder).where(
            InstagramProfileFolder.workspace_id == partner_workspace_id
        ).order_by(InstagramProfileFolder.name)
    )
    return list(folders)


async def get_partner_accounts(
    db: AsyncSession, partner_workspace_id: uuid.UUID, folder_id: uuid.UUID | None = None
) -> list[InstagramAccount]:
    """Get accounts of a partner workspace, optionally filtered by folder."""
    query = select(InstagramAccount).where(
        InstagramAccount.workspace_id == partner_workspace_id
    )

    if folder_id is not None:
        query = query.where(InstagramAccount.profile_folder_id == folder_id)

    accounts = await db.scalars(query.order_by(InstagramAccount.username))
    return list(accounts)


async def get_partner_loops(
    db: AsyncSession, partner_workspace_id: uuid.UUID
) -> list[InstagramLoop]:
    """Get all loops of a partner workspace."""
    loops = await db.scalars(
        select(InstagramLoop).where(
            InstagramLoop.workspace_id == partner_workspace_id
        ).order_by(InstagramLoop.name)
    )
    return list(loops)


async def create_partner_folder(
    db: AsyncSession,
    partner_workspace_id: uuid.UUID,
    name: str,
    color: str = "#00c9d8",
    auto_prefixes: list[str] | None = None,
    auto_enabled: bool = True,
) -> InstagramProfileFolder:
    """Create a folder in a partner's workspace."""
    folder = InstagramProfileFolder(
        workspace_id=partner_workspace_id,
        name=name,
        color=color,
        auto_prefixes=auto_prefixes or [],
        auto_enabled=auto_enabled,
    )
    db.add(folder)
    await db.flush()
    return folder


async def assign_account_to_folder(
    db: AsyncSession,
    account_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    partner_workspace_id: uuid.UUID,
) -> InstagramAccount:
    """Assign an account to a folder (or remove from folder if folder_id is None)."""
    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.id == account_id,
            InstagramAccount.workspace_id == partner_workspace_id,
        )
    )

    if not account:
        raise ValueError("Account not found or does not belong to this workspace")

    # If folder_id is provided, verify it belongs to the same workspace
    if folder_id is not None:
        folder = await db.scalar(
            select(InstagramProfileFolder).where(
                InstagramProfileFolder.id == folder_id,
                InstagramProfileFolder.workspace_id == partner_workspace_id,
            )
        )
        if not folder:
            raise ValueError("Folder not found or does not belong to this workspace")

    account.profile_folder_id = folder_id
    await db.flush()
    return account


async def get_loop_accounts(
    db: AsyncSession, loop_id: uuid.UUID
) -> list[InstagramLoopAccount]:
    """Get all accounts assigned to a loop."""
    loop_accounts = await db.scalars(
        select(InstagramLoopAccount).where(
            InstagramLoopAccount.loop_id == loop_id
        ).order_by(InstagramLoopAccount.created_at)
    )
    return list(loop_accounts)


async def add_account_to_loop(
    db: AsyncSession,
    loop_id: uuid.UUID,
    account_id: uuid.UUID,
    partner_workspace_id: uuid.UUID,
) -> InstagramLoopAccount:
    """Add an account to a loop."""
    # Verify loop belongs to the workspace
    loop = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == partner_workspace_id,
        )
    )
    if not loop:
        raise ValueError("Loop not found or does not belong to this workspace")

    # Verify account belongs to the workspace
    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.id == account_id,
            InstagramAccount.workspace_id == partner_workspace_id,
        )
    )
    if not account:
        raise ValueError("Account not found or does not belong to this workspace")

    # Check if already exists
    existing = await db.scalar(
        select(InstagramLoopAccount).where(
            InstagramLoopAccount.loop_id == loop_id,
            InstagramLoopAccount.account_id == account_id,
        )
    )
    if existing:
        return existing

    # Create the association
    loop_account = InstagramLoopAccount(
        loop_id=loop_id,
        account_id=account_id,
    )
    db.add(loop_account)
    await db.flush()
    return loop_account


async def remove_account_from_loop(
    db: AsyncSession,
    loop_id: uuid.UUID,
    account_id: uuid.UUID,
    partner_workspace_id: uuid.UUID,
) -> bool:
    """Remove an account from a loop."""
    # Verify loop belongs to the workspace
    loop = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.id == loop_id,
            InstagramLoop.workspace_id == partner_workspace_id,
        )
    )
    if not loop:
        raise ValueError("Loop not found or does not belong to this workspace")

    # Delete the association
    from sqlalchemy import delete as sql_delete
    result = await db.execute(
        sql_delete(InstagramLoopAccount).where(
            InstagramLoopAccount.loop_id == loop_id,
            InstagramLoopAccount.account_id == account_id,
        )
    )

    await db.flush()
    return result.rowcount > 0
