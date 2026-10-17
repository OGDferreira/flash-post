"""Partners: commission acceptance, SmokePay split, shared templates, isolation."""

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import (
    Affiliation,
    AppNotification,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopMedia,
    InstagramMedia,
    TgFlow,
    TgMedia,
    TgOrder,
    User,
)
from app.core.time import utc_now
from app.partners import service
from tests.test_affiliates import PASSWORD, _make_owner
from tests.test_loops import _csrf, _login
from tests.test_telegram_bots import TOKEN, _flow, _paid_event, _send, _setup, _signed, _start, _tap, apis  # noqa: F401

CHIEF_PASSWORD = "correct horse battery staple"


async def _as(client, email: str, password: str = PASSWORD) -> dict:
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    await _login(client, email, password)
    return {"X-CSRF-Token": await _csrf(client)}


async def _partner(db, owner, percent="30.00", accepted=False):
    chief, _ = owner
    partner, workspace = await _make_owner(db, "socio")
    link = Affiliation(chief_user_id=chief.id, affiliate_user_id=partner.id, participation_percent=Decimal(percent))
    if accepted:
        link.accepted_percent, link.accepted_at = Decimal(percent), utc_now()
    db.add(link)
    await db.commit()
    return partner, workspace, link


async def _chief_shares_funnel(client, db, chief_ws) -> str:
    loop = InstagramLoop(workspace_id=chief_ws.id, name="Loop do funil", interval_min_minutes=10, interval_max_minutes=20,
                         daily_limit_per_account=5, post_type="reels", status="active")
    db.add(loop)
    await db.flush()
    video = InstagramMedia(workspace_id=chief_ws.id, storage_path=f"{chief_ws.id}/v/segredo.mp4", filename="segredo.mp4",
                           mime_type="video/mp4", media_type="video", size_bytes=10, caption="legenda secreta")
    db.add(video)
    await db.flush()
    db.add(InstagramLoopMedia(loop_id=loop.id, media_id=video.id))
    await db.commit()
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    flow = await client.post("/api/bots/flows", headers=headers, json={"name": "Funil Chefe", "definition": _flow()})
    assert flow.status_code == 201, flow.text
    no_loop = await client.post(f"/api/partners/flows/{flow.json()['id']}/share", headers=headers, json={"shared": True})
    assert no_loop.status_code == 422  # a funnel is always shared together with a loop
    shared = await client.post(f"/api/partners/flows/{flow.json()['id']}/share", headers=headers,
                               json={"shared": True, "loop_id": str(loop.id)})
    assert shared.status_code == 200, shared.text
    return flow.json()["id"]


@pytest.fixture
def storage(monkeypatch):
    copies: list[tuple[str, str]] = []

    class FakeStorage:
        async def copy(self, source, destination):
            copies.append((source, destination))

    from app.instagram import storage as storage_module

    monkeypatch.setattr(storage_module.SupabaseStorage, "from_settings", classmethod(lambda cls: FakeStorage()))
    return copies


