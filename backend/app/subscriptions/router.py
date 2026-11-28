"""Platform subscription endpoints: the owner's paywall, checkout, codes, webhook,
and the Super Admin's plan prices and liberation codes."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import AuthenticatedUser, DbSession, SuperAdminUser, require_csrf
from app.bots import smokepay
from app.core.time import utc_now
from app.models import PlatformLiberationCode, PlatformPlan, PlatformSubscriptionCharge
from app.models.platform_subscription import CHARGE_PAID
from app.subscriptions import service

router = APIRouter(prefix="/api/subscription", tags=["subscription"])
logger = logging.getLogger(__name__)


class PlanOut(BaseModel):
    id: UUID
    code: str
    name: str
    price: Decimal
    period_days: int


class CouponOut(BaseModel):
    percent: Decimal
    expires_at: datetime | None


class AccessOut(BaseModel):
    required: bool
    active: bool
    status: str
    until: str | None
    in_trial: bool
    plans: list[PlanOut]
    # Anti-churn: a retention coupon currently offered to this owner (null = none).
    coupon: CouponOut | None = None


class ChargeOut(BaseModel):
    id: UUID
    status: str
    amount: Decimal
    pix_copy_paste: str | None
    due_at: datetime | None
    discount_percent: Decimal | None = None


def _plan_out(plan: PlatformPlan) -> PlanOut:
    return PlanOut(id=plan.id, code=plan.code, name=plan.name, price=plan.price, period_days=plan.period_days)


def _coupon_out(coupon) -> CouponOut | None:
    if coupon is None:
        return None
    return CouponOut(percent=coupon.percent, expires_at=coupon.expires_at)


async def _active_plans(db: DbSession) -> list[PlatformPlan]:
    return list(
        await db.scalars(
            select(PlatformPlan).where(PlatformPlan.is_active.is_(True)).order_by(PlatformPlan.sort_order, PlatformPlan.price)
        )
    )


@router.get("/me", response_model=AccessOut)
async def my_subscription(user: AuthenticatedUser, db: DbSession) -> AccessOut:
    state = await service.access_state(db, user)
    await db.commit()  # get_or_create may have inserted the trial row
    plans = await _active_plans(db) if state["required"] else []
    coupon = await service.active_retention_coupon(db, user) if state["required"] else None
    return AccessOut(**state, plans=[_plan_out(p) for p in plans], coupon=_coupon_out(coupon))


class CheckoutRequest(BaseModel):
    plan_id: UUID


@router.post("/checkout", response_model=ChargeOut, dependencies=[Depends(require_csrf)])
async def checkout(payload: CheckoutRequest, user: AuthenticatedUser, db: DbSession) -> ChargeOut:
    if not await service.requires_subscription(db, user):
        raise HTTPException(status_code=403, detail="Sua conta não precisa de assinatura.")
    plan = await db.scalar(
        select(PlatformPlan).where(PlatformPlan.id == payload.plan_id, PlatformPlan.is_active.is_(True))
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Plano indisponível.")
    coupon = await service.active_retention_coupon(db, user)
    try:
        charge = await service.start_charge(db, user, plan, coupon=coupon)
    except smokepay.SmokepayError as exc:
        await db.rollback()
        logger.warning("Subscription PIX failed for user %s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="Não foi possível gerar o PIX agora. Tente novamente.") from None
    await db.commit()
    return ChargeOut(
        id=charge.id, status=charge.status, amount=charge.amount,
        pix_copy_paste=charge.pix_copy_paste, due_at=charge.due_at,
        discount_percent=coupon.percent if coupon else None,
    )


@router.get("/charge/{charge_id}", response_model=ChargeOut)
async def charge_status(charge_id: UUID, user: AuthenticatedUser, db: DbSession) -> ChargeOut:
    charge = await db.scalar(
        select(PlatformSubscriptionCharge)
        .join(service.PlatformSubscription, service.PlatformSubscription.id == PlatformSubscriptionCharge.subscription_id)
        .where(PlatformSubscriptionCharge.id == charge_id, service.PlatformSubscription.user_id == user.id)
    )
    if charge is None:
        raise HTTPException(status_code=404, detail="Cobrança não encontrada.")
    return ChargeOut(
        id=charge.id, status=charge.status, amount=charge.amount,
        pix_copy_paste=charge.pix_copy_paste, due_at=charge.due_at,
    )


class RedeemRequest(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=32)]


@router.post("/redeem", response_model=AccessOut, dependencies=[Depends(require_csrf)])
async def redeem(payload: RedeemRequest, user: AuthenticatedUser, db: DbSession) -> AccessOut:
    if not await service.requires_subscription(db, user):
        raise HTTPException(status_code=403, detail="Sua conta não precisa de assinatura.")
    try:
        await service.redeem_liberation_code(db, user, payload.code)
    except service.SubscriptionError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await db.commit()
    state = await service.access_state(db, user)
    plans = await _active_plans(db)
    return AccessOut(**state, plans=[_plan_out(p) for p in plans])


class CancelIntentOut(BaseModel):
    offered: bool
    coupon: CouponOut | None = None


@router.post("/cancel-intent", response_model=CancelIntentOut, dependencies=[Depends(require_csrf)])
async def cancel_intent(user: AuthenticatedUser, db: DbSession) -> CancelIntentOut:
    """Owner signals they want to cancel / not renew. Before blocking access, offer the
    anti-churn coupon (if the Super Admin turned it on). The coupon auto-applies at checkout."""
    coupon = await service.offer_retention_coupon(db, user)
    await db.commit()
    return CancelIntentOut(offered=coupon is not None, coupon=_coupon_out(coupon))


@router.post("/pay/smokepay", include_in_schema=False)
async def smokepay_webhook(request: Request, db: DbSession) -> dict:
    raw = await request.body()
    if not smokepay.verify_signature(raw, request.headers.get("x-webhook-signature")):
        raise HTTPException(status_code=401, detail="Invalid signature.")  # 4xx stops retries
    try:
        event = json.loads(raw)
    except ValueError:
        return {"ok": True}
    external_id = str(event.get("external_id") or "")
    if (
        event.get("event") != "payment.confirmed"
        or event.get("status") != "paid"
        or not external_id.startswith(service.PLATFORM_SUB_PREFIX)
    ):
        return {"ok": True}  # not a platform subscription charge
    try:
        applied = await service.apply_paid_charge(db, external_id)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Retry.") from None  # 5xx: SmokePay retries
    if applied:
        logger.info("Subscription charge %s confirmed.", external_id)
    return {"ok": True}


# --------------------------------------------------------------- Super Admin

admin_router = APIRouter(prefix="/api/subscription/admin", tags=["subscription-admin"])


class PlanAdminOut(PlanOut):
    sort_order: int
    is_active: bool


class PlanUpdateRequest(BaseModel):
    price: Decimal | None = Field(default=None, ge=0)
    name: Annotated[str | None, Field(max_length=80)] = None
    is_active: bool | None = None


@admin_router.get("/plans")
async def list_plans(_admin: SuperAdminUser, db: DbSession) -> dict:
    plans = list(await db.scalars(select(PlatformPlan).order_by(PlatformPlan.sort_order, PlatformPlan.price)))
    return {
        "plans": [
            PlanAdminOut(
                id=p.id, code=p.code, name=p.name, price=p.price, period_days=p.period_days,
                sort_order=p.sort_order, is_active=p.is_active,
            ).model_dump()
            for p in plans
        ]
    }


@admin_router.patch("/plans/{plan_id}", dependencies=[Depends(require_csrf)])
async def update_plan(plan_id: UUID, payload: PlanUpdateRequest, _admin: SuperAdminUser, db: DbSession) -> dict:
    plan = await db.get(PlatformPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plano não encontrado.")
    if payload.price is not None:
        plan.price = payload.price.quantize(Decimal("0.01"))
    if payload.name is not None and payload.name.strip():
        plan.name = payload.name.strip()
    if payload.is_active is not None:
        plan.is_active = payload.is_active
    await db.commit()
    return {"ok": True}


class AntiChurnOut(BaseModel):
    enabled: bool
    percent: Decimal
    valid_days: int


class AntiChurnUpdate(BaseModel):
    enabled: bool
    percent: Annotated[Decimal, Field(ge=1, le=90)]
    valid_days: Annotated[int, Field(ge=1, le=90)]


@admin_router.get("/anti-churn", response_model=AntiChurnOut)
async def get_anti_churn(_admin: SuperAdminUser, db: DbSession) -> AntiChurnOut:
    config = await service.anti_churn_config(db)
    return AntiChurnOut(enabled=config["enabled"], percent=config["percent"], valid_days=config["valid_days"])


@admin_router.put("/anti-churn", response_model=AntiChurnOut, dependencies=[Depends(require_csrf)])
async def set_anti_churn(payload: AntiChurnUpdate, admin: SuperAdminUser, db: DbSession) -> AntiChurnOut:
    saved = await service.set_anti_churn_config(
        db, admin, enabled=payload.enabled, percent=payload.percent, valid_days=payload.valid_days,
    )
    await db.commit()
    return AntiChurnOut(enabled=saved["enabled"], percent=saved["percent"], valid_days=saved["valid_days"])


class CodeCreateRequest(BaseModel):
    days: Annotated[int, Field(ge=1, le=3650)]
    note: Annotated[str | None, Field(max_length=160)] = None
    expires_at: datetime | None = None


@admin_router.get("/codes")
async def list_codes(_admin: SuperAdminUser, db: DbSession) -> dict:
    rows = list(
        await db.scalars(select(PlatformLiberationCode).order_by(PlatformLiberationCode.created_at.desc()).limit(200))
    )
    return {
        "codes": [
            {
                "id": str(r.id), "code": r.code, "days": r.days, "note": r.note,
                "redeemed": r.redeemed_at is not None,
                "redeemed_at": r.redeemed_at.isoformat() if r.redeemed_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@admin_router.post("/codes", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def create_code(payload: CodeCreateRequest, admin: SuperAdminUser, db: DbSession) -> dict:
    try:
        row = await service.create_liberation_code(
            db, admin, days=payload.days, note=payload.note, expires_at=payload.expires_at
        )
    except service.SubscriptionError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await db.commit()
    return {"id": str(row.id), "code": row.code, "days": row.days}
