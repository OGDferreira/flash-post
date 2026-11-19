from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import smokepay
from app.bots.smokepay import PixCharge
from app.models import PlatformLiberationCode, PlatformPlan, PlatformSubscription, PlatformSubscriptionCharge
from app.models.platform_subscription import CHARGE_PAID, SUB_ACTIVE, SUB_PAST_DUE
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
async def test_new_owner_must_pick_plan_collaborator_and_admin_exempt(
    db_session: AsyncSession, owner, collaborator, super_admin
) -> None:
    # Default trial is 0: a new owner gets no free access and sees the paywall.
    owner_user, _ = owner
    owner_state = await service.access_state(db_session, owner_user)
    assert owner_state["required"] is True
    assert owner_state["active"] is False
    assert owner_state["in_trial"] is False
    # Exempt: collaborators (no owned operation) and the Super Admin.
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


# ---------------------------------------- Authorized recurring card billing (Stripe)

import hashlib
import json
import hmac
import time

from pydantic import SecretStr

from app.bots import stripe_gateway
from app.core.config import get_settings
from app.models.platform_subscription import BILLING_CARD


def _enable_stripe(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", SecretStr("stripe_test_key"))
    monkeypatch.setattr(settings, "stripe_webhook_secret", SecretStr("stripe_webhook_test"))


def _stripe_headers(raw: bytes, secret: str = "stripe_webhook_test") -> dict:
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}


def test_interval_for_plan_maps_known_cycles() -> None:
    assert stripe_gateway.interval_for_plan("weekly") == "week"
    assert stripe_gateway.interval_for_plan("monthly") == "month"
    assert stripe_gateway.interval_for_plan("annual") == "year"
    assert stripe_gateway.interval_for_plan("odd") is None


@pytest.mark.anyio
async def test_card_available_and_checkout_opens_stripe(
    db_session: AsyncSession, client: AsyncClient, owner, monkeypatch
) -> None:
    _enable_stripe(monkeypatch)
    plan = await _plan(db_session, "monthly")

    captured: dict = {}

    async def _fake_checkout(**kwargs):
        captured.update(kwargs)
        return stripe_gateway.SubscriptionCheckout(session_id="cs_1", url="https://checkout.stripe.com/pay/cs_1")

    monkeypatch.setattr(stripe_gateway, "create_subscription_checkout", _fake_checkout)

    await _login(client, "owner@example.com", "correct horse battery staple")
    me = await client.get("/api/subscription/me")
    assert me.status_code == 200 and me.json()["card_available"] is True

    resp = await client.post(
        "/api/subscription/checkout/stripe", headers={"X-CSRF-Token": await _csrf(client)},
        json={"plan_id": str(plan.id)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["url"] == "https://checkout.stripe.com/pay/cs_1"
    assert captured["interval"] == "month"
    assert captured["metadata"]["plan_id"] == str(plan.id)


@pytest.mark.anyio
async def test_stripe_webhook_attaches_then_invoice_extends_access(
    db_session: AsyncSession, client: AsyncClient, owner, monkeypatch
) -> None:
    _enable_stripe(monkeypatch)
    owner_user, _ = owner
    plan = await _plan(db_session, "monthly")
    sub = await service.get_or_create(db_session, owner_user)
    await db_session.commit()

    # 1) Checkout completed -> attach Stripe ids to the owner's subscription.
    completed = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "mode": "subscription", "customer": "cus_1", "subscription": "sub_1",
            "metadata": {"sub_id": str(sub.id), "plan_id": str(plan.id)},
        }},
    }
    raw = json.dumps(completed).encode()
    r1 = await client.post("/api/subscription/pay/stripe", content=raw, headers=_stripe_headers(raw))
    assert r1.status_code == 200, r1.text
    await db_session.refresh(sub)
    assert sub.stripe_subscription_id == "sub_1" and sub.billing_method == BILLING_CARD

    # 2) invoice.paid -> access window set to the invoice period end.
    period_end = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    invoice = {
        "type": "invoice.paid",
        "data": {"object": {
            "id": "in_1", "subscription": "sub_1", "amount_paid": 5990,
            "lines": {"data": [{"period": {"end": period_end}}]},
        }},
    }
    raw2 = json.dumps(invoice).encode()
    r2 = await client.post("/api/subscription/pay/stripe", content=raw2, headers=_stripe_headers(raw2))
    assert r2.status_code == 200, r2.text
    await db_session.refresh(sub)
    assert sub.status == SUB_ACTIVE
    assert service.is_active(sub) is True
    assert service.effective_until(sub) > datetime.now(timezone.utc) + timedelta(days=29)

    # Idempotent: re-delivering the same invoice doesn't double-extend.
    before = sub.current_period_end
    r3 = await client.post("/api/subscription/pay/stripe", content=raw2, headers=_stripe_headers(raw2))
    assert r3.status_code == 200
    await db_session.refresh(sub)
    assert sub.current_period_end == before


@pytest.mark.anyio
async def test_stripe_webhook_rejects_bad_signature(client: AsyncClient, owner, monkeypatch) -> None:
    _enable_stripe(monkeypatch)
    raw = json.dumps({"type": "invoice.paid", "data": {"object": {}}}).encode()
    resp = await client.post(
        "/api/subscription/pay/stripe", content=raw,
        headers={"stripe-signature": "t=1,v1=deadbeef", "content-type": "application/json"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_cancel_card_billing_calls_stripe_and_keeps_access(
    db_session: AsyncSession, client: AsyncClient, owner, monkeypatch
) -> None:
    _enable_stripe(monkeypatch)
    owner_user, _ = owner
    sub = await service.get_or_create(db_session, owner_user)
    sub.stripe_subscription_id = "sub_9"
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=10)
    sub.status = SUB_ACTIVE
    await db_session.commit()

    calls: list = []

    async def _fake_cancel(subscription_id, *, at_period_end=True):
        calls.append((subscription_id, at_period_end))

    monkeypatch.setattr(stripe_gateway, "cancel_subscription", _fake_cancel)

    await _login(client, "owner@example.com", "correct horse battery staple")
    resp = await client.post("/api/subscription/cancel", headers={"X-CSRF-Token": await _csrf(client)})
    assert resp.status_code == 200, resp.text
    assert calls == [("sub_9", True)]
    # Access stays until the window ends.
    assert resp.json()["active"] is True
