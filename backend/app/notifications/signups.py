"""Push to the Super Admin whenever a new account waits for approval."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import PlatformRole
from app.models import PushSubscription, User

logger = logging.getLogger(__name__)


async def notify_new_signup(db: AsyncSession, user: User, origin: str) -> None:
    """Best effort: a push failure must never undo a sign-up."""
    try:
        from app.bots import http
        from app.notifications.milestones import push_to
        from app.notifications.webpush import get_vapid_keys

        admins = select(User.id).where(User.platform_role == PlatformRole.SUPER_ADMIN.value)
        subscriptions: list[PushSubscription] = []
        seen: set[str] = set()
        for subscription in await db.scalars(
            select(PushSubscription).where(PushSubscription.user_id.in_(admins))
        ):
            if subscription.endpoint not in seen:
                seen.add(subscription.endpoint)
                subscriptions.append(subscription)
        if not subscriptions:
            return
        tag = f"signup-{user.id.hex[:24]}"
        payload = {
            "title": "Novo cadastro aguardando aprovação",
            "body": f"{user.full_name} ({origin}) quer acessar o Falcon Post.",
            "url": "/admin/users",
            "tag": tag,
        }
        keys = await get_vapid_keys(db)
        async with http.client(10.0) as session:
            await push_to(db, subscriptions, payload, keys, session, tag)
        await db.commit()
    except Exception:
        logger.exception("New sign-up push notification failed")
