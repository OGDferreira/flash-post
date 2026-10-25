"""Per-sócio (partner) feature permissions.

A partner (someone with an active ``Affiliation``) only sees a restricted, unified
panel: a few Flash Post tabs and a few Flash Bot tabs. The Super Admin (or the chief)
can turn each one on or off, or unlock the full panel. Owners, collaborators and the
Super Admin themselves are never restricted by this.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import AuthenticatedUser, DbSession

# The features a partner can be granted, per tool. Keep in sync with the frontend
# (navigation.ts PARTNER_FEATURE_ROUTES).
POST_FEATURES = ("dashboard", "ranking", "accounts", "meta_apps", "settings", "contacts")
BOT_FEATURES = ("dashboard", "leads", "wallet")


def default_permissions() -> dict:
    """The default set a sócio gets: all the restricted tabs, full panel off."""
    return {
        "post": {feature: True for feature in POST_FEATURES},
        "bot": {feature: True for feature in BOT_FEATURES},
        "full_panel": False,
    }


def effective_permissions(permissions: dict | None) -> dict:
    """Merge a stored permissions dict onto the defaults (unknown keys ignored)."""
    base = default_permissions()
    stored = permissions if isinstance(permissions, dict) else {}
    for tool in ("post", "bot"):
        group = stored.get(tool)
        if isinstance(group, dict):
            for feature, value in group.items():
                if feature in base[tool]:
                    base[tool][feature] = bool(value)
    if "full_panel" in stored:
        base["full_panel"] = bool(stored["full_panel"])
    return base


def allows(permissions: dict, tool: str, feature: str) -> bool:
    """Whether the (already-effective) permissions let a partner use ``tool.feature``."""
    if permissions.get("full_panel"):
        return True
    return bool(permissions.get(tool, {}).get(feature, False))


def sanitize(permissions: dict | None) -> dict:
    """Clamp an incoming permissions payload to the known shape (for storage)."""
    return effective_permissions(permissions)


def require_partner_feature(tool: str, feature: str):
    """Dependency: block a partner from a feature the admin turned off.

    Non-partners (owners, collaborators, Super Admin) pass through untouched, so
    adding this to an endpoint never changes their access.
    """

    async def guard(user: AuthenticatedUser, db: DbSession) -> None:
        from app.partners.service import partner_link

        link = await partner_link(db, user.id)
        if link is None:
            return
        if not allows(effective_permissions(link.permissions), tool, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Seu acesso a esta função foi desativado pelo administrador.",
            )

    return Depends(guard)
