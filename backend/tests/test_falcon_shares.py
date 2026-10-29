"""Falcon Bot: per-partner share rules (percentages and SnakePay ShopIDs set by the funnel's
owner), gateway priority with backups, safe failover and permission isolation."""

import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.bots import gateways, http
from app.models import AuditEvent, TgFlow, TgFlowShare, TgOrder, Workspace
from app.partners import service
from tests.test_partners import CHIEF_PASSWORD, _as, _partner
from tests.test_snakepay import CHIEF, SELLER, _enable, _event, snake  # noqa: F401
from tests.test_telegram_bots import TOKEN, _flow, _paid_event, _send, _setup, _signed, _start, _tap, apis  # noqa: F401

PLATFORM = "99999999-8888-7777-6666-555555555555"


async def _chief(client) -> dict:
    return await _as(client, "owner@example.com", CHIEF_PASSWORD)


async def _new_flow(client, headers, name: str) -> str:
    response = await client.post("/api/bots/flows", headers=headers, json={"name": name, "definition": _flow()})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _share(flow_id: str, partner_id, **extra) -> dict:
    body = {"flow_id": flow_id, "partner_id": str(partner_id), "gateway": "smokepay", "seller_percent": "80", "owner_percent": "20"}
    body.update(extra)
    return body


def _wrap(transport_change):
    """Swap the fake gateways' transport for one that changes some answers."""
    inner = http._transport.handler
    http.set_transport(httpx.MockTransport(lambda request: transport_change(request, inner)))


@pytest.mark.anyio
async def test_owner_shares_a_funnel_with_rules_and_shop_ids_and_the_seller_cannot_change_them(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    db_session.add(Workspace(name="plataforma", slug="plataforma-ws", owner_id=super_admin.id, status="ACTIVE",
                             snakepay_recipient_id=PLATFORM))  # the platform's own account
    await db_session.commit()
    headers = await _chief(client)
    flow_id = await _new_flow(client, headers, "Funil Chefe")

    # validation: totals, ranges, own partner, own funnel
    bad_total = await client.put("/api/partners/flow-shares", headers=headers, json=_share(flow_id, partner.id, seller_percent="70"))
    assert bad_total.status_code == 422 and "100%" in bad_total.text
    over = await client.put("/api/partners/flow-shares", headers=headers, json=_share(flow_id, partner.id, seller_percent="0", owner_percent="100"))
    assert over.status_code == 422
    negative = await client.put("/api/partners/flow-shares", headers=headers, json=_share(flow_id, partner.id, seller_percent="110", owner_percent="-10"))
    assert negative.status_code == 422
    stranger = await client.put("/api/partners/flow-shares", headers=headers, json=_share(flow_id, uuid.uuid4()))
    assert stranger.status_code == 422

    created = await client.put("/api/partners/flow-shares", headers=headers, json=_share(flow_id, partner.id))
    assert created.status_code == 200, created.text
    share = created.json()
    assert share["seller_percent"] == 80.0 and share["owner_percent"] == 20.0 and share["gateway"] == "smokepay"

    # SnakePay: the seller charges in their own account, so only the owner's ShopID is needed
    # (to receive the commission). No seller ShopID is asked for.
    await _enable(client)
    headers = await _chief(client)
    snake_rules = _share(flow_id, partner.id, gateway="snakepay")
    assert (await client.put("/api/partners/flow-shares", headers=headers, json=snake_rules)).status_code == 422  # owner ShopID missing
    for owner_id in ("meu-email", PLATFORM):
        bad = await client.put("/api/partners/flow-shares", headers=headers, json={**snake_rules, "owner_shop_id": owner_id})
        assert bad.status_code == 422, (owner_id, bad.text)
    saved = await client.put("/api/partners/flow-shares", headers=headers, json={**snake_rules, "owner_shop_id": CHIEF})
    assert saved.status_code == 200, saved.text
    assert saved.json()["id"] == share["id"]  # same share, new rules
    assert saved.json()["owner_shop_id"] == "••••eeee" and CHIEF not in saved.text  # never the whole ShopID back
    listing = (await client.get("/api/partners/flow-shares")).json()
    assert [item["rule"] for item in listing["items"]] == ["share"] and "líquido" in listing["basis"]
    # editing without retyping the ShopID keeps it
    kept = await client.put("/api/partners/flow-shares", headers=headers, json={**snake_rules, "seller_percent": "75", "owner_percent": "25"})
    assert kept.status_code == 200 and kept.json()["owner_percent"] == 25.0
    rule = await db_session.get(TgFlowShare, uuid.UUID(share["id"]))
    await db_session.refresh(rule)
    assert rule.owner_shop_id == CHIEF

    # the seller sees only the gateway and that they must set up SnakePay — never the split or any ShopID
    partner_headers = await _as(client, "socio@example.com")
    shared = (await client.get("/api/partners/shared")).json()
    rules = shared["flows"][0]["rules"]
    assert rules == {"set_by_owner": True, "gateway": "snakepay", "needs_setup": True}
    assert CHIEF not in str(shared) and "percent" not in str(rules) and "shop_id" not in str(rules)
    attempts = [
        await client.put("/api/partners/flow-shares", headers=partner_headers, json=_share(flow_id, partner.id, seller_percent="100", owner_percent="0")),
        await client.delete(f"/api/partners/flow-shares/{share['id']}", headers=partner_headers),
        await client.get(f"/api/partners/flow-shares/{share['id']}/history"),
        await client.put(f"/api/payment-gateways/flows/{flow_id}", headers=partner_headers, json={"gateway": "smokepay"}),
    ]
    assert [r.status_code for r in attempts] in ([422, 404, 404, 404], [404, 404, 404, 404]), [r.text for r in attempts]
    await db_session.refresh(rule)
    assert rule.seller_percent == Decimal("75.00") and rule.status == "ACTIVE"
    assert (await client.get("/api/partners/flow-shares")).json()["items"] == []  # the seller shared nothing

    # every change is in the owner's audit trail, without a whole ShopID
    headers = await _chief(client)
    history = (await client.get(f"/api/partners/flow-shares/{share['id']}/history")).json()["items"]
    assert sorted(item["action"] for item in history) == ["share.created", "share.updated", "share.updated"]
    assert SELLER not in str(history) and CHIEF not in str(history)

    # revoking stops the seller's sales at once and keeps the record
    revoked = await client.delete(f"/api/partners/flow-shares/{share['id']}", headers=headers)
    assert revoked.status_code == 200 and revoked.json()["status"] == "REVOKED"
    route = await service.billing_route(db_session, partner_ws.id, uuid.UUID(flow_id))
    assert route.allowed is False
    await _as(client, "socio@example.com")
    assert (await client.get("/api/partners/shared")).json()["flows"] == []
    actions = list(await db_session.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == rule.id)))
    assert "share.revoked" in actions


