"""Funil Frankenstein: rank the upsell steps of every funnel and build a new funnel from them."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from test_telegram_bots import (  # noqa: F401  (apis is a fixture)
    _login,
    _send,
    _setup,
    _start,
    apis,
)

from app.models import TgLead, TgOrder


def _flow_with_upsells(steps: list[dict]) -> dict:
    return {
        "offer": {"text": "Escolha 👇"},
        "plans": [{"id": "vip", "name": "VIP", "price": "19.90", "duration_days": 30}],
        "default_delivery": {"type": "default", "text": "Acesso liberado ✅"},
        "upsells": steps,
    }


async def _create_flow(client, headers, name, definition) -> dict:
    res = await client.post("/api/bots/flows", headers=headers, json={"name": name, "definition": definition})
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.anyio
async def test_frankenstein_lists_steps_and_builds_a_self_contained_funnel(client, owner, db_session) -> None:
    headers = await _login(client)
    a = await _create_flow(client, headers, "Funil A", _flow_with_upsells([
        {"name": "Bônus A", "price": "9.90", "text": "Quer o bônus A?"},
    ]))
    b = await _create_flow(client, headers, "Funil B", _flow_with_upsells([
        {"name": "Bônus B1", "price": "29.90", "text": "Quer B1?"},
        {"name": "Bônus B2", "price": "49.90", "text": "Quer B2?"},
    ]))

    steps = (await client.get("/api/bots/flows/frankenstein/steps?period=all", headers=headers)).json()["steps"]
    assert {"Bônus A", "Bônus B1", "Bônus B2"} <= {s["name"] for s in steps}

    # Pick two steps, in a deliberate order, from two different funnels.
    chosen = [{"flow_id": b["id"], "index": 1}, {"flow_id": a["id"], "index": 0}]
    created = await client.post(
        "/api/bots/flows/frankenstein", headers=headers, json={"name": "Meu Frank", "steps": chosen}
    )
    assert created.status_code == 201, created.text
    definition = created.json()["definition"]
    assert [u["name"] for u in definition["upsells"]] == ["Bônus B2", "Bônus A"]
    # Each step carries its own delivery (baked from the source funnel's default), so the new
    # funnel is valid without a default delivery of its own and starts with no plans to edit.
    assert all(u["delivery"] is not None for u in definition["upsells"])
    assert definition["plans"] == []


@pytest.mark.anyio
async def test_frankenstein_ranks_steps_by_what_they_sold(client, owner, db_session, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers, _flow_with_upsells([
        {"name": "Campeão", "price": "99.90", "text": "Quer?"},
    ]))
    await _create_flow(client, headers, "Sem vendas", _flow_with_upsells([
        {"name": "Parado", "price": "9.90", "text": "Quer?"},
    ]))
    await _send(client, db_session, bot["id"], _start())
    lead = await db_session.scalar(select(TgLead))
    db_session.add(
        TgOrder(
            workspace_id=lead.workspace_id,
            bot_id=lead.bot_id,
            lead_id=lead.id,
            flow_id=uuid.UUID(flow["id"]),
            kind="upsell",
            offer_id="up0",
            offer_name="Campeão",
            amount=Decimal("99.90"),
            status="paid",
            paid_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    steps = (await client.get("/api/bots/flows/frankenstein/steps?period=all", headers=headers)).json()["steps"]
    assert steps[0]["name"] == "Campeão"
    assert steps[0]["paid"] == 1
    assert steps[0]["revenue"] == 99.9
