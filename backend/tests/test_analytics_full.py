"""Análises completas: what sells and what doesn't, with bot / funnel / plan filters."""

import uuid

import pytest
from sqlalchemy import select

from app.models import TgOrder
from test_flashbot_v2 import PACK, _pay
from test_telegram_bots import _flow, _login, _send, _setup, _start, _tap, apis  # noqa: F401


def _as_user(update: dict, user_id: int) -> dict:
    """The same Telegram update from another person."""
    body = update.get("message") or update["callback_query"]
    body["from"]["id"] = user_id
    chat = body["chat"] if "chat" in body else body["message"]["chat"]
    chat["id"] = user_id
    return update


@pytest.mark.anyio
async def test_full_analytics_shows_what_sells_with_filters(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    flow = _flow(welcome=[], order_bump={"name": "Pack extra", "price": "5.00", "delivery": PACK})
    flow["plans"][0]["delivery"] = {"type": "default", "text": "Acesso VIP"}
    bot, _ = await _setup(client, headers, flow)

    # lead 1 buys the plan with the order bump; lead 2 generates a Pix and leaves
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("bump:y:vip"))
    order = await db_session.scalar(select(TgOrder))
    apis.pix_amount = 24.90
    await _pay(client, db_session, order)
    await _send(client, db_session, bot["id"], _as_user(_start("/start tiktok"), 777))
    await _send(client, db_session, bot["id"], _as_user(_tap("bump:n:vip"), 777))

    data = (await client.get("/api/bots/analytics/full", params={"period": "today"})).json()
    s = data["summary"]
    assert s["leads"] == 2 and s["generated"] == 2 and s["sales"] == 1 and s["revenue"] == 24.9
    assert s["approval"] == 50.0 and s["lead_conversion"] == 50.0 and s["buyers"] == 1
    assert data["previous"]["sales"] == 0
    plan = data["plans"][0]
    assert plan["name"] == "VIP Mensal" and plan["sales"] == 1 and plan["generated"] == 2
    assert data["order_bump"]["sales"] == 1 and data["order_bump"]["rate"] == 100.0
    kinds = {row["kind"]: row for row in data["offer_types"]}
    assert kinds["plan"]["sales"] == 1 and kinds["upsell"]["sales"] == 0
    assert data["customers"]["abandoned_pix"] == 1 and data["customers"]["abandoned_value"] == 19.9
    assert data["customers"]["avg_seconds_to_pay"] is not None
    assert sum(h["sales"] for h in data["hours"]) == 1 and sum(d["sales"] for d in data["weekdays"]) == 1
    sources = {row["name"]: row for row in data["sources"]}
    assert sources["ig_ana"]["sales"] == 1 and sources["tiktok"]["sales"] == 0
    assert data["bots"][0]["id"] == bot["id"] and data["flows"][0]["sales"] == 1
    assert {b["id"] for b in data["options"]["bots"]} == {bot["id"]} and "VIP Mensal" in data["options"]["plans"]

    # filters: by plan, by bot, by a funnel with nothing
    by_plan = (await client.get("/api/bots/analytics/full", params={"period": "today", "plan": "VIP Mensal"})).json()
    assert by_plan["summary"]["sales"] == 1
    none_plan = (await client.get("/api/bots/analytics/full", params={"period": "today", "plan": "Outro"})).json()
    assert none_plan["summary"]["sales"] == 0 and none_plan["summary"]["generated"] == 0
    by_bot = (await client.get("/api/bots/analytics/full", params={"period": "today", "bot_id": bot["id"]})).json()
    assert by_bot["summary"]["revenue"] == 24.9
    other = (await client.get("/api/bots/analytics/full", params={"period": "today", "flow_id": str(uuid.uuid4())})).json()
    assert other["summary"]["leads"] == 0 and other["summary"]["sales"] == 0
