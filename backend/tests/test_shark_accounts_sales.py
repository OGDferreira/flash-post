"""Several SharkBot accounts per workspace, origin of each sale, de-duplication,
paginated sales list and the conversion metrics with their attribution rules."""

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SharkAccount, SharkLead, SharkTransaction, Workspace
from tests.test_loops import _active_account, _csrf, _login
from tests.test_sharkbot_flow import PAYMENT_APPROVED, PAYMENT_CREATED, USER_JOINED

NOW = datetime.now(timezone.utc)
PASSWORD = "correct horse battery staple"


async def _new_account(client: AsyncClient, name: str, external: str | None = None) -> dict:
    response = await client.post(
        "/api/sharkbot/accounts",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"name": name, "external_account_id": external},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _path(url: str) -> str:
    return urlparse(url).path


@pytest.mark.anyio
async def test_accounts_crud_isolation_and_rotation(
    client: AsyncClient, db_session: AsyncSession, owner, collaborator
) -> None:
    await _login(client, "owner@example.com", PASSWORD)
    listing = (await client.get("/api/sharkbot/accounts")).json()
    assert listing[0]["is_default"] is True and listing[0]["name"] == "Conta principal"
    a = await _new_account(client, "Loja A", "shark-123")
    b = await _new_account(client, "Loja B")
    assert a["webhook_url"] != b["webhook_url"] != listing[0]["webhook_url"]
    token = await _csrf(client)
    dup = await client.post(
        "/api/sharkbot/accounts", headers={"X-CSRF-Token": token}, json={"name": "loja a"}
    )
    assert dup.status_code == 409
    blank = await client.post(
        "/api/sharkbot/accounts", headers={"X-CSRF-Token": token}, json={"name": "   "}
    )
    assert blank.status_code == 422

    old_path = _path(a["webhook_url"])
    rotated = (await client.post(f"/api/sharkbot/accounts/{a['id']}/rotate", headers={"X-CSRF-Token": token})).json()
    assert _path(rotated["webhook_url"]) != old_path
    assert (await client.post(old_path, json=USER_JOINED)).status_code == 404  # old URL is dead
    assert (await client.post(_path(rotated["webhook_url"]), json=USER_JOINED)).status_code == 200

    # A collaborator cannot manage Shark accounts or read sales.
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": token})
    await _login(client, "collaborator@example.com", "collaborator password")
    assert (await client.get("/api/sharkbot/accounts")).status_code == 403
    assert (await client.get("/api/sharkbot/sales")).status_code == 403