@pytest.mark.anyio
async def test_a_snakepay_shared_funnel_is_locked_until_the_seller_sets_up_their_own_snakepay(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)  # partnership default: 30%
    await _enable(client)
    headers = await _chief(client)
    flow_id = await _new_flow(client, headers, "Funil Chefe")
    saved = await client.put("/api/partners/flow-shares", headers=headers, json=_share(
        flow_id, partner.id, gateway="snakepay", seller_percent="80", owner_percent="20", owner_shop_id=CHIEF,
    ))
    assert saved.status_code == 200, saved.text

    # the seller has no SnakePay of their own: the funnel is locked and tells them to set it up
    partner_headers = await _as(client, "socio@example.com")
    shared = (await client.get("/api/partners/shared")).json()
    assert shared["flows"][0]["rules"] == {"set_by_owner": True, "gateway": "snakepay", "needs_setup": True}
    assert (await client.post(f"/api/partners/shared/flows/{flow_id}/use", headers=partner_headers)).status_code == 409
    blocked = await client.post("/api/bots", headers=partner_headers, json={"token": TOKEN, "flow_id": flow_id})
    assert blocked.status_code == 409 and "SnakePay" in blocked.text

    # the seller saves their own SnakePay key: the funnel unlocks
    assert (await client.put("/api/payment-gateways/snakepay/credentials", headers=partner_headers,
                             json={"api_key": "seller_sk_test", "webhook_secret": "seller_webhook_test"})).status_code == 200
    shared = (await client.get("/api/partners/shared")).json()
    assert shared["flows"][0]["rules"] == {"set_by_owner": True, "gateway": "snakepay", "needs_setup": False}
    bot = (await client.post("/api/bots", headers=partner_headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))

    # the charge is created in the seller's account; only the owner's 20% commission goes out by split
    assert not apis.methods("pix.create")
    created = apis.methods("snake.create")[-1]
    assert created["split"] == [{"recipient_id": CHIEF, "percentage": 20.0}]
    assert [call[1]["authorization"] for call in apis.calls if call[0] == "snake.auth"] == ["Bearer seller_sk_test"]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.share_id == uuid.UUID(saved.json()["id"]) and order.origin == "shared_funnel"
    assert order.split_percent == Decimal("20.00") and order.split_amount == Decimal("3.81")
    assert order.partner_net == Decimal("15.24")

    raw, sig = _event(snake["charges"]["in_1"], "seller_webhook_test")
    assert (await client.post("/api/bots/pay/snakepay", content=raw, headers=sig)).status_code == 200
    me = (await client.get("/api/partners/me?period=today")).json()
    assert me["totals"]["sales"] == 1 and me["totals"]["net"] == 15.24 and me["totals"]["commission"] == 3.81
    await _chief(client)
    ops = (await client.get(f"/api/partners/{link.id}/operations?period=today")).json()
    assert ops["commission"]["commission"] == 3.81 and ops["commission"]["sales"] == 1
    listing = (await client.get("/api/partners/flow-shares")).json()["items"]
    assert listing[0]["stats"] == {"sales": 1, "gross": 19.9, "commission": 3.81}
    # the owner is not asked for the seller's ShopID anywhere else
    assert (await client.get("/api/payment-gateways")).json()["partners_without_shop_id"] == []


