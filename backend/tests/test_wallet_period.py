"""Wallet cards that follow the period filter."""

import pytest
from sqlalchemy import select

from tests.test_partners import CHIEF_PASSWORD, _as
from tests.test_telegram_bots import _paid_event, _send, _setup, _signed, _start, _tap, apis  # noqa: F401


@pytest.mark.anyio
async def test_wallet_period_cards_follow_the_filter(client, db_session, owner, apis) -> None:
    from app.models import TgOrder

    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    raw, sig = _signed(_paid_event(order.id))
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200

    today = (await client.get("/api/wallet/period?period=today")).json()
    assert today["flash_sales"] == 19.9 and today["flash_revenue"] == 19.9 and today["shark_revenue"] == 0.0
    assert "fees" not in today  # the Flash fees are the Super Admin's only
    yesterday = (await client.get("/api/wallet/period?period=yesterday")).json()
    assert yesterday["flash_revenue"] == 0.0
    assert (await client.get("/api/wallet/period?period=all")).json()["flash_revenue"] == 19.9
