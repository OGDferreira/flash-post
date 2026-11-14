from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import smokepay
from app.bots.smokepay import PixCharge
from app.models import PlatformLiberationCode, PlatformPlan, PlatformSubscription, PlatformSubscriptionCharge
from app.models.platform_subscription import CHARGE_PAID, SUB_ACTIVE, SUB_PAST_DUE, SUB_TRIALING
from app.subscriptions import service
from tests.test_loops import _csrf, _login


async def _plan(db: AsyncSession, code: str) -> PlatformPlan:
    """Use a plan seeded by the migration (weekly/monthly/annual)."""
    plan = await db.scalar(select(PlatformPlan).where(PlatformPlan.code == code))
    assert plan is not None, f"seed plan {code} missing"
    return plan


def _fake_pix(**_kwargs) -> PixCharge:
    return PixCharge(
        transaction_id="tx_123", external_id=_kwargs.get("external_id", ""), status="pending",
        amount=_kwargs.get("amount", Decimal("0")), fee=None, net_amount=None,
        copy_paste="000201...pix", qr_code_base64=None, expires_at=None,
    )


@pytest.mark.anyio
async def test_owner_gets_trial_collaborator_and_admin_exempt(
    db_session: AsyncSession, owner, collaborator, super_admin
) -> None:
    owner_user, _ = owner
    owner_state = await service.access_state(db_session, owner_user)
    assert owner_state == {
        "required": True, "active": True, "status": SUB_TRIALING,
        "until": owner_state["until"], "in_trial": True,
    }
    assert owner_state["until"] is not None  # 7-day trial window set
    assert (await service.access_state(db_session, collaborator))["required"] is False
    assert (await service.access_state(db_session, super_admin))["required"] is False


@pytest.mark.anyio
async def test_checkout_creates_pix_and_webhook_extends_access(
    db_session: AsyncSession, client: AsyncClient, owner, monkeypatch
) -> None:
    owner_user, _ = owner
    plan = await _plan(db_session, "monthly")
    monkeypatch.setattr(smokepay, "create_pix", lambda **kw: _as_coro(_fake_pix(**kw)))

    await _login(client, "owner@example.com", "correct horse battery staple")
    resp = await client.post(
        "/api/subscription/checkout", headers={"X-CSRF-Token": await _csrf(client)},
        json={"plan_id": str(plan.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pix_copy_paste"] == "000201...pix" and body["status"] == "pending"

    # The SmokePay webhook confirming the charge extends the paid window.
    charge_external = await db_session.scalar(select(PlatformSubscriptionCharge.external_id))
    applied = await service.apply_paid_charge(db_session, charge_external)
    await db_session.commit()
    assert applied is True
    # Idempotent: a retry doesn't double-extend.
    assert await service.apply_paid_charge(db_session, charge_external) is True

    sub = await db_session.scalar(select(PlatformSubscription).where(PlatformSubscription.user_id == owner_user.id))
    assert sub.status == SUB_ACTIVE and sub.plan_id == plan.id
    assert service.is_active(sub) is True
    assert service.effective_until(sub) > datetime.now(timezone.utc) + timedelta(days=29)


@pytest.mark.anyio
async def test_liberation_code_grants_access_and_cannot_be_reused(
    db_session: AsyncSession, owner, super_admin
) -> None:
    owner_user, _ = owner
    row = await service.create_liberation_code(db_session, super_admin, days=30, note="cortesia", expires_at=None)
    await db_session.commit()

    sub = await service.redeem_liberation_code(db_session, owner_user, row.code)
    await db_session.commit()
    assert sub.status == SUB_ACTIVE
    assert sub.current_period_end > datetime.now(timezone.utc) + timedelta(days=29)

    with pytest.raises(service.SubscriptionError):
        await service.redeem_liberation_code(db_session, owner_user, row.code)


@pytest.mark.anyio
async def test_expired_window_sweeps_to_past_due(db_session: AsyncSession, owner) -> None:
    owner_user, _ = owner
    sub = await service.get_or_create(db_session, owner_user)
    sub.trial_end = datetime.now(timezone.utc) - timedelta(days=1)  # trial already over
    await db_session.commit()

    changed = await service.mark_due_past(db_session)
    await db_session.commit()
    assert changed == 1
    refreshed = await db_session.get(PlatformSubscription, sub.id)
    assert refreshed.status == SUB_PAST_DUE
    assert service.is_active(refreshed) is False


@pytest.mark.anyio
async def test_super_admin_edits_plan_price_and_creates_code(
    db_session: AsyncSession, client: AsyncClient, super_admin
) -> None:
    plan = await _plan(db_session, "weekly")
    await _login(client, "superadmin@example.com", "super admin password")
    token = await _csrf(client)

    edited = await client.patch(
        f"/api/subscription/admin/plans/{plan.id}", headers={"X-CSRF-Token": token}, json={"price": "29.90"}
    )
    assert edited.status_code == 200, edited.text
    await db_session.refresh(plan)
    assert plan.price == Decimal("29.90")

    made = await client.post(
        "/api/subscription/admin/codes", headers={"X-CSRF-Token": token}, json={"days": 15, "note": "amigo"}
    )
    assert made.status_code == 201, made.text
    code = made.json()["code"]
    stored = await db_session.scalar(select(PlatformLiberationCode).where(PlatformLiberationCode.code == code))
    assert stored is not None and stored.days == 15


async def _as_coro(value):
    return value