@pytest.mark.anyio
async def test_commission_needs_acceptance_and_split_goes_into_the_charge(client, db_session, owner, apis) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner)

    headers = await _as(client, "socio@example.com")
    me = (await client.get("/api/partners/me")).json()
    assert me["role"] == "partner" and me["partnership"]["pending_acceptance"] is True
    assert me["shop_ref"] == f"fp-{partner_ws.id.hex}"
    wrong = await client.post("/api/partners/me/accept", headers=headers, json={"percent": "25"})
    assert wrong.status_code == 409
    ok = await client.post("/api/partners/me/accept", headers=headers, json={"percent": "30"})
    assert ok.status_code == 200, ok.text
    assert await db_session.scalar(select(AppNotification.id).where(AppNotification.user_id == chief.id))

    # the partner's bot runs the chief's shared funnel: subaccount charge, 30% to the chief
    shared_flow_id = await _chief_shares_funnel(client, db_session, chief_ws)
    headers = await _as(client, "socio@example.com")
    connected = await client.post("/api/bots", headers=headers, json={"token": TOKEN, "flow_id": shared_flow_id})
    assert connected.status_code == 201, connected.text
    bot = connected.json()
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    created = apis.methods("pix.create")[-1]
    assert created["shop_id"] == f"fp-{partner_ws.id.hex}"
    assert created["splits"] == [{"shop_id": f"fp-{chief_ws.id.hex}", "percent": 30.0}]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.split_percent == Decimal("30.00") and order.split_chief_user_id == chief.id
    assert order.origin == "shared_funnel"
    # net 18.90 (19.90 - 1.00 fee) -> chief 5.67, partner 13.23
    assert order.split_amount == Decimal("5.67") and order.partner_net == Decimal("13.23")

    # a resent webhook never counts the sale twice
    for _ in range(2):
        raw, sig = _signed(_paid_event(order.id))
        assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200
    totals = (await client.get("/api/partners/me")).json()["totals"]
    assert totals["sales"] == 1 and totals["commission"] == 5.67 and totals["net"] == 13.23
    await db_session.commit()
    notices = {
        (row.user_id, row.kind): row.title
        for row in await db_session.scalars(select(AppNotification).where(AppNotification.kind.in_(("sale", "commission"))))
    }
    assert notices[(partner.id, "sale")] == "⚡ Nova venda!"
    assert notices[(chief.id, "commission")] == "💰 Comissão recebida!"
    bodies = {row.kind: row.body for row in await db_session.scalars(select(AppNotification))}
    assert bodies["sale"] == "Você recebeu R$ 13,23" and bodies["commission"].startswith("Você recebeu R$ 5,67")  # sent once: the resent webhook added nothing

    # chief: sees the partner's numbers and operation, never the bot token
    chief_headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    row = (await client.get("/api/affiliates")).json()["rows"][0]
    assert row["commission_received"] == "5.67" and row["bot_sales"] == 1 and row["pending_acceptance"] is False
    ops = await client.get(f"/api/partners/{link.id}/operations")
    assert ops.status_code == 200 and ops.json()["bots"][0]["username"] == "ana_vip_bot"
    assert TOKEN not in json.dumps(ops.json()) and "encrypted_token" not in ops.text

    # a new percentage waits for a new acceptance: the next sale still splits 30%
    changed = await client.patch(f"/api/affiliates/{link.id}", headers=chief_headers, json={"participation_percent": "40"})
    assert changed.status_code == 200 and changed.json()["pending_acceptance"] is True
    await _as(client, "socio@example.com")
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert apis.methods("pix.create")[-1]["splits"][0]["percent"] == 30.0
    assert (await client.get("/api/partners/me")).json()["partnership"]["pending_acceptance"] is True


@pytest.mark.anyio
async def test_billing_routes(db_session, owner, super_admin) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner)
    shared = TgFlow(workspace_id=chief_ws.id, name="Modelo", definition={}, shared=True)
    db_session.add(shared)
    await db_session.commit()
    # not accepted: the shared funnel is not available, own funnels have no split
    assert (await service.billing_route(db_session, partner_ws.id, shared.id)).allowed is False
    route = await service.billing_route(db_session, partner_ws.id)
    assert route.shop_ref == f"fp-{partner_ws.id.hex}" and route.splits == [] and route.origin == "own_funnel"
    link.accepted_percent, link.accepted_at = Decimal("30"), utc_now()
    chief.platform_role = "SUPER_ADMIN"  # the chief is the platform owner: commission to the main account
    await db_session.commit()
    route = await service.billing_route(db_session, partner_ws.id, shared.id)
    assert route.origin == "shared_funnel" and route.splits == [{"parent": True, "percent": 30.0}]
    assert route.preview(Decimal("100.00")) == (Decimal("30.00"), Decimal("70.00"))
    # own funnel: no commission (platform fee is 0 until the Super Admin sets one)
    assert (await service.billing_route(db_session, partner_ws.id)).splits == []
    # the platform owner's own charges stay on the main account
    assert (await service.billing_route(db_session, chief_ws.id)).shop_ref is None


