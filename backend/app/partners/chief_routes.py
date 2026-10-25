"""Chief management routes: allows chief to manage partners' folders and loops."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import AuthenticatedUser, DbSession, require_csrf
from app.partners import chief_management as chief_svc
from app.partners.service import is_chief


router = APIRouter(prefix="/api/chief/partners", tags=["Chief Partner Management"])


class FolderCreateRequest(BaseModel):
    name: str
    color: str = "#00c9d8"
    auto_prefixes: list[str] = []
    auto_enabled: bool = True


class AssignAccountToFolderRequest(BaseModel):
    account_id: str
    folder_id: str | None  # None to remove from folder


class LoopAccountRequest(BaseModel):
    account_id: str


@router.get("")
async def list_partners(
    user: AuthenticatedUser,
    db: DbSession,
) -> dict:
    """List all partners of the current chief."""
    # Verify user is a chief
    if not await is_chief(db, user.id):
        raise HTTPException(403, "Only chiefs can access partner management")

    partners = await chief_svc.get_chief_partners(db, user.id)

    return {
        "partners": partners,
        "count": len(partners),
    }


@router.get("/{partner_workspace_id}/folders")
async def list_partner_folders(
    partner_workspace_id: str,
    user: AuthenticatedUser,
    db: DbSession,
) -> dict:
    """List all folders of a partner."""
    try:
        workspace_id = uuid.UUID(partner_workspace_id)
    except ValueError:
        raise HTTPException(400, "Invalid workspace ID")

    # Verify chief can manage this partner
    if not await chief_svc.can_chief_manage_partner(db, user.id, workspace_id):
        raise HTTPException(403, "You can only manage your own partners")

    folders = await chief_svc.get_partner_folders(db, workspace_id)

    return {
        "folders": [
            {
                "id": str(f.id),
                "name": f.name,
                "color": f.color,
                "auto_prefixes": list(f.auto_prefixes or []),
                "auto_enabled": f.auto_enabled,
                "created_at": f.created_at.isoformat(),
            }
            for f in folders
        ],
    }


@router.post("/{partner_workspace_id}/folders")
async def create_partner_folder(
    partner_workspace_id: str,
    data: FolderCreateRequest,
    user: AuthenticatedUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Create a folder in a partner's workspace."""
    try:
        workspace_id = uuid.UUID(partner_workspace_id)
    except ValueError:
        raise HTTPException(400, "Invalid workspace ID")

    # Verify chief can manage this partner
    if not await chief_svc.can_chief_manage_partner(db, user.id, workspace_id):
        raise HTTPException(403, "You can only manage your own partners")

    folder = await chief_svc.create_partner_folder(
        db, workspace_id, data.name, data.color, data.auto_prefixes, data.auto_enabled
    )
    await db.commit()

    return {
        "success": True,
        "folder": {
            "id": str(folder.id),
            "name": folder.name,
            "color": folder.color,
            "auto_prefixes": list(folder.auto_prefixes or []),
            "auto_enabled": folder.auto_enabled,
        },
    }


@router.get("/{partner_workspace_id}/accounts")
async def list_partner_accounts(
    partner_workspace_id: str,
    user: AuthenticatedUser,
    db: DbSession,
    folder_id: str | None = None,
) -> dict:
    """List accounts of a partner, optionally filtered by folder."""
    try:
        workspace_id = uuid.UUID(partner_workspace_id)
        folder_uuid = uuid.UUID(folder_id) if folder_id else None
    except ValueError:
        raise HTTPException(400, "Invalid ID format")

    # Verify chief can manage this partner
    if not await chief_svc.can_chief_manage_partner(db, user.id, workspace_id):
        raise HTTPException(403, "You can only manage your own partners")

    accounts = await chief_svc.get_partner_accounts(db, workspace_id, folder_uuid)

    return {
        "accounts": [
            {
                "id": str(a.id),
                "username": a.username,
                "profile_picture_url": a.profile_picture_url,
                "status": a.status,
                "folder_id": str(a.profile_folder_id) if a.profile_folder_id else None,
                "follower_count": a.follower_count,
                "connected_at": a.connected_at.isoformat(),
            }
            for a in accounts
        ],
    }


