"""Anti-churn: when an owner signals they want to cancel, the platform offers a
discount coupon before blocking access; paying with it renews at the discount."""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import smokepay
from app.models import PlatformRetentionCoupon, PlatformSubscriptionCharge
from app.models.platform_subscription import COUPON_OFFERED, COUPON_USED
from app.subscriptions import service
from tests.test_loops import _csrf, _login
from tests.test_subscriptions import _as_coro, _fake_pix, _plan


@pytest.mark.anyio
async def test_cancel_intent_off_by_default(db_session: AsyncSession, client: AsyncClient, owner) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")
    resp = await client.post("/api/subscription/cancel-intent", headers={"X-CSRF-Token": await _csrf(client)})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"offered": False, "coupon": None}


@pytest.mark.anyio
async def test_admin_config_and_coupon_discounts_checkout(
    db_session: AsyncSession, client: AsyncClient, owner, super_admin, monkeypatch
) -> None:
    owner_user, _ = owner
    # Super Admin turns the feature on: 30% off, valid 10 days.
    await service.set_anti_churn_config(db_session, super_admin, enabled=True, percent=Decimal("30"), valid_days=10)
    await db_session.commit()
    config = await service.anti_churn_config(db_session)
    assert config["enabled"] is True and config["percent"] == Decimal("30.00") and config["valid_days"] == 10

    monkeypatch.setattr(smokepay, "create_pix", lambda **kw: _as_coro(_fake_pix(**kw)))
    await _login(client, "owner@example.com", "correct horse battery staple")
    headers = {"X-CSRF-Token": await _csrf(client)}

    # Owner signals cancel -> gets the coupon.
    intent = (await client.post("/api/subscription/cancel-intent", headers=headers)).json()
    assert intent["offered"] is True and Decimal(str(intent["coupon"]["percent"])) == Decimal("30.00")

    # /me surfaces the active coupon.
    me = (await client.get("/api/subscription/me")).json()
    assert me["coupon"] is not None and Decimal(str(me["coupon"]["percent"])) == Decimal("30.00")

    # Checkout auto-applies it: R$ 59,90 monthly -> 30% off.
    plan = await _plan(db_session, "monthly")
    resp = (await client.post(
        "/api/subscription/checkout", headers=headers, json={"plan_id": str(plan.id)},
    )).json()
    expected = (plan.price - (plan.price * Decimal("30") / Decimal("100"))).quantize(Decimal("0.01"))
    assert Decimal(str(resp["amount"])) == expected
    assert Decimal(str(resp["discount_percent"])) == Decimal("30.00")

    # Paying the PIX marks the coupon used and renews.
    external = await db_session.scalar(select(PlatformSubscriptionCharge.external_id))
    assert await service.apply_paid_charge(db_session, external) is True
    await db_session.commit()
    coupon = await db_session.scalar(
        select(PlatformRetentionCoupon).where(PlatformRetentionCoupon.user_id == owner_user.id)
    )
    assert coupon.status == COUPON_USED and coupon.used_at is not None
    # No active coupon left to reoffer unless a fresh cancel-intent mints one.
    assert await service.active_retention_coupon(db_session, owner_user) is None


@pytest.mark.anyio
async def test_coupon_reused_while_valid_and_expires(
    db_session: AsyncSession, super_admin, owner, monkeypatch
) -> None:
    owner_user, _ = owner
    await service.set_anti_churn_config(db_session, super_admin, enabled=True, percent=Decimal("15"), valid_days=7)
    await db_session.commit()

    first = await service.offer_retention_coupon(db_session, owner_user)
    await db_session.commit()
    second = await service.offer_retention_coupon(db_session, owner_user)
    assert first is not None and second is not None and first.id == second.id  # reused, not duplicated

    # Force it past validity -> the sweep expires it, and the owner has none active.
    first.expires_at = service.utc_now() - service.timedelta(seconds=1)
    await db_session.commit()
    changed = await service.expire_retention_coupons(db_session)
    await db_session.commit()
    assert changed == 1
    assert await service.active_retention_coupon(db_session, owner_user) is None