@pytest.mark.anyio
async def test_shared_funnel_runs_but_its_content_never_reaches_the_partner(client, db_session, owner, apis, storage) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    stranger, _ = await _make_owner(db_session, "estranho")
    flow_id = await _chief_shares_funnel(client, db_session, chief_ws)

    headers = await _as(client, "socio@example.com")
    listed = (await client.get("/api/bots/flows/list")).json()
    assert listed["flows"] == [] and listed["shared_flows"] == [{"id": flow_id, "name": "Funil Chefe", "shared_from_chief": True}]
    assert "Oi, {nome}" not in json.dumps((await client.get("/api/partners/shared")).json())
    for path in (f"/api/bots/flows/{flow_id}", f"/api/bots/flows/{flow_id}/export", f"/api/bots/flows/{flow_id}/summary"):
        assert (await client.get(path)).status_code == 404, path
    assert (await client.put(f"/api/bots/flows/{flow_id}", headers=headers, json={"name": "x", "definition": _flow()})).status_code == 404
    assert (await client.post(f"/api/bots/flows/{flow_id}/import-code", headers=headers)).status_code == 404
    assert (await client.post(f"/api/bots/flows/{flow_id}/duplicate", headers=headers)).status_code == 404

    # "use" copies only the paired loop (zero accounts); the funnel is never copied
    used = await client.post(f"/api/partners/shared/flows/{flow_id}/use", headers=headers)
    assert used.status_code == 201, used.text
    await db_session.commit()
    copy = await db_session.get(InstagramLoop, uuid.UUID(used.json()["loop"]["id"]))
    assert copy.workspace_id == partner_ws.id and copy.status == "paused"
    assert not await db_session.scalar(select(InstagramLoopAccount.loop_id).where(InstagramLoopAccount.loop_id == copy.id))
    assert await db_session.scalar(select(func.count(TgFlow.id)).where(TgFlow.workspace_id == partner_ws.id)) == 0
    # the loop's videos post normally, but the partner can never see or download them
    media = (await client.get("/api/media")).json()["media"]
    assert len(media) == 1 and media[0]["locked"] is True and media[0]["caption"] is None
    assert "segredo" not in json.dumps(media)
    assert (await client.get(f"/api/media/{media[0]['id']}/preview", follow_redirects=False)).status_code == 403

    # the partner's bot runs it; once the chief stops sharing, new charges stop
    bot = (await client.post("/api/bots", headers=headers, json={"token": TOKEN, "flow_id": flow_id})).json()
    await _send(client, db_session, bot["id"], _start())
    assert apis.methods("sendMessage")[0]["text"] == "Oi, Lucas!"
    chief_headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    await client.post(f"/api/partners/flows/{flow_id}/share", headers=chief_headers, json={"shared": False})
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert apis.methods("pix.create") == [] and "não está disponível" in apis.methods("sendMessage")[-1]["text"]

    # someone outside the partnership can neither see nor attach it
    other = await _as(client, "estranho@example.com")
    assert (await client.get("/api/bots/flows/list")).json()["shared_flows"] == []
    assert (await client.post(f"/api/partners/shared/flows/{flow_id}/use", headers=other)).status_code == 404


@pytest.mark.anyio
async def test_own_funnel_pays_only_the_platform_fee(client, db_session, owner, super_admin, apis) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    admin = await _as(client, "superadmin@example.com", "super admin password")
    assert (await client.put("/api/admin/platform-fee", headers=admin, json={"type": "fixed", "value": "1.00"})).status_code == 200

    headers = await _as(client, "socio@example.com")
    bot, _ = await _setup(client, headers)  # the partner's own funnel
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    created = apis.methods("pix.create")[-1]
    assert created["shop_id"] == f"fp-{partner_ws.id.hex}" and created["splits"] == [{"parent": True, "amount": 1.0}]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.origin == "own_funnel" and order.split_chief_user_id is None and order.split_amount is None
    assert order.platform_fee == Decimal("1.00") and order.partner_net == Decimal("17.90")  # 18.90 net - 1.00

    # Super Admin sees every funnel in full and can hand out an import code
    admin = await _as(client, "superadmin@example.com", "super admin password")
    flows = (await client.get("/api/admin/flows")).json()["flows"]
    detail = (await client.get(f"/api/admin/flows/{flows[0]['id']}")).json()
    resp = await client.post(f"/api/admin/flows/{flows[0]['id']}/import-code", headers=admin)
    assert resp.status_code == 200, resp.text
    code = resp.json()["code"]
    code = (await client.post(f"/api/admin/flows/{flows[0]['id']}/import-code", headers=admin)).json()["code"]
    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    assert (await client.get("/api/admin/flows")).status_code == 403
    imported = await client.post("/api/bots/flows/import-code", headers={"X-CSRF-Token": await _csrf(client)}, json={"code": code})
    assert imported.status_code == 201, imported.text
    assert imported.json()["definition"]["welcome"][0]["text"] == "Oi, {nome}!"
    bad = await client.post("/api/bots/flows/import-code", headers={"X-CSRF-Token": await _csrf(client)}, json={"code": code[:-3] + "AAA"})
    assert bad.status_code == 422


