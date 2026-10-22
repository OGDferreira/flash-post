"""Falcon Bot: folders of funnels (random funnel per lead on /start), the Estratégia numbers
and instant sends after a payment."""

import uuid

import pytest
from sqlalchemy import select

from app.bots import engine
from app.models import TgBot, TgLead, TgOrder
from tests.test_partners import CHIEF_PASSWORD, _as, _partner
from tests.test_telegram_bots import TOKEN, _flow, _login, _paid_event, _send, _signed, apis  # noqa: F401


def _start_as(user_id: int, text: str = "/start") -> dict:
    user = {"id": user_id, "is_bot": False, "first_name": f"Lead {user_id}"}
    return {"message": {"message_id": 1, "from": user, "chat": {"id": user_id, "type": "private"}, "text": text}}


def _tap_as(user_id: int, data: str) -> dict:
    user = {"id": user_id, "is_bot": False, "first_name": f"Lead {user_id}"}
    return {"callback_query": {"id": f"cb{user_id}", "from": user, "data": data,
                               "message": {"message_id": 9, "chat": {"id": user_id, "type": "private"}}}}


async def _pay(client, order: TgOrder) -> None:
    raw, sig = _signed(_paid_event(order.id, amount=float(order.amount)))
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200


def _funnel(welcome: str, price: str) -> dict:
    return _flow(
        welcome=[{"type": "text", "text": welcome}],
        plans=[
            {"id": "vip", "name": "VIP", "price": price, "delivery": {"type": "default", "text": "ok"}},
            {"id": "pro", "name": "PRO", "price": "49.90", "delivery": {"type": "default", "text": "ok"}},
        ],
    )


@pytest.mark.anyio
async def test_folder_bot_gives_each_lead_a_random_funnel_and_strategy_compares_them(
    client, db_session, owner, apis, monkeypatch
) -> None:
    headers = await _login(client)
    a = (await client.post("/api/bots/flows", headers=headers, json={"name": "Funil A", "definition": _funnel("Bem-vindo A", "19.90")})).json()
    b = (await client.post("/api/bots/flows", headers=headers, json={"name": "Funil B", "definition": _funnel("Bem-vindo B", "29.90")})).json()
    created = await client.post("/api/bots/folders", headers=headers, json={"name": "Teste A/B", "flow_ids": [a["id"], b["id"]]})
    assert created.status_code == 201, created.text
    folder_id = created.json()["id"]
    bot = (await client.post("/api/bots", headers=headers, json={"token": TOKEN})).json()
    connected = await client.patch(f"/api/bots/{bot['id']}", headers=headers, json={"folder_id": folder_id})
    assert connected.status_code == 200 and connected.json()["folder_id"] == folder_id and connected.json()["flow_id"] is None

    # the draw: lead 1 gets A, lead 2 gets B, lead 3 gets A
    picks = iter([0, 1, 0])
    monkeypatch.setattr(engine.secrets, "choice", lambda flows: sorted(flows, key=lambda f: f.name)[next(picks)])
    for lead_id in (101, 102, 103):
        await _send(client, db_session, bot["id"], _start_as(lead_id))
    texts = [m["text"] for m in apis.methods("sendMessage")]
    assert texts.count("Bem-vindo A") == 2 and texts.count("Bem-vindo B") == 1
    # a lead keeps its funnel on a new /start
    await _send(client, db_session, bot["id"], _start_as(102))
    assert [m["text"] for m in apis.methods("sendMessage")].count("Bem-vindo B") == 2
    await db_session.commit()
    leads = {lead.tg_user_id: lead.flow_id for lead in await db_session.scalars(select(TgLead))}
    assert leads == {101: uuid.UUID(a["id"]), 102: uuid.UUID(b["id"]), 103: uuid.UUID(a["id"])}

    # each lead buys from its own funnel; the order records that funnel
    await _send(client, db_session, bot["id"], _tap_as(102, "plan:vip"))
    await _send(client, db_session, bot["id"], _tap_as(101, "plan:pro"))
    await db_session.commit()
    orders = {o.lead_id: o for o in await db_session.scalars(select(TgOrder))}
    by_lead = {lead.tg_user_id: lead.id for lead in await db_session.scalars(select(TgLead))}
    assert orders[by_lead[102]].flow_id == uuid.UUID(b["id"]) and str(orders[by_lead[102]].amount) == "29.90"
    assert orders[by_lead[101]].flow_id == uuid.UUID(a["id"])
    apis.pix_amount = 29.90
    await _pay(client, orders[by_lead[102]])

    data = (await client.get("/api/bots/strategy?period=today")).json()
    rows = {row["name"]: row for row in data["flows"]}
    assert rows["Funil A"]["starts"] == 2 and rows["Funil A"]["pix"] == 1 and rows["Funil A"]["sales"] == 0
    assert rows["Funil B"]["starts"] == 1 and rows["Funil B"]["sales"] == 1 and rows["Funil B"]["conversion"] == 100.0
    assert rows["Funil B"]["gross"] == 29.9 and rows["Funil B"]["net"] == 28.9  # fake SmokePay fee R$ 1,00
    assert rows["Funil B"]["plans"] == [{"id": "vip", "name": "VIP", "sales": 1, "gross": 29.9}]
    folder = data["folders"][0]
    assert folder["starts"] == 3 and folder["sales"] == 1 and folder["leader"] == "Funil B" and folder["bots"] == ["ana_vip_bot"]
    assert data["leaders"]["net"]["name"] == "Funil B" and data["leaders"]["conversion"]["value"] == 100.0

    # removing a funnel from the folder re-draws only the leads that had it
    assert (await client.put(f"/api/bots/folders/{folder_id}", headers=headers, json={"name": "Teste A/B", "flow_ids": [b["id"]]})).status_code == 200
    monkeypatch.setattr(engine.secrets, "choice", lambda flows: flows[0])
    await _send(client, db_session, bot["id"], _start_as(101))
    await db_session.commit()
    lead = await db_session.scalar(select(TgLead).where(TgLead.tg_user_id == 101))
    await db_session.refresh(lead)
    assert lead.flow_id == uuid.UUID(b["id"])

    # deleting the folder disconnects the bot, leads keep their funnel
    assert (await client.delete(f"/api/bots/folders/{folder_id}", headers=headers)).status_code == 200
    stored = await db_session.get(TgBot, uuid.UUID(bot["id"]))
    await db_session.refresh(stored)
    assert stored.folder_id is None


