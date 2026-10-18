"""FlashBot remarketing: per-funnel campaigns, audience, sending through each lead's bot, purchase."""

import pytest
from sqlalchemy import select

from app.bots import campaigns
from app.models import TgCampaign, TgOrder
from test_flashbot_v2 import _pay
from test_telegram_bots import (  # noqa: F401  (apis is a fixture)
    _flow,
    _login,
    _send,
    _setup,
    _start,
    _tap,
    apis,
)


def _campaign(flow_id: str, **offer) -> dict:
    return {
        "name": "Volta pra mim",
        "flow_id": flow_id,
        "definition": {
            "audience": {"target": "not_bought", "period": "total"},
            "messages": [{"text": "Oi {nome}, sentiu saudade?", "buttons": [{"label": "Prévias", "url": "https://t.me/previas"}]}],
            "offer": {"plans": [{"name": "VIP Volta", "price": "9.90", "duration_days": 30}], **offer},
        },
    }


@pytest.mark.anyio
async def test_campaign_reaches_the_funnel_audience_and_sells(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers, _flow(welcome=[], default_delivery={"type": "default", "text": "Bem-vindo de volta"}))
    await _send(client, db_session, bot["id"], _start())

    reach = await client.post("/api/bots/campaigns/estimate", headers=headers, json={"flow_id": flow["id"], "audience": {"target": "not_bought"}})
    assert reach.json() == {"reach": 1, "blocked": 0}
    bought = await client.post("/api/bots/campaigns/estimate", headers=headers, json={"flow_id": flow["id"], "audience": {"target": "bought"}})
    assert bought.json()["reach"] == 0

    created = await client.post("/api/bots/campaigns", headers=headers, json=_campaign(flow["id"]))
    assert created.status_code == 201, created.text
    campaign = created.json()
    assert campaign["status"] == "draft" and campaign["flow_name"] == "Funil Ana"

    started = await client.post(f"/api/bots/campaigns/{campaign['id']}/send", headers=headers)
    assert started.json()["status"] == "sending" and started.json()["total"] == 1
    await campaigns.run_campaigns(db_session)
    message = apis.methods("sendMessage")[-1]
    assert message["text"] == "Oi Lucas, sentiu saudade?"
    rows = message["reply_markup"]["inline_keyboard"]
    assert rows[0][0]["callback_data"] == f"rmk:{campaign['id'].replace('-', '')}:0" and "R$ 9,90" in rows[0][0]["text"]
    assert rows[1][0] == {"text": "Prévias", "url": "https://t.me/previas"}
    await campaigns.run_campaigns(db_session)  # nobody left: finished, nothing sent twice
    await db_session.commit()
    row = await db_session.scalar(select(TgCampaign))
    await db_session.refresh(row)
    assert row.status == "finished" and row.sent == 1
    assert [m["text"] for m in apis.methods("sendMessage")].count("Oi Lucas, sentiu saudade?") == 1

    await _send(client, db_session, bot["id"], _tap(rows[0][0]["callback_data"]))
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.kind == "remarketing" and order.amount == campaigns.Decimal("9.90")
    apis.pix_amount = 9.90
    await _pay(client, db_session, order)
    assert "Bem-vindo de volta" in [m["text"] for m in apis.methods("sendMessage")]
    listed = (await client.get(f"/api/bots/campaigns?flow_id={flow['id']}")).json()["campaigns"]
    assert listed[0]["sales"] == 1 and listed[0]["revenue"] == "9.90"
    # the buyer left the "não compraram" audience
    reach = await client.post("/api/bots/campaigns/estimate", headers=headers, json={"flow_id": flow["id"], "audience": {"target": "not_bought"}})
    assert reach.json()["reach"] == 0


@pytest.mark.anyio
async def test_campaign_order_bump_and_validation(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers, _flow(welcome=[]))
    # the funnel has no default delivery: a plan without its own delivery is refused
    refused = await client.post("/api/bots/campaigns", headers=headers, json=_campaign(flow["id"]))
    assert refused.status_code == 422 and "entrega padrão" in refused.json()["detail"]

    body = _campaign(flow["id"], order_bump={"name": "Pack", "price": "5.00", "delivery": {"type": "default", "text": "Pack ok"}})
    body["definition"]["offer"]["plans"][0]["delivery"] = {"type": "default", "text": "VIP ok"}
    created = (await client.post("/api/bots/campaigns", headers=headers, json=body)).json()
    hex_id = created["id"].replace("-", "")
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap(f"rmk:{hex_id}:0"))
    question = apis.methods("sendMessage")[-1]
    assert question["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"rmkb:y:{hex_id}:0"
    await _send(client, db_session, bot["id"], _tap(f"rmkb:y:{hex_id}:0"))
    assert apis.methods("pix.create")[-1]["amount"] == 14.9
    # another operation's campaign id is never honored
    await _send(client, db_session, bot["id"], _tap("rmk:" + "0" * 32 + ":0"))
    assert len(apis.methods("pix.create")) == 1

    scheduled = await client.post(f"/api/bots/campaigns/{created['id']}/schedule", headers=headers, json={"scheduled_at": "2000-01-01T00:00:00Z"})
    assert scheduled.status_code == 422
    deleted = await client.delete(f"/api/bots/campaigns/{created['id']}", headers=headers)
    assert deleted.status_code == 204