@pytest.mark.anyio
async def test_partner_invite_waits_for_approval_without_partnership(client, db_session, owner) -> None:
    partner, _ws, _link = await _partner(db_session, owner, accepted=True)
    await _as(client, "socio@example.com")
    code = (await client.get("/api/affiliates/invite")).json()["code"]
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    created = await client.post("/api/auth/register", headers={"X-CSRF-Token": await _csrf(client)}, json={
        "full_name": "Indicado", "email": "novo@example.com", "nickname": "novo",
        "password": PASSWORD, "confirm_password": PASSWORD, "invite_code": code,
    })
    assert created.status_code == 201, created.text
    new = await db_session.scalar(select(User).where(User.email == "novo@example.com"))
    assert new.is_approved is False and new.invited_by_user_id == partner.id
    assert not await db_session.scalar(select(Affiliation.id).where(Affiliation.affiliate_user_id == new.id))


@pytest.mark.anyio
async def test_admin_operations_is_super_admin_only(client, db_session, owner, super_admin) -> None:
    await _partner(db_session, owner)
    await _login(client, "owner@example.com", CHIEF_PASSWORD)
    assert (await client.get("/api/admin/operations")).status_code == 403
    await _as(client, "superadmin@example.com", "super admin password")
    data = (await client.get("/api/admin/operations")).json()
    by_name = {u["name"]: u for u in data["users"]}
    assert by_name["Socio"]["hierarchy"] == "partner" and by_name["FlashPost Owner"]["hierarchy"] == "chief"
    users = (await client.get("/api/admin/users")).json()["items"]
    assert {u["full_name"]: u["hierarchy"] for u in users}["Socio"] == "partner"


@pytest.mark.anyio
async def test_old_copy_of_a_chief_funnel_cannot_be_opened_or_copied(client, db_session, owner) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    flow_id = await _chief_shares_funnel(client, db_session, chief_ws)
    source = await db_session.get(TgFlow, uuid.UUID(flow_id))
    secret = TgMedia(workspace_id=partner_ws.id, kind="video", file_name="vip.mp4", content_type="video/mp4",
                     size_bytes=10, storage_path="x/vip.mp4", file_ids={}, locked=True)
    db_session.add(secret)
    old = TgFlow(workspace_id=partner_ws.id, name="Cópia antiga", definition=source.definition, template_flow_id=source.id)
    db_session.add(old)
    await db_session.commit()

    headers = await _as(client, "socio@example.com")
    listed = (await client.get("/api/bots/flows/list")).json()["flows"]
    assert listed[0]["protected"] is True and listed[0]["definition"] is None
    for path in (f"/api/bots/flows/{old.id}", f"/api/bots/flows/{old.id}/export"):
        assert (await client.get(path)).status_code == 403, path
    assert (await client.put(f"/api/bots/flows/{old.id}", headers=headers, json={"name": "x", "definition": _flow()})).status_code == 403
    assert (await client.post(f"/api/bots/flows/{old.id}/duplicate", headers=headers)).status_code == 403
    assert (await client.post(f"/api/bots/flows/{old.id}/import-code", headers=headers)).status_code == 403
    assert (await client.get("/api/bots/media/list")).json()["media"] == []
    assert (await client.get(f"/api/bots/media/{secret.id}/preview")).status_code == 403
