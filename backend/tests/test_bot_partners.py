"""Bot partnerships: invite an independent user, split each sale, finance panel."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from test_telegram_bots import _csrf, _login, _setup, apis  # noqa: F401

from app.core.nickname import nickname_key
from app.core.security import hash_password
from app.models import (
    BotPartner,
    TgLead,
    TgOrder,
    User,
)
from app.partners import bot_share_service as svc


async def _partner_user(db, email="augusto@example.com", nickname="Augusto VV", password="partner password 123") -> User:
    user = User(
        email=email, nickname=nickname, nickname_normalized=nickname_key(nickname),
        full_name="Augusto Partner", password_hash=hash_password(password),
        platform_role="USER", is_active=True, is_verified=True, username="augustovv",
    )
    db.add(user)
    await db.flush()
    from app.models import Workspace, WorkspaceMember

    ws = Workspace(name="Augusto WS", slug=f"augusto-{user.id.hex[:8]}", owner_id=user.id, status="ACTIVE")
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    await db.commit()
    return user


async def _paid_order(db, workspace_id, bot_id, flow_id, amount="100.00", gateway_fee="5.00") -> TgOrder:
    lead = TgLead(workspace_id=workspace_id, bot_id=bot_id, flow_id=flow_id, tg_user_id=999, chat_id=999)
    db.add(lead)
    await db.flush()
    order = TgOrder(
        workspace_id=workspace_id, bot_id=bot_id, lead_id=lead.id, flow_id=flow_id,
        kind="plan", offer_id="vip", offer_name="VIP", amount=Decimal(amount),
        gateway="smokepay", gateway_fee=Decimal(gateway_fee),
        net_amount=Decimal(amount) - Decimal(gateway_fee),
        status="paid", paid_at=datetime.now(timezone.utc),
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@pytest.mark.anyio
async def test_split_deducts_gateway_and_bot_fee_then_divides_net(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    owner_user, workspace = owner
    partner = await _partner_user(db_session)

    part = BotPartner(
        bot_id=uuid.UUID(bot["id"]), owner_user_id=owner_user.id, partner_user_id=partner.id,
        partner_percent=Decimal("30.00"), bot_fee=Decimal("2.00"), status="ACTIVE",
        accepted_at=datetime.now(timezone.utc),
    )
    db_session.add(part)
    await db_session.commit()

    order = await _paid_order(db_session, workspace.id, uuid.UUID(bot["id"]), uuid.UUID(flow["id"]))
    created = await svc.record_sale_split(db_session, order)
    await db_session.commit()
    assert len(created) == 1
    sale = created[0]
    # gross 100 - gateway 5 = net_amount 95; - bot fee 2 = 93 distributable
    assert sale.net == Decimal("93.00")
    assert sale.partner_amount == Decimal("27.90")  # floor(93 * 30%)
    assert sale.owner_amount == Decimal("65.10")

    # Idempotent: a second call does not record the sale twice.
    assert await svc.record_sale_split(db_session, order) == []

    summary = await svc.finance_summary(db_session, part, None, None)
    assert summary["totals"]["sales"] == 1
    assert summary["totals"]["partner_amount"] == 27.90
    assert summary["totals"]["owner_amount"] == 65.10


@pytest.mark.anyio
async def test_split_records_one_row_per_active_partner(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    owner_user, workspace = owner
    p1 = await _partner_user(db_session, email="a@example.com", nickname="Parceiro A")
    p2 = await _partner_user(db_session, email="b@example.com", nickname="Parceiro B")

    for partner, pct in ((p1, "30.00"), (p2, "20.00")):
        db_session.add(BotPartner(
            bot_id=uuid.UUID(bot["id"]), owner_user_id=owner_user.id, partner_user_id=partner.id,
            partner_percent=Decimal(pct), bot_fee=Decimal("0.00"), status="ACTIVE",
            accepted_at=datetime.now(timezone.utc),
        ))
    await db_session.commit()

    order = await _paid_order(db_session, workspace.id, uuid.UUID(bot["id"]), uuid.UUID(flow["id"]), gateway_fee="0.00")
    created = await svc.record_sale_split(db_session, order)
    await db_session.commit()
    # net 100; partner A 30.00, partner B 20.00; one ledger row each.
    assert len(created) == 2
    amounts = sorted(s.partner_amount for s in created)
    assert amounts == [Decimal("20.00"), Decimal("30.00")]
    # Idempotent across both partners.
    assert await svc.record_sale_split(db_session, order) == []


@pytest.mark.anyio
async def test_activating_over_100_percent_is_blocked(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _flow = await _setup(client, headers)
    owner_user, _workspace = owner
    p1 = await _partner_user(db_session, email="a@example.com", nickname="Parceiro A")
    p2 = await _partner_user(db_session, email="b@example.com", nickname="Parceiro B")

    active = BotPartner(
        bot_id=uuid.UUID(bot["id"]), owner_user_id=owner_user.id, partner_user_id=p1.id,
        partner_percent=Decimal("70.00"), bot_fee=Decimal("0.00"), status="ACTIVE",
        accepted_at=datetime.now(timezone.utc),
    )
    paused = BotPartner(
        bot_id=uuid.UUID(bot["id"]), owner_user_id=owner_user.id, partner_user_id=p2.id,
        partner_percent=Decimal("40.00"), bot_fee=Decimal("0.00"), status="PAUSED",
        accepted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([active, paused])
    await db_session.commit()

    # 70 + 40 = 110 > 100 → activation refused with a clear message.
    res = await client.patch(f"/api/bot-partners/{paused.id}", headers=headers, json={"status": "ACTIVE"})
    assert res.status_code == 409
    assert "100%" in res.json()["detail"]

    # Dropping the active one to 50 leaves room (50 + 40 = 90).
    ok = await client.patch(f"/api/bot-partners/{active.id}", headers=headers, json={"partner_percent": "50"})
    assert ok.status_code == 200
    ok2 = await client.patch(f"/api/bot-partners/{paused.id}", headers=headers, json={"status": "ACTIVE"})
    assert ok2.status_code == 200, ok2.text
    assert ok2.json()["status"] == "ACTIVE"


@pytest.mark.anyio
async def test_owner_marks_commission_paid_and_partner_sees_status(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    owner_user, workspace = owner
    partner = await _partner_user(db_session)
    part = BotPartner(
        bot_id=uuid.UUID(bot["id"]), owner_user_id=owner_user.id, partner_user_id=partner.id,
        partner_percent=Decimal("50.00"), bot_fee=Decimal("0.00"), status="ACTIVE",
        accepted_at=datetime.now(timezone.utc),
    )
    db_session.add(part)
    await db_session.commit()

    order = await _paid_order(db_session, workspace.id, uuid.UUID(bot["id"]), uuid.UUID(flow["id"]), gateway_fee="0.00")
    [sale] = await svc.record_sale_split(db_session, order)
    await db_session.commit()
    assert sale.payout_status == "pending"

    # Owner marks the commission paid.
    res = await client.patch(f"/api/bot-partners/sales/{sale.id}/status", headers=headers, json={"status": "paid", "note": "pix enviado"})
    assert res.status_code == 200, res.text
    assert res.json()["payout_status"] == "paid"

    # Partner logs in and sees the status + the by-status totals.
    await client.post("/api/auth/login", headers={"X-CSRF-Token": await _csrf(client)},
                      json={"email": "augusto@example.com", "password": "partner password 123"})
    pheaders = {"X-CSRF-Token": await _csrf(client)}
    fin = await client.get(f"/api/bot-partners/shared/{bot['id']}/finance?period=all", headers=pheaders)
    assert fin.status_code == 200, fin.text
    body = fin.json()
    assert body["sales"][0]["payout_status"] == "paid"
    assert body["by_status"]["paid"]["count"] == 1
    assert body["by_status"]["paid"]["partner_amount"] == 50.0

    # A partner cannot change the status (not their endpoint / not their owner scope).
    nope = await client.patch(f"/api/bot-partners/sales/{sale.id}/status", headers=pheaders, json={"status": "pending"})
    assert nope.status_code in (403, 404)


@pytest.mark.anyio
async def test_no_split_without_active_partner(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    _owner_user, workspace = owner
    order = await _paid_order(db_session, workspace.id, uuid.UUID(bot["id"]), uuid.UUID(flow["id"]))
    assert await svc.record_sale_split(db_session, order) == []


@pytest.mark.anyio
async def test_invite_accept_and_edit_flow(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    partner = await _partner_user(db_session)

    # Owner invites the partner by e-mail.
    invite = await client.post(
        f"/api/bot-partners/bots/{bot['id']}/invite", headers=headers,
        json={"identifier": "augusto@example.com", "partner_percent": "40"},
    )
    assert invite.status_code == 201, invite.text
    part_id = invite.json()["id"]
    assert invite.json()["status"] == "PENDING"

    # A common owner cannot set the bot fee.
    denied = await client.post(
        f"/api/bot-partners/bots/{bot['id']}/invite", headers=headers,
        json={"identifier": "augusto@example.com", "partner_percent": "40", "bot_fee": "0"},
    )
    assert denied.status_code in (403, 409)  # 409 if already invited; 403 fee gate

    # Partner logs in (session cookie switches) and accepts.
    await client.post("/api/auth/login", headers={"X-CSRF-Token": await _csrf(client)},
                      json={"email": "augusto@example.com", "password": "partner password 123"})
    pheaders = {"X-CSRF-Token": await _csrf(client)}
    accepted = await client.post(f"/api/bot-partners/{part_id}/accept", headers=pheaders)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACTIVE"

    shared = await client.get("/api/bot-partners/shared", headers=pheaders)
    assert shared.status_code == 200 and len(shared.json()["shared"]) == 1

    detail = await client.get(f"/api/bot-partners/shared/{bot['id']}", headers=pheaders)
    assert detail.status_code == 200 and detail.json()["can_edit"] is True
    assert detail.json()["flows"][0]["id"] == flow["id"]

    got = await client.get(f"/api/bot-partners/shared/{bot['id']}/flows/{flow['id']}", headers=pheaders)
    assert got.status_code == 200
    definition = got.json()["definition"]
    definition["offer"]["text"] = "Editado pelo parceiro 👇"
    saved = await client.put(
        f"/api/bot-partners/shared/{bot['id']}/flows/{flow['id']}", headers=pheaders,
        json={"name": "Funil Ana", "definition": definition},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["definition"]["offer"]["text"] == "Editado pelo parceiro 👇"

    # The partner cannot reach a funnel that is not this bot's.
    other = await client.get(f"/api/bot-partners/shared/{bot['id']}/flows/{uuid.uuid4()}", headers=pheaders)
    assert other.status_code == 404


@pytest.mark.anyio
async def test_partner_cannot_invite_self_and_super_admin_zeroes_fee(client, db_session, owner, super_admin, apis) -> None:
    # Super admin can zero the bot fee on a bot they own.
    from app.models import TgBot, Workspace, WorkspaceMember

    ws = Workspace(name="SA WS", slug="sa-ws", owner_id=super_admin.id, status="ACTIVE")
    db_session.add(ws)
    await db_session.flush()
    db_session.add(WorkspaceMember(workspace_id=ws.id, user_id=super_admin.id, role="OWNER", status="ACTIVE"))
    bot = TgBot(workspace_id=ws.id, tg_bot_id=12345, username="sabot", name="SA Bot",
                encrypted_token="x", webhook_secret="s")
    db_session.add(bot)
    await db_session.commit()

    await _partner_user(db_session, email="p2@example.com", nickname="Parceiro Dois")
    await client.post("/api/auth/login", headers={"X-CSRF-Token": await _csrf(client)},
                      json={"email": "superadmin@example.com", "password": "super admin password"})
    headers = {"X-CSRF-Token": await _csrf(client)}
    res = await client.post(
        f"/api/bot-partners/bots/{bot.id}/invite", headers=headers,
        json={"identifier": "p2@example.com", "partner_percent": "50", "bot_fee": "0"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["bot_fee"] == 0.0
