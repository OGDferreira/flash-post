"""Routes for transaction fee management via admin chat."""

import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import DbSession, SuperAdminUser, require_csrf
from app.partners import fee_service
from app.models import User
from sqlalchemy import select

router = APIRouter(prefix="/api/admin/fees", tags=["Admin Fee Management"])


class FeeUpdateRequest(BaseModel):
    user_id: str | None = None  # None for global change
    new_fee: Decimal | None = Field(None, ge=0, le=100)  # BRL, None for platform default
    reason: str | None = None


class FeeQueryRequest(BaseModel):
    user_id: str | None = None


class FeeHistoryResponse(BaseModel):
    user_id: str
    user_name: str
    old_fee: float | None
    new_fee: float | None
    is_global_change: bool
    reason: str | None
    changed_by: str | None
    created_at: str


@router.get("/current")
async def get_current_fees(
    _admin: SuperAdminUser,
    db: DbSession,
) -> dict:
    """Get all partners with their current fees."""
    partners = await fee_service.get_all_partners_with_fees(db)
    custom_fees = await fee_service.get_users_with_custom_fees(db)

    return {
        "partners": partners,
        "users_with_custom_fees": custom_fees,
    }


@router.get("/user/{user_id}")
async def get_user_fee(
    user_id: str,
    _admin: SuperAdminUser,
    db: DbSession,
) -> dict:
    """Get the transaction fee for a specific user."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    fee = await fee_service.get_user_fee(db, uid)
    user = await db.scalar(select(User).where(User.id == uid))

    if not user:
        raise HTTPException(404, "User not found")

    return {
        "user_id": user_id,
        "user_name": user.full_name,
        "current_fee": float(fee) if fee else None,
        "uses_default": fee is None,
    }


@router.put("/user")
async def update_user_fee(
    data: FeeUpdateRequest,
    admin: SuperAdminUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Update transaction fee for a specific user."""
    if not data.user_id:
        raise HTTPException(400, "user_id is required for individual fee update")

    try:
        user_id = uuid.UUID(data.user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    old_fee, new_fee = await fee_service.set_user_fee(
        db, user_id, data.new_fee, admin.id, data.reason, is_global=False
    )
    await db.commit()

    user = await db.scalar(select(User).where(User.id == user_id))

    return {
        "success": True,
        "user_id": data.user_id,
        "user_name": user.full_name if user else "Unknown",
        "old_fee": float(old_fee) if old_fee else None,
        "new_fee": float(new_fee) if new_fee else None,
        "message": f"Taxa atualizada de {f'{float(old_fee):.2f}' if old_fee else 'padrão'} para {f'{float(new_fee):.2f}' if new_fee else 'padrão'}",
    }


@router.put("/global")
async def update_global_fee(
    data: FeeUpdateRequest,
    admin: SuperAdminUser,
    db: DbSession,
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Update transaction fee for all users."""
    count = await fee_service.set_global_fee(
        db, data.new_fee, admin.id, data.reason
    )
    await db.commit()

    return {
        "success": True,
        "affected_users": count,
        "new_fee": float(data.new_fee) if data.new_fee else None,
        "message": f"Taxa global atualizada para {f'{float(data.new_fee):.2f}' if data.new_fee else 'padrão da plataforma'}. {count} usuários afetados.",
    }


@router.get("/history")
async def get_fee_history(
    _admin: SuperAdminUser,
    db: DbSession,
    user_id: str | None = None,
    limit: int = 50,
) -> dict:
    """Get fee change history."""
    uid = None
    if user_id:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(400, "Invalid user ID")

    history = await fee_service.get_fee_history(db, uid, limit)

    # Get user names
    user_ids = {log.user_id for log in history} | {log.changed_by_user_id for log in history if log.changed_by_user_id}
    users = {u.id: u for u in await db.scalars(select(User).where(User.id.in_(user_ids)))}

    result = []
    for log in history:
        user = users.get(log.user_id)
        changed_by = users.get(log.changed_by_user_id) if log.changed_by_user_id else None

        result.append({
            "user_id": str(log.user_id),
            "user_name": user.full_name if user else "Unknown",
            "old_fee": log.old_fee,
            "new_fee": log.new_fee,
            "is_global_change": log.is_global_change,
            "reason": log.reason,
            "changed_by": changed_by.full_name if changed_by else None,
            "changed_by_id": str(log.changed_by_user_id) if log.changed_by_user_id else None,
            "created_at": log.created_at.isoformat(),
        })

    return {
        "history": result,
        "count": len(result),
    }


@router.post("/preview-global")
async def preview_global_change(
    data: FeeUpdateRequest,
    _admin: SuperAdminUser,
    db: DbSession,
) -> dict:
    """Preview how many users would be affected by a global fee change."""
    users = list(await db.scalars(select(User).where(User.is_active == True)))

    affected_users = []
    for user in users:
        affected_users.append({
            "user_id": str(user.id),
            "name": user.full_name,
            "email": user.email,
            "current_fee": float(user.transaction_fee) if user.transaction_fee else None,
            "new_fee": float(data.new_fee) if data.new_fee else None,
        })

    return {
        "affected_count": len(affected_users),
        "affected_users": affected_users[:50],  # Limit preview to 50 users
        "total_users": len(affected_users),
        "new_fee": float(data.new_fee) if data.new_fee else None,
    }
