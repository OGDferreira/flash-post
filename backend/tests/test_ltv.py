"""LTV do lead: a safra do período somada ao longo da vida inteira, além da 1ª venda."""

import pytest
from sqlalchemy import select

from app.models import TgOrder
from test_analytics_full import _as_user
from test_flashbot_v2 import _pay
from test_telegram_bots import _flow, _login, _send, _setup, _start, _tap, apis  # noqa: F401


@pytest.mark.anyio
async def test_ltv_first_sale_and_lifetime(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    flow = _flow(welcome=[])
    flow["plans"][0]["delivery"] = {"type": "default", "text": "Acesso VIP"}
    bot, _ = await _setup(client, headers, flow)

    # lead 1 compra o plano; lead 2 entra e não compra
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    order = await db_session.scalar(select(TgOrder))
    apis.pix_amount = 19.90
    await _pay(client, db_session, order)
    await _send(client, db_session, bot["id"], _as_user(_start(), 777))

    data = (await client.get("/api/bots/analytics/ltv", params={"period": "today"})).json()
    s = data["summary"]
    assert s["cohort"] == 2 and s["buyers"] == 1 and s["conversion"] == 50.0
    assert s["total_ltv"] == 19.9 and s["avg_ltv"] == 19.9 and s["avg_first_sale"] == 19.9
    assert s["uplift"] == 1.0 and s["expansion_revenue"] == 0.0
    assert s["avg_ltv_per_lead"] == pytest.approx(9.95, abs=0.01)

    kinds = {row["kind"]: row for row in data["by_kind"]}
    assert kinds["plan"]["sales"] == 1 and kinds["plan"]["revenue"] == 19.9
    assert kinds["upsell"]["sales"] == 0 and kinds["remarketing"]["revenue"] == 0.0

    assert len(data["top_leads"]) == 1
    top = data["top_leads"][0]
    assert top["ltv"] == 19.9 and top["first_sale"] == 19.9 and top["orders"] == 1
    assert top["first_at"] is not None


@pytest.mark.anyio
async def test_ltv_empty_when_no_buyers(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[]))
    await _send(client, db_session, bot["id"], _start())

    data = (await client.get("/api/bots/analytics/ltv", params={"period": "today"})).json()
    assert data["summary"]["cohort"] == 1 and data["summary"]["buyers"] == 0
    assert data["summary"]["avg_ltv"] == 0.0 and data["summary"]["uplift"] == 0.0
    assert data["top_leads"] == []
