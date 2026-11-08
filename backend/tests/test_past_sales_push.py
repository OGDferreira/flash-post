"""Configurações -> receive the sales of a past period again as push notifications."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.time import utc_now
from app.models import Affiliation, PushSubscription, TgOrder
from app.models.sharkbot import SharkTransaction
from app.notifications import replay
from tests.test_affiliates import _make_owner
from tests.test_wallet import _as, _paid


@pytest.mark.anyio
async def test_past_sales_are_sent_again_oldest_first(client, db_session, owner, monkeypatch) -> None:
    chief, chief_ws = owner
    sent: list[list[dict]] = []

    async def fake_send(user_id, notices):
        sent.append(notices)
        return len(notices)

    monkeypatch.setattr(replay, "send", fake_send)
    headers = await _as(client, "owner@example.com", "correct horse battery staple")
    # no device with notifications on: nothing to send to
    refused = await client.post("/api/notifications/past-sales", headers=headers, json={"period": "today"})
    assert refused.status_code == 409

    db_session.add(PushSubscription(user_id=chief.id, workspace_id=chief_ws.id, endpoint="https://push.example/1", p256dh="k", auth="a"))
    await _paid(db_session, chief_ws)  # a Flash sale (R$ 19,90)
    now = utc_now()
    db_session.add(SharkTransaction(workspace_id=chief_ws.id, transaction_key="s1", status="paid", amount=Decimal("12.90"),
                                    created_at_source=now, paid_at=now - timedelta(minutes=5)))
    partner, partner_ws = await _make_owner(db_session, "socia")
    db_session.add(Affiliation(chief_user_id=chief.id, affiliate_user_id=partner.id, participation_percent=Decimal("10")))
    await _paid(db_session, partner_ws)
    order = (await db_session.scalars(select(TgOrder).where(TgOrder.workspace_id == partner_ws.id))).first()
    order.split_chief_user_id, order.split_amount = chief.id, Decimal("1.50")
    await db_session.commit()

    done = await client.post("/api/notifications/past-sales", headers=headers, json={"period": "today"})
    assert done.status_code == 200, done.text
    assert done.json()["count"] == 3
    titles = [n["title"] for n in sent[0]]
    assert titles[0] == "🦈 Nova venda - Shark Bot!"  # the oldest first
    assert set(titles) == {"🦈 Nova venda - Shark Bot!", "⚡ Nova venda!", "💰 Comissão recebida!"}
    bodies = " ".join(n["body"] for n in sent[0])
    assert "R$ 19,90" in bodies and "R$ 12,90" in bodies and "R$ 1,50 🤑 da venda de Socia" in bodies and " às " in bodies

    # another period with nothing in it
    empty = await client.post("/api/notifications/past-sales", headers=headers,
                              json={"period": "custom", "start_date": "2026-01-01", "end_date": "2026-01-02"})
    assert empty.json()["count"] == 0
