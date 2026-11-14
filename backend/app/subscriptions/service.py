"""Platform subscription logic: who pays, access windows, PIX charges, codes.

Only an operation owner pays (collaborators and the Super Admin never do). A new
owner gets a free trial; after that a paid window is extended each time a PIX
charge is confirmed, or a liberation code is redeemed.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import PlatformRole, WorkspaceRole
from app.core.time import utc_now
from app.bots import smokepay
from app.models import (
    PlatformLiberationCode,
    PlatformPlan,
    PlatformSubscription,
    PlatformSubscriptionCharge,
    User,
    WorkspaceMember,
)
from app.models.platform_subscription import (
    CHARGE_EXPIRED,
    CHARGE_PAID,
    CHARGE_PENDING,
    SUB_ACTIVE,
    SUB_CANCELED,
    SUB_PAST_DUE,
    SUB_TRIALING,
)

TRIAL_DAYS = 7
# A subscription PIX stays payable for a day.
CHARGE_EXPIRATION_SECONDS = 24 * 60 * 60
# external_id prefix so the bot-order webhook ignores these and vice versa.
PLATFORM_SUB_PREFIX = "psub_"


class SubscriptionError(RuntimeError):
    pass


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def owns_operation(db: AsyncSession, user: User) -> bool:
    """True when the user owns a workspace (an operation). Partners own theirs too."""
    found = await db.scalar(
        select(WorkspaceMember.id).where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.role == WorkspaceRole.OWNER.value,
            WorkspaceMember.status == "ACTIVE",
        ).limit(1)
    )
    return found is not None


async def requires_subscription(db: AsyncSession, user: User) -> bool:
    """The Super Admin never pays; collaborators (no owned workspace) don't either."""
    if user.platform_role == PlatformRole.SUPER_ADMIN.value:
        return False
    return await owns_operation(db, user)


def effective_until(sub: PlatformSubscription) -> datetime | None:
    """The later of the trial end and the paid-period end."""
    ends = [d for d in (_aware(sub.trial_end), _aware(sub.current_period_end)) if d is not None]
    return max(ends) if ends else None


def is_active(sub: PlatformSubscription, now: datetime | None = None) -> bool:
    now = now or utc_now()
    if sub.status == SUB_CANCELED:
        until = _aware(sub.current_period_end)
        return until is not None and until > now  # canceled keeps access until it runs out
    until = effective_until(sub)
    return until is not None and until > now


async def get_or_create(db: AsyncSession, user: User) -> PlatformSubscription:
    sub = await db.scalar(select(PlatformSubscription).where(PlatformSubscription.user_id == user.id))
    if sub is not None:
        return sub
    # New (or pre-existing, first seen now) owner: start the free trial from now.
    sub = PlatformSubscription(
        user_id=user.id,
        status=SUB_TRIALING,
        trial_end=utc_now() + timedelta(days=TRIAL_DAYS),
    )
    db.add(sub)
    await db.flush()
    return sub


def _in_trial(sub: PlatformSubscription, now: datetime | None = None) -> bool:
    now = now or utc_now()
    end = _aware(sub.trial_end)
    paid = _aware(sub.current_period_end)
    return end is not None and end > now and (paid is None or paid <= now)


async def access_state(db: AsyncSession, user: User) -> dict:
    """What the front-end needs to decide whether to show the paywall."""
    if not await requires_subscription(db, user):
        return {"required": False, "active": True, "status": "exempt", "until": None, "in_trial": False}
    sub = await get_or_create(db, user)
    active = is_active(sub)
    until = effective_until(sub)
    return {
        "required": True,
        "active": active,
        "status": sub.status,
        "until": until.isoformat() if until else None,
        "in_trial": _in_trial(sub),
    }


def _extend(sub: PlatformSubscription, days: int, now: datetime | None = None) -> None:
    now = now or utc_now()
    base = _aware(sub.current_period_end)
    start = base if base and base > now else now
    sub.current_period_end = start + timedelta(days=days)
    sub.status = SUB_ACTIVE