@pytest.mark.anyio
async def test_folders_only_take_usable_funnels_and_stay_private(client, db_session, owner, apis) -> None:
    chief, chief_ws = owner
    partner, partner_ws, _ = await _partner(db_session, owner, accepted=True)
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    secret = (await client.post("/api/bots/flows", headers=headers, json={"name": "Não compartilhado", "definition": _flow()})).json()
    shared = (await client.post("/api/bots/flows", headers=headers, json={"name": "Compartilhado", "definition": _flow()})).json()
    rule = {"flow_id": shared["id"], "partner_id": str(partner.id), "gateway": "smokepay", "seller_percent": "80", "owner_percent": "20"}
    assert (await client.put("/api/partners/flow-shares", headers=headers, json=rule)).status_code == 200
    chief_folder = (await client.post("/api/bots/folders", headers=headers, json={"name": "Do chefe", "flow_ids": [secret["id"]]})).json()["id"]

    partner_headers = await _as(client, "socio@example.com")
    own = (await client.post("/api/bots/flows", headers=partner_headers, json={"name": "Meu", "definition": _flow()})).json()
    assert (await client.post("/api/bots/folders", headers=partner_headers, json={"name": "x", "flow_ids": [secret["id"]]})).status_code == 422
    ok = await client.post("/api/bots/folders", headers=partner_headers, json={"name": "Mix", "flow_ids": [own["id"], shared["id"]]})
    assert ok.status_code == 201, ok.text
    assert [f["shared"] for f in ok.json()["folders"][0]["flows"]] == [True, False]
    # another operation's folder is invisible and untouchable
    assert all(f["id"] != chief_folder for f in (await client.get("/api/bots/folders")).json()["folders"])
    assert (await client.put(f"/api/bots/folders/{chief_folder}", headers=partner_headers, json={"name": "x", "flow_ids": []})).status_code == 404
    assert (await client.delete(f"/api/bots/folders/{chief_folder}", headers=partner_headers)).status_code == 404
    bot = (await client.post("/api/bots", headers=partner_headers, json={"token": TOKEN})).json()
    assert (await client.patch(f"/api/bots/{bot['id']}", headers=partner_headers, json={"folder_id": chief_folder})).status_code == 404

    # a funnel that stops being shared is never drawn again
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    share_id = (await client.get("/api/partners/flow-shares")).json()["items"][0]["id"]
    assert (await client.delete(f"/api/partners/flow-shares/{share_id}", headers=headers)).status_code == 200
    stored = await db_session.get(TgBot, uuid.UUID(bot["id"]))
    stored.folder_id = uuid.UUID(ok.json()["id"])
    await db_session.commit()
    assert [f.name for f in await engine.folder_flows(db_session, stored)] == ["Meu"]


@pytest.mark.anyio
async def test_access_and_next_upsell_go_out_right_after_each_payment(client, db_session, owner, apis) -> None:
    """No worker run here: everything after a payment must already have been sent."""
    headers = await _login(client)
    definition = _flow(
        welcome=[],
        plans=[{"id": "vip", "name": "VIP", "price": "19.90", "delivery": {"type": "default", "text": "Acesso liberado"}}],
        upsells=[
            {"name": "Chamada", "price": "49.90", "delay_minutes": 30, "text": "Quer uma chamada?", "delivery": {"type": "default", "text": "Chamada ok"}},
            {"name": "Pack", "price": "9.90", "delay_minutes": 30, "text": "Quer o pack?", "delivery": {"type": "default", "text": "Pack ok"}},
        ],
    )
    flow = (await client.post("/api/bots/flows", headers=headers, json={"name": "Funil", "definition": definition})).json()
    bot = (await client.post("/api/bots", headers=headers, json={"token": TOKEN, "flow_id": flow["id"]})).json()
    await _send(client, db_session, bot["id"], _start_as(7))
    await _send(client, db_session, bot["id"], _tap_as(7, "plan:vip"))
    order = await db_session.scalar(select(TgOrder))
    await _pay(client, order)
    texts = [m["text"] for m in apis.methods("sendMessage")]
    assert texts[-2:] == ["Acesso liberado", "Quer uma chamada?"]  # despite the 30 min delay

    await _send(client, db_session, bot["id"], _tap_as(7, f"up:0:{order.id.hex}"))
    await db_session.commit()
    upsell = await db_session.scalar(select(TgOrder).where(TgOrder.kind == "upsell"))
    apis.pix_amount = 49.90
    await _pay(client, upsell)
    texts = [m["text"] for m in apis.methods("sendMessage")]
    assert texts[-2:] == ["Chamada ok", "Quer o pack?"]
