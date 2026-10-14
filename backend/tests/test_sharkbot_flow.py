"""SharkBot payloads from the integration (user_joined, payment_created,
payment_approved): idempotency, ordering, dates, isolation and bot metrics."""

import asyncio
import copy
from decimal import Decimal
from urllib.parse import urlparse
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SharkLead, SharkTransaction
from tests.test_loops import _active_account, _csrf, _login

USER_JOINED = {
    "event": "user_joined",
    "timestamp": 1791990403,
    "webhook_id": "abc123",
    "data": {
        "customer": {
            "id": "lead_id_123", "telegram_id": "123456789", "first_name": "João",
            "last_name": "Silva", "username": "joaosilva", "is_vip": False,
            "email": "joao@example.com", "phone": "11999999999",
        },
        "bot": {"id": "bot_id_123", "name": "Meu Bot", "username": "meubot"},
        "flow": {"id": "flow_id_123", "name": "Fluxo Principal"},
        "tracking": {"utm_source": "instagram", "utm_campaign": "black_friday", "ip": "189.1.2.3"},
        "joined_at": "2026-10-14T15:06:43Z",
    },
}
PAYMENT_CREATED = {
    "data": {
        "customer": copy.deepcopy(USER_JOINED["data"]["customer"]),
        "bot": {"id": "bot_id_123", "name": "Meu Bot", "username": "meubot"},
        "flow": {"id": "flow_id_123", "name": "Fluxo Principal"},
        "transaction": {
            "id": "payment_id_123", "external_id": "ext_123", "status": "pending", "amount": 97,
            "currency": "BRL", "gateway": "pushinpay", "plan_name": "Plano Premium", "type": "normal",
            "payment_method": "pix", "pix_code": "00020126...", "sales_code": "vendedor123",
            "created_at": "2026-10-14T15:06:43Z",
        },
        "tracking": {"utm_source": "instagram", "utm_campaign": "black_friday"},
    },
    "event": "payment_created",
    "timestamp": 1791990403,
    "webhook_id": "abc123",
}
PAYMENT_APPROVED = {
    "webhook_id": "abc123",
    "data": {
        "customer": {**copy.deepcopy(USER_JOINED["data"]["customer"]), "is_vip": True},
        "bot": {"id": "bot_id_123", "name": "Meu Bot", "username": "meubot"},
        "flow": {"id": "flow_id_123", "name": "Fluxo Principal"},
        "transaction": {
            "id": "payment_id_123", "external_id": "ext_123", "status": "paid", "amount": 97,
            "currency": "BRL", "gateway": "pushinpay", "plan_name": "Plano Premium", "type": "normal",
            "payment_method": "pix", "sales_code": "vendedor123",
            "created_at": "2026-10-14T15:06:43Z", "paid_at": "2026-10-14T15:06:43Z",
        },
        "tracking": {"utm_source": "kwai", "utm_medium": "712843014"},
        "contact_capture_status": "completed",
    },
    "event": "payment_approved",
    "timestamp": 1791990403,
}


def _variant(payload: dict, **changes) -> dict:
    result = copy.deepcopy(payload)
    for path, value in changes.items():
        target = result
        *parents, leaf = path.split("__")
        for key in parents:
            target = target[key]
        target[leaf] = value
    return result


async def _webhook(client: AsyncClient, account_id=None) -> str:
    await _login(client, "owner@example.com", "correct horse battery staple")
    config = (await client.get("/api/sharkbot/webhook/config")).json()
    path = urlparse(config["webhook_url"]).path
    return f"{path}?account={account_id}" if account_id else path