async def start_charge(db: AsyncSession, user: User, plan: PlatformPlan) -> PlatformSubscriptionCharge:
    """Create a pending charge and its SmokePay PIX. Returns the charge with PIX data."""
    sub = await get_or_create(db, user)
    charge = PlatformSubscriptionCharge(
        subscription_id=sub.id,
        plan_id=plan.id,
        amount=plan.price,
        period_days=plan.period_days,
        status=CHARGE_PENDING,
        external_id=f"{PLATFORM_SUB_PREFIX}{uuid.uuid4().hex}",
        due_at=utc_now() + timedelta(seconds=CHARGE_EXPIRATION_SECONDS),
    )
    db.add(charge)
    await db.flush()

    settings = get_settings()
    webhook_url = f"{settings.public_base_url.rstrip('/')}/api/subscription/pay/smokepay"
    pix = await smokepay.create_pix(
        amount=plan.price,
        external_id=charge.external_id,
        description=f"Assinatura FlashPost - {plan.name}",
        webhook_url=webhook_url,
        expiration_seconds=CHARGE_EXPIRATION_SECONDS,
    )
    charge.pix_copy_paste = pix.copy_paste
    charge.pix_txid = pix.transaction_id or None
    # A zero-price plan (e.g. a comp) is paid the instant it's created.
    if plan.price <= 0:
        charge.status = CHARGE_PAID
        charge.paid_at = utc_now()
        _extend(sub, plan.period_days)
    await db.flush()
    return charge


async def apply_paid_charge(db: AsyncSession, external_id: str, paid_at: datetime | None = None) -> bool:
    """Mark a charge paid (idempotent) and extend its subscription. Returns True if applied."""
    charge = await db.scalar(
        select(PlatformSubscriptionCharge).where(PlatformSubscriptionCharge.external_id == external_id)
    )
    if charge is None:
        return False
    if charge.status == CHARGE_PAID:
        return True  # already processed; webhook retries are safe
    sub = await db.get(PlatformSubscription, charge.subscription_id)
    if sub is None:
        return False
    charge.status = CHARGE_PAID
    charge.paid_at = paid_at or utc_now()
    if charge.plan_id is not None:
        sub.plan_id = charge.plan_id
    _extend(sub, charge.period_days, now=charge.paid_at)
    return True


def _new_code() -> str:
    # Human-friendly, unambiguous (no O/0/I/1).
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


async def create_liberation_code(
    db: AsyncSession, admin: User, *, days: int, note: str | None, expires_at: datetime | None
) -> PlatformLiberationCode:
    for _ in range(5):
        code = _new_code()
        if await db.scalar(select(PlatformLiberationCode.id).where(PlatformLiberationCode.code == code)) is None:
            break
    else:
        raise SubscriptionError("Não foi possível gerar um código único. Tente novamente.")
    row = PlatformLiberationCode(
        code=code, days=days, note=note, created_by_user_id=admin.id, expires_at=expires_at
    )
    db.add(row)
    await db.flush()
    return row


async def redeem_liberation_code(db: AsyncSession, user: User, code: str) -> PlatformSubscription:
    row = await db.scalar(
        select(PlatformLiberationCode).where(PlatformLiberationCode.code == code.strip().upper())
    )
    if row is None:
        raise SubscriptionError("Código inválido.")
    if row.redeemed_at is not None:
        raise SubscriptionError("Este código já foi utilizado.")
    expires = _aware(row.expires_at)
    if expires is not None and expires <= utc_now():
        raise SubscriptionError("Este código expirou.")
    sub = await get_or_create(db, user)
    _extend(sub, row.days)
    row.redeemed_by_user_id = user.id
    row.redeemed_at = utc_now()
    return sub


async def mark_due_past(db: AsyncSession, now: datetime | None = None) -> int:
    """Flip active/trialing subscriptions whose window has ended to past_due, and
    expire their stale pending charges. Returns how many subscriptions changed."""
    now = now or utc_now()
    subs = list(
        await db.scalars(
            select(PlatformSubscription).where(PlatformSubscription.status.in_((SUB_ACTIVE, SUB_TRIALING)))
        )
    )
    changed = 0
    for sub in subs:
        if not is_active(sub, now):
            sub.status = SUB_PAST_DUE
            changed += 1
    stale = list(
        await db.scalars(
            select(PlatformSubscriptionCharge).where(
                PlatformSubscriptionCharge.status == CHARGE_PENDING,
                PlatformSubscriptionCharge.due_at < now,
            )
        )
    )
    for charge in stale:
        charge.status = CHARGE_EXPIRED
    return changed