@pytest.mark.anyio
async def test_sale_origin_and_cross_url_duplicates(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    await _login(client, "owner@example.com", PASSWORD)
    main = (await client.get("/api/sharkbot/accounts")).json()[0]
    shop = await _new_account(client, "Loja A")

    first = await client.post(_path(shop["webhook_url"]), json=PAYMENT_APPROVED)
    assert first.json() == {"accepted": 1, "duplicates": 0, "ignored": 0}
    # The very same payment delivered through another URL is not a second sale.
    again = await client.post(_path(main["webhook_url"]), json=PAYMENT_APPROVED)
    assert again.json()["duplicates"] == 1
    again = await client.post(_path(shop["webhook_url"]), json=PAYMENT_APPROVED)
    assert again.json()["duplicates"] == 1
    assert await db_session.scalar(select(func.count(SharkTransaction.id))) == 1

    sales = (await client.get("/api/sharkbot/sales", params={"period": "all"})).json()
    assert sales["total"] == 1
    assert sales["items"][0]["shark_account_name"] == "Loja A"
    assert Decimal(sales["summary"]["revenue"]) == Decimal("97.00")

    only_main = (await client.get(
        "/api/sharkbot/sales", params={"period": "all", "shark_account_id": shop["id"]}
    )).json()
    assert only_main["total"] == 1
    other = await _new_account(client, "Loja B")
    empty = (await client.get(
        "/api/sharkbot/sales", params={"period": "all", "shark_account_id": other["id"]}
    )).json()
    assert empty["total"] == 0 and empty["summary"]["revenue"] == "0.00"

    # Last event time is tracked per account.
    accounts = (await client.get("/api/sharkbot/accounts")).json()
    assert next(item for item in accounts if item["name"] == "Loja A")["last_event_at"] is not None
    # Foreign / unknown ids are rejected, not silently ignored.
    bogus = "00000000-0000-0000-0000-000000000000"
    assert (await client.get("/api/sharkbot/sales", params={"shark_account_id": bogus})).status_code == 404
    assert (await client.get("/api/sharkbot/sales", params={"account_id": bogus})).status_code == 404


@pytest.mark.anyio
async def test_sales_pagination_filters_and_conversion_rules(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    ig = _active_account(workspace.id, "sales_ig")
    db_session.add(ig)
    await db_session.flush()
    day = NOW - timedelta(hours=1)
    # 4 leads; 2 of them bought (L1: 2 paid purchases, L2: 1); 1 PIX still pending.
    for index in range(4):
        db_session.add(SharkLead(
            workspace_id=workspace.id, lead_key=f"L{index}", bot_id="b", joined_at=day,
        ))
    spec = [("t1", "paid", "100.00", "L0", ig.id), ("t2", "paid", "50.00", "L0", None),
            ("t3", "paid", "30.00", "L1", ig.id), ("t4", "pending", "80.00", "L2", ig.id),
            ("t5", "paid", None, "L3", None)]
    for key, status, amount, lead, account in spec:
        db_session.add(SharkTransaction(
            workspace_id=workspace.id, transaction_key=key, status=status,
            amount=Decimal(amount) if amount else None, lead_key=lead, account_id=account,
            created_at_source=day, paid_at=day if status == "paid" else None,
        ))
    # Outside the period: must not count.
    db_session.add(SharkTransaction(
        workspace_id=workspace.id, transaction_key="old", status="paid", amount=Decimal("999"),
        created_at_source=NOW - timedelta(days=90), paid_at=NOW - timedelta(days=90),
    ))
    await db_session.commit()
    await _login(client, "owner@example.com", PASSWORD)

    page1 = (await client.get("/api/sharkbot/sales", params={"period": "7d", "page_size": 5})).json()
    assert page1["total"] == 4  # paid only (t1,t2,t3,t5); PIX pending is not a sale
    summary = page1["summary"]
    assert summary["purchases"] == 4 and summary["purchases_without_amount"] == 1
    assert Decimal(summary["revenue"]) == Decimal("180.00")
    # Ticket médio: paid sales WITH amount only -> 180 / 3
    assert Decimal(summary["average_ticket"]) == Decimal("60.00")
    assert summary["pix_generated"] == 5 and summary["pix_paid_from_period"] == 4
    assert summary["pix_to_paid_rate"] == 80.0  # 4 paid of 5 generated
    assert summary["leads"] == 4 and summary["lead_buyers"] == 3  # L0, L1, L3 bought
    assert summary["lead_to_purchase_rate"] == 75.0
    assert summary["leads_per_purchase"] == 1.0  # 4 leads / 4 purchases
    assert "coorte" in page1["criteria"]["pix_to_paid_rate"].lower()

    paged = (await client.get("/api/sharkbot/sales", params={"period": "7d", "page_size": 5, "page": 2})).json()
    assert paged["items"] == []
    pending = (await client.get("/api/sharkbot/sales", params={"period": "7d", "status": "pending"})).json()
    assert pending["total"] == 1
    everything = (await client.get("/api/sharkbot/sales", params={"period": "all", "status": "all"})).json()
    assert everything["total"] == 6
    by_account = (await client.get(
        "/api/sharkbot/sales", params={"period": "7d", "account_id": str(ig.id)}
    )).json()
    assert by_account["total"] == 2  # t1, t3 (paid, attributed to the account)
    assert Decimal(by_account["summary"]["revenue"]) == Decimal("130.00")


@pytest.mark.anyio
async def test_conversion_metrics_handle_zero_divisions(
    client: AsyncClient, owner
) -> None:
    await _login(client, "owner@example.com", PASSWORD)
    empty = (await client.get("/api/sharkbot/sales", params={"period": "7d"})).json()["summary"]
    assert empty["pix_to_paid_rate"] is None and empty["lead_to_purchase_rate"] is None
    assert empty["leads_per_purchase"] is None and empty["average_ticket"] is None
    assert Decimal(empty["revenue"]) == 0
