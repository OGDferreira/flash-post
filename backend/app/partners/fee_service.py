"""Fee management service for transaction fees."""

import uuid
from decimal import Decimal
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FeeChangeLog, User, Affiliation
from app.core.time import utc_now


async def get_user_fee(db: AsyncSession, user_id: uuid.UUID) -> Decimal | None:
    """Get the transaction fee for a specific user (None means platform default)."""
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        return None
    return user.transaction_fee


async def set_user_fee(
    db: AsyncSession,
    user_id: uuid.UUID,
    new_fee: Decimal | None,
    changed_by_user_id: uuid.UUID,
    reason: str | None = None,
    is_global: bool = False
) -> tuple[Decimal | None, Decimal | None]:
    """
    Set transaction fee for a user and log the change.
    Returns (old_fee, new_fee).
    """
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise ValueError(f"User {user_id} not found")

    old_fee = user.transaction_fee

    # Update user fee
    user.transaction_fee = new_fee

    # Log the change
    log = FeeChangeLog(
        user_id=user_id,
        changed_by_user_id=changed_by_user_id,
        old_fee=float(old_fee) if old_fee else None,
        new_fee=float(new_fee) if new_fee else None,
        is_global_change=is_global,
        reason=reason,
    )
    db.add(log)
    await db.flush()

    return old_fee, new_fee


async def set_global_fee(
    db: AsyncSession,
    new_fee: Decimal | None,
    changed_by_user_id: uuid.UUID,
    reason: str | None = None,
    exclude_user_ids: list[uuid.UUID] | None = None
) -> int:
    """
    Set transaction fee for all users (or all except specific ones).
    Returns the number of users affected.
    """
    # Get all active users
    query = select(User).where(User.is_active == True)
    if exclude_user_ids:
        query = query.where(~User.id.in_(exclude_user_ids))

    users = await db.scalars(query)
    users_list = list(users)

    # Update all users and log changes
    for user in users_list:
        old_fee = user.transaction_fee
        user.transaction_fee = new_fee

        # Log each change
        log = FeeChangeLog(
            user_id=user.id,
            changed_by_user_id=changed_by_user_id,
            old_fee=float(old_fee) if old_fee else None,
            new_fee=float(new_fee) if new_fee else None,
            is_global_change=True,
            reason=reason,
        )
        db.add(log)

    await db.flush()
    return len(users_list)


async def get_fee_history(
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
    limit: int = 50
) -> list[FeeChangeLog]:
    """Get fee change history for a user or all users."""
    query = select(FeeChangeLog)
    if user_id:
        query = query.where(FeeChangeLog.user_id == user_id)
    query = query.order_by(FeeChangeLog.created_at.desc()).limit(limit)

    return list(await db.scalars(query))


async def get_all_partners_with_fees(db: AsyncSession) -> list[dict]:
    """Get all partners with their current fees."""
    # Get all active affiliations
    affiliations = await db.scalars(
        select(Affiliation).where(Affiliation.status == "ACTIVE")
    )

    partners_data = []
    for aff in affiliations:
        user = await db.scalar(select(User).where(User.id == aff.affiliate_user_id))
        chief = await db.scalar(select(User).where(User.id == aff.chief_user_id))

        if user:
            partners_data.append({
                "user_id": str(user.id),
                "name": user.full_name,
                "email": user.email,
                "nickname": user.nickname,
                "current_fee": float(user.transaction_fee) if user.transaction_fee else None,
                "chief_name": chief.full_name if chief else None,
                "chief_id": str(chief.id) if chief else None,
            })

    return partners_data


async def get_users_with_custom_fees(db: AsyncSession) -> list[dict]:
    """Get all users with custom fees (non-default)."""
    users = await db.scalars(
        select(User).where(User.transaction_fee.isnot(None), User.is_active == True)
    )

    result = []
    for user in users:
        result.append({
            "user_id": str(user.id),
            "name": user.full_name,
            "email": user.email,
            "nickname": user.nickname,
            "current_fee": float(user.transaction_fee) if user.transaction_fee else None,
        })

    return result