@pytest.mark.anyio
async def test_legacy_share_keeps_the_partnership_percentage(client, db_session, owner, apis) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    headers = await _chief(client)
    flow_id = await _new_flow(client, headers, "Funil Antigo")
    assert (await client.post(f"/api/partners/flows/{flow_id}/share", headers=headers, json={"shared": True})).status_code == 200
    route = await service.billing_route(db_session, partner_ws.id, uuid.UUID(flow_id))
    assert route.allowed and route.percent == Decimal("30.00") and route.share_id is None
    items = (await client.get("/api/partners/flow-shares")).json()["items"]
    assert [(i["rule"], i["owner_percent"], i["seller_percent"]) for i in items] == [("partnership", 30.0, 70.0)]


@pytest.mark.anyio
async def test_priority_principal_backups_and_funnel_association(client, db_session, owner, super_admin, snake, apis) -> None:
    chief, chief_ws = owner
    chief.platform_role = "SUPER_ADMIN"  # only the Super Admin chooses/orders gateways
    await db_session.commit()
    await _enable(client)
    headers = await _chief(client)
    first = await _new_flow(client, headers, "Funil A")
    second = await _new_flow(client, headers, "Funil B")
    state = (await client.get("/api/payment-gateways")).json()
    # nothing saved yet: what already happens (SmokePay only)
    assert [(p["gateway"], p["enabled"]) for p in state["priority"]] == [("smokepay", True), ("snakepay", False), ("atenaspay", False)]

    # The Super Admin's SnakePay is set up via the server env, so it can be enabled right away.
    assert (await client.put("/api/payment-gateways", headers=headers, json={"gateway": "smokepay", "snakepay_recipient_id": CHIEF})).status_code == 200

    invalid = [
        [{"gateway": "snakepay", "enabled": True}, {"gateway": "snakepay", "enabled": False}],
        [{"gateway": "snakepay", "enabled": True, "flow_ids": [first]}, {"gateway": "smokepay", "enabled": False}],
        [{"gateway": "snakepay", "enabled": True, "flow_ids": [str(uuid.uuid4())]}, {"gateway": "smokepay", "enabled": True}],
        [{"gateway": "snakepay", "enabled": True, "flow_ids": []}, {"gateway": "smokepay", "enabled": True}],
    ]
    for items in invalid:
        assert (await client.put("/api/payment-gateways/priority", headers=headers, json={"items": items})).status_code == 422, items

    # SnakePay principal only for funnel A; SmokePay for everything and backup of A
    saved = await client.put("/api/payment-gateways/priority", headers=headers, json={"items": [
        {"gateway": "snakepay", "enabled": True, "flow_ids": [first]}, {"gateway": "smokepay", "enabled": True},
    ]})
    assert saved.status_code == 200, saved.text
    assert [(p["gateway"], p["priority"], p["status"]) for p in saved.json()["priority"]] == [("snakepay", 1, "ativo"), ("smokepay", 2, "ativo"), ("atenaspay", 3, "indisponivel")]
    await db_session.commit()
    workspace = await db_session.get(Workspace, chief_ws.id)
    await db_session.refresh(workspace)
    flow_a = await db_session.get(TgFlow, uuid.UUID(first))
    flow_b = await db_session.get(TgFlow, uuid.UUID(second))
    assert await gateways.gateway_order(db_session, workspace, flow_a) == ["snakepay", "smokepay"]
    assert await gateways.gateway_order(db_session, workspace, flow_b) == ["smokepay"]  # A's gateway does not reach B
    assert workspace.payment_gateway == "smokepay"

    # a funnel's own choice beats the operation's order
    assert (await client.put(f"/api/payment-gateways/flows/{second}", headers=headers, json={"gateway": "snakepay"})).status_code == 200
    await db_session.refresh(flow_b)
    assert await gateways.gateway_order(db_session, workspace, flow_b) == ["snakepay", "smokepay"]
    # a gateway turned off is never used, not even by a funnel that picked it
    assert (await client.put("/api/payment-gateways/priority", headers=headers, json={"items": [
        {"gateway": "smokepay", "enabled": True}, {"gateway": "snakepay", "enabled": False},
    ]})).status_code == 200
    assert await gateways.gateway_order(db_session, workspace, flow_b) == ["smokepay"]
    actions = list(await db_session.scalars(select(AuditEvent.action).where(AuditEvent.workspace_id == chief_ws.id)))
    assert actions.count("gateways.priority") == 2


