"""Native A/B test of two funnel versions on a bot."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import ab_tests
from app.models import TgAbTest, TgBot, TgLead, TgOrder

from test_telegram_bots import _flow, _login, _send, _setup, apis  # noqa: F401


def _start_as(uid: int, text: str = "/start ig_ana") -> dict:
    user = {"id": uid, "is_bot": False, "first_name": f"Lead{uid}", "username": f"lead{uid}"}
    return {"message": {"message_id": 1, "from": user, "chat": {"id": uid, "type": "private"}, "text": text}}


async def _two_flows_and_bot(client, headers):
    """Bot running funnel A, plus a second funnel B, both owned by the operation."""
    bot, flow_a = await _setup(client, headers)
    flow_b = await client.post("/api/bots/flows", headers=headers, json={"name": "Versão B", "definition": _flow()})
    assert flow_b.status_code == 201, flow_b.text
    return bot, flow_a, flow_b.json()


@pytest.mark.anyio
async def test_create_distributes_leads_and_shows_results(client, db_session: AsyncSession, owner, apis, monkeypatch) -> None:
    headers = await _login(client)
    bot, flow_a, flow_b = await _two_flows_and_bot(client, headers)

    created = await client.post(
        "/api/bots/ab-tests",
        headers=headers,
        json={"name": "Teste de capa", "bot_id": bot["id"], "flow_a_id": flow_a["id"], "flow_b_id": flow_b["id"], "weight_a": 50},
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "active"

    # The bot now runs the lead's drawn funnel; randbelow < weight_a (50) always lands on A.
    monkeypatch.setattr(ab_tests.secrets, "randbelow", lambda n: 0)
    for uid in (111, 222, 333):
        assert (await _send(client, db_session, bot["id"], _start_as(uid))).status_code == 200

    leads = (await db_session.scalars(select(TgLead).where(TgLead.bot_id == uuid.UUID(bot["id"])))).all()
    assert len(leads) == 3
    assert {str(lead.flow_id) for lead in leads} == {flow_a["id"]}

    listing = await client.get("/api/bots/ab-tests", headers=headers)
    assert listing.status_code == 200, listing.text
    test = listing.json()["tests"][0]
    assert test["results"]["a"]["leads"] == 3
    assert test["results"]["b"]["leads"] == 0


@pytest.mark.anyio
async def test_weight_chooses_variant_b(client, db_session: AsyncSession, owner, apis, monkeypatch) -> None:
    headers = await _login(client)
    bot, flow_a, flow_b = await _two_flows_and_bot(client, headers)
    created = await client.post(
        "/api/bots/ab-tests",
        headers=headers,
        json={"name": "50/50", "bot_id": bot["id"], "flow_a_id": flow_a["id"], "flow_b_id": flow_b["id"], "weight_a": 50},
    )
    test_id = created.json()["id"]
    # randbelow(100) == 50 is NOT < 50 -> variant B.
    monkeypatch.setattr(ab_tests.secrets, "randbelow", lambda n: 50)
    assert (await _send(client, db_session, bot["id"], _start_as(444))).status_code == 200
    lead = await db_session.scalar(select(TgLead).where(TgLead.bot_id == uuid.UUID(bot["id"])))
    assert str(lead.flow_id) == flow_b["id"]

    # A lead already drawn keeps its variant even if the weight is later changed.
    patched = await client.patch(f"/api/bots/ab-tests/{test_id}", headers=headers, json={"weight_a": 90})
    assert patched.status_code == 200 and patched.json()["weight_a"] == 90
    monkeypatch.setattr(ab_tests.secrets, "randbelow", lambda n: 0)  # would now draw A
    assert (await _send(client, db_session, bot["id"], _start_as(444))).status_code == 200
    await db_session.refresh(lead)
    assert str(lead.flow_id) == flow_b["id"]


@pytest.mark.anyio
async def test_stopping_reverts_bot_to_single_funnel(client, db_session: AsyncSession, owner, apis) -> None:
    headers = await _login(client)
    bot, flow_a, flow_b = await _two_flows_and_bot(client, headers)
    created = await client.post(
        "/api/bots/ab-tests",
        headers=headers,
        json={"name": "Teste", "bot_id": bot["id"], "flow_a_id": flow_a["id"], "flow_b_id": flow_b["id"], "weight_a": 50},
    )
    test_id = created.json()["id"]
    bot_row = await db_session.get(TgBot, uuid.UUID(bot["id"]))
    await db_session.refresh(bot_row)
    assert str(bot_row.ab_test_id) == test_id

    stopped = await client.post(f"/api/bots/ab-tests/{test_id}/stop", headers=headers)
    assert stopped.status_code == 200 and stopped.json()["status"] == "stopped"
    await db_session.refresh(bot_row)
    assert bot_row.ab_test_id is None  # reverts to its single funnel (flow A)

    # A stopped test keeps its results; a rejected duplicate-flow test is refused.
    assert (await client.get("/api/bots/ab-tests", headers=headers)).json()["tests"][0]["status"] == "stopped"
    dup = await client.post(
        "/api/bots/ab-tests",
        headers=headers,
        json={"name": "x", "bot_id": bot["id"], "flow_a_id": flow_a["id"], "flow_b_id": flow_a["id"], "weight_a": 50},
    )
    assert dup.status_code == 422
