"""Partner permission management and validation."""

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PartnerPermission, Affiliation, User


PlatformType = Literal["flashpost", "flashbot"]


async def get_partner_permissions(
    db: AsyncSession,
    user_id: uuid.UUID,
    platform: PlatformType
) -> PartnerPermission | None:
    """Get partner permissions for a specific platform."""
    return await db.scalar(
        select(PartnerPermission).where(
            PartnerPermission.user_id == user_id,
            PartnerPermission.platform == platform
        )
    )


async def get_all_partner_permissions(
    db: AsyncSession,
    user_id: uuid.UUID
) -> dict[str, PartnerPermission]:
    """Get all permissions for a partner (both platforms)."""
    perms = await db.scalars(
        select(PartnerPermission).where(PartnerPermission.user_id == user_id)
    )
    return {p.platform: p for p in perms}


async def ensure_partner_permissions(
    db: AsyncSession,
    user_id: uuid.UUID,
    platform: PlatformType
) -> PartnerPermission:
    """Get or create default permissions for a partner."""
    existing = await get_partner_permissions(db, user_id, platform)
    if existing:
        return existing

    # Create default permissions (only dashboard access)
    perm = PartnerPermission(
        user_id=user_id,
        platform=platform,
        can_view_dashboard=True,
        can_view_ranking=False,
        can_view_accounts=False,
        can_view_meta_apps=False,
        can_view_settings=False,
        can_view_contact=False,
        can_view_bot_dashboard=True,
        can_view_leads=False,
        can_view_wallets=False,
    )
    db.add(perm)
    await db.flush()
    return perm


async def update_partner_permissions(
    db: AsyncSession,
    user_id: uuid.UUID,
    platform: PlatformType,
    permissions: dict[str, bool]
) -> PartnerPermission:
    """Update partner permissions for a platform."""
    perm = await ensure_partner_permissions(db, user_id, platform)

    # Update only the fields that were provided
    for key, value in permissions.items():
        if hasattr(perm, key) and isinstance(value, bool):
            setattr(perm, key, value)

    await db.flush()
    return perm


async def is_partner(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Check if a user is an active partner."""
    link = await db.scalar(
        select(Affiliation).where(
            Affiliation.affiliate_user_id == user_id,
            Affiliation.status == "ACTIVE"
        )
    )
    return link is not None


async def has_permission(
    db: AsyncSession,
    user_id: uuid.UUID,
    platform: PlatformType,
    permission: str
) -> bool:
    """Check if a partner has a specific permission."""
    # Super admins have all permissions
    user = await db.scalar(select(User).where(User.id == user_id))
    if user and user.platform_role == "SUPER_ADMIN":
        return True

    # Check if user is a partner
    if not await is_partner(db, user_id):
        # Not a partner, check if they're a regular owner (full access)
        return True  # Non-partners have full access to their own workspace

    # Get partner permissions
    perm = await get_partner_permissions(db, user_id, platform)
    if not perm:
        # No explicit permissions set, default to dashboard only
        return permission in ["can_view_dashboard", "can_view_bot_dashboard"]

    return getattr(perm, permission, False)


def serialize_permissions(perm: PartnerPermission | None) -> dict:
    """Serialize permissions to JSON format."""
    if not perm:
        return {
            "can_view_dashboard": True,
            "can_view_ranking": False,
            "can_view_accounts": False,
            "can_view_meta_apps": False,
            "can_view_settings": False,
            "can_view_contact": False,
            "can_view_bot_dashboard": True,
            "can_view_leads": False,
            "can_view_wallets": False,
        }

    return {
        "can_view_dashboard": perm.can_view_dashboard,
        "can_view_ranking": perm.can_view_ranking,
        "can_view_accounts": perm.can_view_accounts,
        "can_view_meta_apps": perm.can_view_meta_apps,
        "can_view_settings": perm.can_view_settings,
        "can_view_contact": perm.can_view_contact,
        "can_view_bot_dashboard": perm.can_view_bot_dashboard,
        "can_view_leads": perm.can_view_leads,
        "can_view_wallets": perm.can_view_wallets,
    }