@pytest.mark.anyio
async def test_backup_after_a_timeout_never_lets_a_sale_be_paid_twice(client, db_session, owner, super_admin, snake, apis) -> None:
    chief, chief_ws = owner
    await _enable(client)
    headers = await _chief(client)
    assert (await client.put("/api/payment-gateways", headers=headers, json={"gateway": "snakepay", "snakepay_recipient_id": CHIEF})).status_code == 200
    saved = await client.put("/api/payment-gateways/priority", headers=headers, json={"items": [
        {"gateway": "snakepay", "enabled": True}, {"gateway": "smokepay", "enabled": True},
    ]})
    assert saved.status_code == 200, saved.text

    def lost_answer(request, inner):
        if request.method == "POST" and str(request.url).endswith("/charges"):
            inner(request)  # SnakePay creates the charge, but its answer never arrives
            raise httpx.ReadTimeout("timed out", request=request)
        return inner(request)

    _wrap(lost_answer)
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    # the backup charged; the lead got one Pix only, SmokePay's
    assert order.gateway == "smokepay" and order.gateway_attempts == ["snakepay"] and order.status == "pending"
    assert len(apis.methods("pix.create")) == 1
    pix_codes = [b for m, b in apis.calls if m in ("sendPhoto", "sendMessage") and "00020126" in str(b)]
    assert len(pix_codes) == 1 and "SNAKEPIX" not in str(pix_codes)

    # the lost SnakePay charge cannot pay this order, even if someone paid it
    raw, sig = _event(snake["charges"]["in_1"])
    assert (await client.post("/api/bots/pay/snakepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "pending"
    # tapping the offer again reuses the pending Pix instead of charging again
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert len(apis.methods("pix.create")) == 1 and len(apis.methods("snake.create")) == 1
    # the SmokePay notice pays once; a repeated notice delivers nothing more
    for _ in range(2):
        raw, sig = _signed(_paid_event(order.id))
        assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "paid"
    assert len(apis.methods("createChatInviteLink")) == 1


@pytest.mark.anyio
async def test_smokepay_refusal_falls_back_to_snakepay_and_its_notice_is_ignored(client, db_session, owner, super_admin, snake, apis) -> None:
    chief, chief_ws = owner
    chief.platform_role = "SUPER_ADMIN"  # chooses SmokePay principal with SnakePay backup
    await db_session.commit()
    await _enable(client)
    headers = await _chief(client)
    assert (await client.put("/api/payment-gateways", headers=headers, json={"gateway": "smokepay", "snakepay_recipient_id": CHIEF})).status_code == 200
    assert (await client.put("/api/payment-gateways/priority", headers=headers, json={"items": [
        {"gateway": "smokepay", "enabled": True}, {"gateway": "snakepay", "enabled": True},
    ]})).status_code == 200

    def smoke_refuses(request, inner):
        if "/api/pix/create" in str(request.url):
            return httpx.Response(422, json={"error": "conta em análise"})
        return inner(request)

    _wrap(smoke_refuses)
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.gateway == "snakepay" and order.gateway_attempts == ["smokepay"]
    raw, sig = _signed(_paid_event(order.id))
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "pending"  # only SnakePay's own notice pays a SnakePay order

    # with every gateway failing the lead is told and nothing is charged twice
    _wrap(lambda request, inner: httpx.Response(422, json={"error": "não"}) if "snake.test" in str(request.url) else inner(request))
    order.status = "expired"
    await db_session.commit()
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await db_session.commit()
    failed = await db_session.scalar(select(TgOrder).where(TgOrder.id != order.id))
    assert failed.status == "failed" and failed.gateway_attempts == ["smokepay", "snakepay"]


@pytest.mark.anyio
async def test_other_users_rules_and_gateways_stay_isolated(client, db_session, owner, apis) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    headers = await _chief(client)
    flow_id = await _new_flow(client, headers, "Funil Chefe")
    share = (await client.put("/api/partners/flow-shares", headers=headers, json=_share(flow_id, partner.id))).json()

    partner_headers = await _as(client, "socio@example.com")
    own_flow = await _new_flow(client, partner_headers, "Funil do sócio")
    # the seller cannot associate the chief's funnel to their gateways, nor share it
    bad = await client.put("/api/payment-gateways/priority", headers=partner_headers, json={"items": [
        {"gateway": "smokepay", "enabled": True, "flow_ids": [flow_id]}, {"gateway": "snakepay", "enabled": False},
    ]})
    assert bad.status_code == 422
    assert (await client.put("/api/partners/flow-shares", headers=partner_headers, json=_share(flow_id, chief.id))).status_code in (404, 422)
    # the chief cannot touch the partner's funnel either
    headers = await _chief(client)
    assert (await client.put("/api/partners/flow-shares", headers=headers, json=_share(own_flow, partner.id))).status_code == 404
    assert (await client.put(f"/api/payment-gateways/flows/{own_flow}", headers=headers, json={"gateway": None})).status_code == 404
    assert share["id"] in str((await client.get("/api/partners/flow-shares")).json())


@pytest.mark.anyio
async def test_seller_with_own_snakepay_key_is_charged_in_their_account_and_splits_the_owners_commission(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    await _enable(client)
    headers = await _chief(client)
    flow_id = await _new_flow(client, headers, "Funil Chefe")
    saved = await client.put("/api/partners/flow-shares", headers=headers, json=_share(
        flow_id, partner.id, gateway="snakepay", seller_percent="80", owner_percent="20", seller_shop_id=SELLER, owner_shop_id=CHIEF,
    ))
    assert saved.status_code == 200, saved.text

    # the seller saves their own SnakePay key: the sale is charged in the seller's account
    partner_headers = await _as(client, "socio@example.com")
    assert (await client.put("/api/payment-gateways/snakepay/credentials", headers=partner_headers,
                             json={"api_key": "seller_sk_test", "webhook_secret": "seller_webhook_test"})).status_code == 200
    bot = (await client.post("/api/bots", headers=partner_headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    created = apis.methods("snake.create")[-1]
    assert created["split"] == [{"recipient_id": CHIEF, "percentage": 20.0}]  # only the owner's commission goes out
    auths = [call[1]["authorization"] for call in apis.calls if call[0] == "snake.auth"]
    assert auths == ["Bearer seller_sk_test"]  # never the platform's key
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.share_id == uuid.UUID(saved.json()["id"]) and order.split_amount == Decimal("3.81")
    assert order.partner_net == Decimal("15.24")

    # the payment is confirmed with the seller's webhook secret
    raw, sig = _event(snake["charges"]["in_1"], "seller_webhook_test")
    assert (await client.post("/api/bots/pay/snakepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "paid"


@pytest.mark.anyio
async def test_super_admin_owner_gets_the_commission_in_the_platform_account_from_the_sellers_charge(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    await _enable(client)
    headers = await _chief(client)
    flow_id = await _new_flow(client, headers, "Funil Chefe")
    assert (await client.put("/api/partners/flow-shares", headers=headers, json=_share(
        flow_id, partner.id, gateway="snakepay", seller_percent="80", owner_percent="20", seller_shop_id=SELLER, owner_shop_id=CHIEF,
    ))).status_code == 200
    chief.platform_role = "SUPER_ADMIN"  # like the real owner: the platform account
    chief_ws.snakepay_recipient_id = PLATFORM
    await db_session.commit()

    partner_headers = await _as(client, "socio@example.com")
    assert (await client.put("/api/payment-gateways/snakepay/credentials", headers=partner_headers,
                             json={"api_key": "seller_sk_test", "webhook_secret": "seller_webhook_test"})).status_code == 200
    bot = (await client.post("/api/bots", headers=partner_headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    created = apis.methods("snake.create")[-1]
    auths = [call[1]["authorization"] for call in apis.calls if call[0] == "snake.auth"]
    assert auths == ["Bearer seller_sk_test"]
    assert [item["recipient_id"] for item in created["split"]] == [PLATFORM]
    assert created["split"][0]["percentage"] == 20.0


async def _partner_sees_nothing(client, db_session, partner) -> None:
    """The seller's panel, bots, revenue, wallet and notices know nothing of the owner's 100% sales."""
    from app.models import AppNotification

    await _as(client, "socio@example.com")
    stats = (await client.get("/api/bots/stats?period=today")).json()["totals"]
    assert stats["leads"] == 0 and stats["sales"] == 0 and stats["pix_generated"] == 0 and stats["revenue"] == 0
    assert [(b["leads"], b["sales"]) for b in (await client.get("/api/bots")).json()["bots"]] == [(0, 0)]
    assert (await client.get("/api/bots/orders/list")).json()["orders"] == []
    assert (await client.get("/api/bots/activity")).json()["items"] == []
    assert (await client.get("/api/finance/month")).json()["today"]["flashbot_gross"] == "0.00"
    me = (await client.get("/api/partners/me?period=today")).json()["totals"]
    assert me["sales"] == 0 and me["gross"] == 0 and me["net"] == 0
    from app.wallet.router import balances, month_revenue_by_bot, snakepay_breakdown

    await db_session.commit()
    workspace = await service.owner_workspace(db_session, partner.id)
    money = await balances(db_session, partner, workspace.id)
    assert money["earned"] == 0 and money["available"] == 0 and money["commission_paid"] == 0
    assert (await month_revenue_by_bot(db_session, workspace.id))[2] == 0
    assert sum((await snakepay_breakdown(db_session, partner, workspace.id)).values()) == 0
    assert not list(await db_session.scalars(select(AppNotification).where(AppNotification.user_id == partner.id)))


@pytest.mark.anyio
async def test_owner_takes_all_charges_the_whole_sale_in_the_owners_account_and_the_seller_never_knows(
    client, db_session, owner, apis
) -> None:
    from app.models import AppNotification, TgLead

    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    headers = await _chief(client)
    flow_id = await _new_flow(client, headers, "Funil Chefe")
    saved = await client.put("/api/partners/flow-shares", headers=headers, json=_share(flow_id, partner.id, owner_takes_all=True))
    assert saved.status_code == 200, saved.text
    assert saved.json()["owner_takes_all"] is True

    partner_headers = await _as(client, "socio@example.com")
    bot = (await client.post("/api/bots", headers=partner_headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    created = apis.methods("pix.create")[-1]
    assert created["shop_id"] == f"fp-{chief_ws.id.hex}" and not created.get("splits")  # all in the owner's subaccount
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.origin == "owner_all" and order.seller_hidden is True and order.split_chief_user_id == chief.id
    assert order.partner_net == Decimal("0.00") and order.split_amount == Decimal("18.90")  # 19.90 - 1.00 fee
    assert (await db_session.scalar(select(TgLead))).seller_hidden is True
    raw, sig = _signed(_paid_event(order.id))
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200

    await _partner_sees_nothing(client, db_session, partner)
    # the owner gets the notice and the money as theirs
    notices = list(await db_session.scalars(select(AppNotification).where(AppNotification.user_id == chief.id)))
    assert [n.kind for n in notices] == ["sale"]
    from app.wallet.router import month_commissions

    assert await month_commissions(db_session, chief_ws.id) == Decimal("18.90")
    # the Falcon fee of the owner's 100% sales is the owner's (never the seller's)
    chief.transaction_fee, partner.transaction_fee = Decimal("0.40"), Decimal("0.99")
    await db_session.commit()
    route = await service.billing_route(db_session, partner_ws.id, uuid.UUID(flow_id))
    assert route.owner_all and route.shop_ref == f"fp-{chief_ws.id.hex}" and route.splits == [{"parent": True, "amount": 0.4}]

    # turned off: the seller's next sales follow the saved percentages again
    headers = await _chief(client)
    off = await client.put("/api/partners/flow-shares", headers=headers, json=_share(flow_id, partner.id))
    assert off.status_code == 200 and off.json()["owner_takes_all"] is False
    route = await service.billing_route(db_session, partner_ws.id, uuid.UUID(flow_id))
    assert route.owner_all is False and route.percent == Decimal("20.00")


@pytest.mark.anyio
async def test_owner_takes_all_with_snakepay_goes_to_the_owners_shop_id_or_the_platform_account(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    await _enable(client)
    headers = await _chief(client)
    flow_id = await _new_flow(client, headers, "Funil Chefe")
    # no seller ShopID needed; the owner's own is
    rules = _share(flow_id, partner.id, gateway="snakepay", owner_takes_all=True)
    assert (await client.put("/api/partners/flow-shares", headers=headers, json=rules)).status_code == 422
    saved = await client.put("/api/partners/flow-shares", headers=headers, json={**rules, "owner_shop_id": CHIEF})
    assert saved.status_code == 200, saved.text

    partner_headers = await _as(client, "socio@example.com")
    bot = (await client.post("/api/bots", headers=partner_headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert not apis.methods("pix.create")
    assert apis.methods("snake.create")[-1]["split"] == [{"recipient_id": CHIEF, "percentage": 100.0}]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.seller_hidden is True and order.partner_net == Decimal("0.00") and order.split_amount == Decimal("19.05")
    raw, sig = _event(snake["charges"]["in_1"])
    assert (await client.post("/api/bots/pay/snakepay", content=raw, headers=sig)).status_code == 200
    await _partner_sees_nothing(client, db_session, partner)

    # the Super Admin owner: the whole sale stays in the platform account, no split at all
    chief.platform_role = "SUPER_ADMIN"
    await db_session.commit()
    other = _start()
    other["message"]["from"]["id"] = other["message"]["chat"]["id"] = 777
    await _send(client, db_session, bot["id"], other)
    tap = _tap("plan:vip")
    tap["callback_query"]["from"]["id"] = tap["callback_query"]["message"]["chat"]["id"] = 777
    await _send(client, db_session, bot["id"], tap)
    assert not apis.methods("snake.create")[-1].get("split")
    await db_session.commit()
    second = await db_session.scalar(select(TgOrder).where(TgOrder.id != order.id))
    assert second.seller_hidden is True and second.split_amount == Decimal("19.05") and second.partner_net == Decimal("0.00")
    assert not second.transaction_fee
    await _partner_sees_nothing(client, db_session, partner)


@pytest.mark.anyio
async def test_owner_takes_all_with_the_owners_own_snakepay_key_is_charged_in_the_owners_account(
    client, db_session, owner, super_admin, snake, apis
) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    await _enable(client)
    headers = await _chief(client)
    assert (await client.put("/api/payment-gateways/snakepay/credentials", headers=headers,
                             json={"api_key": "owner_sk_test", "webhook_secret": "owner_webhook_test"})).status_code == 200
    flow_id = await _new_flow(client, headers, "Funil Chefe")
    saved = await client.put("/api/partners/flow-shares", headers=headers, json=_share(
        flow_id, partner.id, gateway="snakepay", owner_takes_all=True,
    ))
    assert saved.status_code == 200, saved.text  # no ShopID needed: the owner's own key charges

    partner_headers = await _as(client, "socio@example.com")
    bot = (await client.post("/api/bots", headers=partner_headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert not apis.methods("snake.create")[-1].get("split")
    assert [call[1]["authorization"] for call in apis.calls if call[0] == "snake.auth"] == ["Bearer owner_sk_test"]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.split_amount == Decimal("19.05") and order.partner_net == Decimal("0.00") and order.seller_hidden
    raw, sig = _event(snake["charges"]["in_1"], "owner_webhook_test")
    assert (await client.post("/api/bots/pay/snakepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "paid"
    await _partner_sees_nothing(client, db_session, partner)