async def _summary(client: AsyncClient, day: str) -> dict:
    response = await client.get(
        "/api/analytics/summary",
        params={"period": "custom", "start_date": day, "end_date": day},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio
async def test_reference_flow_counts_one_lead_one_pix_one_sale(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    path = await _webhook(client)
    for payload in (USER_JOINED, USER_JOINED, PAYMENT_CREATED, PAYMENT_APPROVED, PAYMENT_APPROVED):
        response = await client.post(path, json=payload)
        assert response.status_code == 200, response.text

    assert await db_session.scalar(select(func.count(SharkLead.id))) == 1
    transaction = await db_session.scalar(select(SharkTransaction))
    assert transaction.status == "paid"
    assert transaction.amount == Decimal("97.00")
    assert transaction.bot_id == "bot_id_123" and transaction.flow_id == "flow_id_123"
    assert transaction.account_id is None  # no verifiable Instagram account in the payload

    summary = await _summary(client, "2026-10-14")
    assert (summary["leads"], summary["pix_generated"], summary["pix_paid"]) == (1, 1, 1)
    assert summary["pix_paid_amount"] == "97.00"


@pytest.mark.anyio
async def test_same_webhook_id_does_not_merge_different_leads(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    path = await _webhook(client)
    other = _variant(USER_JOINED, data__customer__id="lead_id_999", data__customer__telegram_id="42")
    assert (await client.post(path, json=USER_JOINED)).json()["accepted"] == 1
    assert (await client.post(path, json=other)).json()["accepted"] == 1
    assert await db_session.scalar(select(func.count(SharkLead.id))) == 2


@pytest.mark.anyio
async def test_pix_generated_is_not_revenue(client: AsyncClient, owner) -> None:
    path = await _webhook(client)
    await client.post(path, json=PAYMENT_CREATED)
    summary = await _summary(client, "2026-10-14")
    assert summary["pix_generated"] == 1
    assert summary["pix_paid"] == 0
    assert summary["pix_paid_amount"] == "0.00"


@pytest.mark.anyio
async def test_out_of_order_approval_is_never_downgraded(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    path = await _webhook(client)
    approved = await client.post(path, json=PAYMENT_APPROVED)
    late_pending = await client.post(path, json=PAYMENT_CREATED)
    assert approved.json()["accepted"] == 1
    assert late_pending.json() == {"accepted": 0, "duplicates": 1, "ignored": 0}
    transaction = await db_session.scalar(select(SharkTransaction))
    assert transaction.status == "paid"
    assert await db_session.scalar(select(func.count(SharkTransaction.id))) == 1
    summary = await _summary(client, "2026-10-14")
    assert (summary["pix_generated"], summary["pix_paid"]) == (1, 1)


@pytest.mark.anyio
async def test_generation_and_approval_days_use_app_time_zone(client: AsyncClient, owner) -> None:
    path = await _webhook(client)
    # 02:30 UTC on the 14th is still the 13th in São Paulo (UTC-3).
    created = _variant(PAYMENT_CREATED, data__transaction__created_at="2026-10-14T02:30:00Z")
    approved = _variant(
        PAYMENT_APPROVED,
        data__transaction__created_at="2026-10-14T02:30:00Z",
        data__transaction__paid_at="2026-10-14T04:00:00Z",
    )
    await client.post(path, json=created)
    await client.post(path, json=approved)
    day13 = await _summary(client, "2026-10-13")
    day14 = await _summary(client, "2026-10-14")
    assert (day13["pix_generated"], day13["pix_paid"]) == (1, 0)
    assert (day14["pix_generated"], day14["pix_paid"], day14["pix_paid_amount"]) == (0, 1, "97.00")


@pytest.mark.anyio
async def test_missing_amount_is_unavailable_not_zero(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    path = await _webhook(client)
    no_amount = copy.deepcopy(PAYMENT_APPROVED)
    del no_amount["data"]["transaction"]["amount"]
    await client.post(path, json=no_amount)
    transaction = await db_session.scalar(select(SharkTransaction))
    assert transaction.amount is None
    summary = await _summary(client, "2026-10-14")
    assert summary["pix_paid"] == 1
    assert summary["pix_paid_without_amount"] == 1


@pytest.mark.anyio
async def test_concurrent_redeliveries_create_a_single_transaction(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    """Parallel deliveries in separate DB sessions (as on the server)."""
    from datetime import datetime, timezone

    from app.core.database import get_session_factory
    from app.shark.ingest import parse_event, upsert_transaction

    _user, workspace = owner
    workspace_id = workspace.id
    event = parse_event(PAYMENT_APPROVED)

    async def deliver() -> bool:
        async with get_session_factory()() as session:
            for _attempt in range(5):
                try:
                    changed = await upsert_transaction(
                        session, workspace_id, event, None, datetime.now(timezone.utc)
                    )
                    await session.commit()
                    return changed
                except Exception:
                    await session.rollback()
                    await asyncio.sleep(0.05)
            raise AssertionError("delivery kept failing")

    results = await asyncio.gather(*(deliver() for _ in range(5)))
    assert results.count(True) == 1
    assert await db_session.scalar(select(func.count(SharkTransaction.id))) == 1


@pytest.mark.anyio
async def test_account_url_attributes_sales_and_rejects_foreign_accounts(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "shark_attributed")
    db_session.add(account)
    await db_session.commit()
    path = await _webhook(client, account.id)
    assert (await client.post(path, json=PAYMENT_APPROVED)).status_code == 200
    transaction = await db_session.scalar(select(SharkTransaction))
    assert transaction.account_id == account.id

    base = path.split("?")[0]
    foreign = await client.post(f"{base}?account={uuid.uuid4()}", json=PAYMENT_APPROVED)
    assert foreign.status_code == 404


@pytest.mark.anyio
async def test_bot_performance_ranks_bots_with_cohort_conversions(client: AsyncClient, owner) -> None:
    path = await _webhook(client)
    # Bot A: 2 leads, 2 PIX, 1 paid (97). Bot B: 1 lead, 1 PIX paid (200).
    await client.post(path, json=USER_JOINED)
    await client.post(path, json=_variant(USER_JOINED, data__customer__id="lead_2"))
    await client.post(path, json=PAYMENT_CREATED)
    await client.post(path, json=PAYMENT_APPROVED)
    await client.post(
        path,
        json=_variant(PAYMENT_CREATED, data__customer__id="lead_2", data__transaction__id="pay_2"),
    )
    bot_b = {"id": "bot_b", "name": "Bot B"}
    await client.post(path, json=_variant(USER_JOINED, data__customer__id="lead_b", data__bot=bot_b))
    await client.post(
        path,
        json=_variant(
            PAYMENT_APPROVED,
            data__customer__id="lead_b",
            data__bot=bot_b,
            data__transaction__id="pay_b",
            data__transaction__amount=200,
        ),
    )
    response = await client.get(
        "/api/analytics/bots",
        params={"period": "custom", "start_date": "2026-10-14", "end_date": "2026-10-14"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["bot_id"] for row in body["rows"]] == ["bot_b", "bot_id_123"]
    bot_a = body["rows"][1]
    assert (bot_a["leads"], bot_a["pix_generated"], bot_a["payments_approved"]) == (2, 2, 1)
    assert bot_a["revenue"] == "97.00"
    assert bot_a["lead_to_buyer_rate"] == 50.0
    assert bot_a["pix_to_paid_rate"] == 50.0
    totals = body["totals"]
    assert (totals["leads"], totals["payments_approved"], totals["revenue"]) == (3, 2, "297.00")

    by_sales_asc = await client.get(
        "/api/analytics/bots",
        params={"period": "custom", "start_date": "2026-10-14", "end_date": "2026-10-14",
                "sort": "sales", "order": "asc", "group_by": "flow"},
    )
    assert by_sales_asc.status_code == 200
    assert by_sales_asc.json()["group_by"] == "flow"


@pytest.mark.anyio
async def test_bot_performance_is_owner_only_and_workspace_isolated(
    client: AsyncClient, owner, collaborator
) -> None:
    path = await _webhook(client)
    await client.post(path, json=PAYMENT_APPROVED)
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    client.cookies.clear()
    await _login(client, "collaborator@example.com", "collaborator password")
    assert (await client.get("/api/analytics/bots")).status_code == 403
