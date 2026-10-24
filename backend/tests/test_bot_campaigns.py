"""FlashBot remarketing: per-funnel campaigns, audience, sending through each lead's bot, purchase."""

import uuid
from datetime import datetime, timedelta, timezone

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


def test_next_fire_daily_hours_weekdays() -> None:
    # "a cada X horas": simply adds the interval.
    base = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)  # a Monday
    every6 = campaigns.Recurrence(kind="hours", hours=6)
    assert campaigns.next_fire(every6, base) == base + timedelta(hours=6)

    # "diário" at 09:00 BRT (UTC-3) -> 12:00 UTC, the next day when already past.
    daily = campaigns.Recurrence(kind="daily", time="09:00")
    assert campaigns.next_fire(daily, base) == datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc)

    # "dias da semana": only Wednesday (2) and Friday (4). From Monday noon -> Wednesday.
    weekly = campaigns.Recurrence(kind="weekdays", time="09:00", weekdays=[2, 4])
    assert campaigns.next_fire(weekly, base) == datetime(2026, 1, 7, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        campaigns.Recurrence(kind="weekdays", time="09:00", weekdays=[])


@pytest.mark.anyio
async def test_recurring_campaign_reschedules_and_keeps_a_run_history(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers, _flow(welcome=[], default_delivery={"type": "default", "text": "oi"}))
    await _send(client, db_session, bot["id"], _start())
    created = (await client.post("/api/bots/campaigns", headers=headers, json=_campaign(flow["id"]))).json()

    # Schedule it to repeat every 2 hours; no explicit first time -> next fire is now + 2h.
    scheduled = await client.post(
        f"/api/bots/campaigns/{created['id']}/schedule", headers=headers, json={"recurrence": {"kind": "hours", "hours": 2}}
    )
    assert scheduled.status_code == 200, scheduled.text
    body = scheduled.json()
    assert body["status"] == "scheduled" and body["recurrence"] == {"kind": "hours", "time": "09:00", "hours": 2, "weekdays": []}

    # Force it due and run the worker: it sends, finishes the run, and reschedules the next one.
    row = await db_session.get(TgCampaign, uuid.UUID(created["id"]))
    row.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    await campaigns.run_campaigns(db_session)
    await campaigns.run_campaigns(db_session)  # drain the batch -> finished
    await db_session.commit()
    await db_session.refresh(row)
    assert row.status == "scheduled" and row.sent == 1  # recurring: back to scheduled, not finished
    assert campaigns.engine.aware(row.scheduled_at) > datetime.now(timezone.utc)  # a future next fire

    runs = (await client.get(f"/api/bots/campaigns/{created['id']}/runs", headers=headers)).json()["runs"]
    assert len(runs) == 1 and runs[0]["status"] == "finished" and runs[0]["sent"] == 1

    # Cancelling the schedule clears the recurrence.
    cleared = await client.post(f"/api/bots/campaigns/{created['id']}/schedule", headers=headers, json={})
    assert cleared.json()["recurrence"] is None


@pytest.mark.anyio
async def test_overlapping_campaigns_are_flagged_as_conflicts(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    _, flow = await _setup(client, headers, _flow(welcome=[], default_delivery={"type": "default", "text": "oi"}))
    first = (await client.post("/api/bots/campaigns", headers=headers, json=_campaign(flow["id"]))).json()
    second = (await client.post("/api/bots/campaigns", headers=headers, json=_campaign(flow["id"]))).json()

    # Nothing is scheduled yet: no conflicts.
    listed = (await client.get(f"/api/bots/campaigns?flow_id={flow['id']}", headers=headers)).json()["campaigns"]
    assert all(c["conflicts"] == [] for c in listed)

    # Scheduling the first makes it a conflict for the (overlapping) second.
    await client.post(f"/api/bots/campaigns/{first['id']}/schedule", headers=headers, json={"recurrence": {"kind": "daily", "time": "08:00"}})
    listed = {c["id"]: c for c in (await client.get(f"/api/bots/campaigns?flow_id={flow['id']}", headers=headers)).json()["campaigns"]}
    assert [c["id"] for c in listed[second["id"]]["conflicts"]] == [first["id"]]
