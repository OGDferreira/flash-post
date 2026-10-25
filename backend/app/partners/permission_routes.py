"""Routes for partner permission management."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import DbSession, SuperAdminUser, require_csrf
from app.partners import permissions as perm_service

router = APIRouter(prefix="/api/admin/partner-permissions", tags=["Admin Partner Permissions"])


class PermissionUpdate(BaseModel):
    user_id: str
    platform: Literal["flashpost", "flashbot"]
    permissions: dict[str, bool]


class PermissionsResponse(BaseModel):
    user_id: str
    flashpost: dict[str, bool]
    flashbot: dict[str, bool]


@router.get("/{user_id}")
async def get_permissions(
    user_id: str,
    _admin: SuperAdminUser,
    db: DbSession,
) -> PermissionsResponse:
    """Get all permissions for a partner."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    # Check if user is a partner
    if not await perm_service.is_partner(db, uid):
        raise HTTPException(400, "User is not a partner")

    # Get permissions for both platforms
    perms = await perm_service.get_all_partner_permissions(db, uid)

    return PermissionsResponse(
        user_id=user_id,
        flashpost=perm_service.serialize_permissions(perms.get("flashpost")),
        flashbot=perm_service.serialize_permissions(perms.get("flashbot")),
    )


@router.put("")
async def update_permissions(
    data: PermissionUpdate,
    _admin: SuperAdminUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Update permissions for a partner on a specific platform."""
    try:
        user_id = uuid.UUID(data.user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    # Check if user is a partner
    if not await perm_service.is_partner(db, user_id):
        raise HTTPException(400, "User is not a partner")

    # Update permissions
    perm = await perm_service.update_partner_permissions(
        db, user_id, data.platform, data.permissions
    )
    await db.commit()

    return {
        "success": True,
        "platform": data.platform,
        "permissions": perm_service.serialize_permissions(perm),
    }


@router.post("/initialize/{user_id}")
async def initialize_permissions(
    user_id: str,
    _admin: SuperAdminUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Initialize default permissions for a partner."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    # Check if user is a partner
    if not await perm_service.is_partner(db, uid):
        raise HTTPException(400, "User is not a partner")

    # Create default permissions for both platforms
    fp_perm = await perm_service.ensure_partner_permissions(db, uid, "flashpost")
    fb_perm = await perm_service.ensure_partner_permissions(db, uid, "flashbot")
    await db.commit()

    return {
        "success": True,
        "flashpost": perm_service.serialize_permissions(fp_perm),
        "flashbot": perm_service.serialize_permissions(fb_perm),
    }