@router.put("/{partner_workspace_id}/accounts/assign-folder")
async def assign_account_to_folder(
    partner_workspace_id: str,
    data: AssignAccountToFolderRequest,
    user: AuthenticatedUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Assign an account to a folder (or remove from folder)."""
    try:
        workspace_id = uuid.UUID(partner_workspace_id)
        account_id = uuid.UUID(data.account_id)
        folder_id = uuid.UUID(data.folder_id) if data.folder_id else None
    except ValueError:
        raise HTTPException(400, "Invalid ID format")

    # Verify chief can manage this partner
    if not await chief_svc.can_chief_manage_partner(db, user.id, workspace_id):
        raise HTTPException(403, "You can only manage your own partners")

    try:
        account = await chief_svc.assign_account_to_folder(
            db, account_id, folder_id, workspace_id
        )
        await db.commit()

        return {
            "success": True,
            "account_id": str(account.id),
            "folder_id": str(account.profile_folder_id) if account.profile_folder_id else None,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{partner_workspace_id}/loops")
async def list_partner_loops(
    partner_workspace_id: str,
    user: AuthenticatedUser,
    db: DbSession,
) -> dict:
    """List all loops of a partner."""
    try:
        workspace_id = uuid.UUID(partner_workspace_id)
    except ValueError:
        raise HTTPException(400, "Invalid workspace ID")

    # Verify chief can manage this partner
    if not await chief_svc.can_chief_manage_partner(db, user.id, workspace_id):
        raise HTTPException(403, "You can only manage your own partners")

    loops = await chief_svc.get_partner_loops(db, workspace_id)

    return {
        "loops": [
            {
                "id": str(loop.id),
                "name": loop.name,
                "status": loop.status,
                "post_type": loop.post_type,
                "interval_min_minutes": loop.interval_min_minutes,
                "interval_max_minutes": loop.interval_max_minutes,
                "linked": loop.linked,
                "shared": loop.shared,
                "created_at": loop.created_at.isoformat(),
            }
            for loop in loops
        ],
    }


@router.get("/{partner_workspace_id}/loops/{loop_id}/accounts")
async def list_loop_accounts(
    partner_workspace_id: str,
    loop_id: str,
    user: AuthenticatedUser,
    db: DbSession,
) -> dict:
    """List accounts assigned to a loop."""
    try:
        workspace_id = uuid.UUID(partner_workspace_id)
        loop_uuid = uuid.UUID(loop_id)
    except ValueError:
        raise HTTPException(400, "Invalid ID format")

    # Verify chief can manage this partner
    if not await chief_svc.can_chief_manage_partner(db, user.id, workspace_id):
        raise HTTPException(403, "You can only manage your own partners")

    loop_accounts = await chief_svc.get_loop_accounts(db, loop_uuid)

    # Get account details
    from app.models import InstagramAccount
    from sqlalchemy import select

    account_ids = [la.account_id for la in loop_accounts]
    accounts = await db.scalars(
        select(InstagramAccount).where(InstagramAccount.id.in_(account_ids or [uuid.uuid4()]))
    )
    accounts_dict = {str(a.id): a for a in accounts}

    return {
        "loop_id": loop_id,
        "accounts": [
            {
                "loop_account_id": str(la.id),
                "account_id": str(la.account_id),
                "username": accounts_dict[str(la.account_id)].username if str(la.account_id) in accounts_dict else "Unknown",
                "added_at": la.created_at.isoformat(),
            }
            for la in loop_accounts
        ],
    }


@router.post("/{partner_workspace_id}/loops/{loop_id}/accounts")
async def add_account_to_loop(
    partner_workspace_id: str,
    loop_id: str,
    data: LoopAccountRequest,
    user: AuthenticatedUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Add an account to a loop."""
    try:
        workspace_id = uuid.UUID(partner_workspace_id)
        loop_uuid = uuid.UUID(loop_id)
        account_id = uuid.UUID(data.account_id)
    except ValueError:
        raise HTTPException(400, "Invalid ID format")

    # Verify chief can manage this partner
    if not await chief_svc.can_chief_manage_partner(db, user.id, workspace_id):
        raise HTTPException(403, "You can only manage your own partners")

    try:
        loop_account = await chief_svc.add_account_to_loop(
            db, loop_uuid, account_id, workspace_id
        )
        await db.commit()

        return {
            "success": True,
            "loop_account_id": str(loop_account.id),
            "account_id": str(loop_account.account_id),
            "loop_id": str(loop_account.loop_id),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{partner_workspace_id}/loops/{loop_id}/accounts/{account_id}")
async def remove_account_from_loop(
    partner_workspace_id: str,
    loop_id: str,
    account_id: str,
    user: AuthenticatedUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Remove an account from a loop."""
    try:
        workspace_id = uuid.UUID(partner_workspace_id)
        loop_uuid = uuid.UUID(loop_id)
        account_uuid = uuid.UUID(account_id)
    except ValueError:
        raise HTTPException(400, "Invalid ID format")

    # Verify chief can manage this partner
    if not await chief_svc.can_chief_manage_partner(db, user.id, workspace_id):
        raise HTTPException(403, "You can only manage your own partners")

    try:
        removed = await chief_svc.remove_account_from_loop(
            db, loop_uuid, account_uuid, workspace_id
        )
        await db.commit()

        return {
            "success": True,
            "removed": removed,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
