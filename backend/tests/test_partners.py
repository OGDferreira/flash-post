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
    assert no_loop.status_code == 200 and no_loop.json()["loop_id"] is None  # the loop is optional
    shared = await client.post(f"/api/partners/flows/{flow.json()['id']}/share", headers=headers,
                               json={"shared": True, "loop_id": str(loop.id)})
    assert shared.status_code == 200, shared.text
    return flow.json()["id"]


@pytest.fixture
def foreign_keys():
    """Enforce foreign keys like Postgres does (SQLite skips them by default)."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    def on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(Engine, "connect", on)
    yield
    event.remove(Engine, "connect", on)


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
async def test_shared_funnel_runs_but_its_content_never_reaches_the_partner(foreign_keys, client, db_session, owner, apis, storage) -> None:
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

    # "use" links only the paired loop (zero accounts); the funnel is never copied
    used = await client.post(f"/api/partners/shared/flows/{flow_id}/use", headers=headers)
    assert used.status_code == 201, used.text
    await db_session.commit()
    copy = await db_session.get(InstagramLoop, uuid.UUID(used.json()["loop"]["id"]))
    assert copy.workspace_id == partner_ws.id and copy.linked is True and copy.status == "active"
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

    # its sales still pay the chief's commission, exactly like the original funnel
    route = await service.billing_route(db_session, partner_ws.id, old.id)
    assert route.allowed and route.origin == "shared_funnel" and route.chief_user_id == chief.id
    assert route.splits == [{"shop_id": f"fp-{chief_ws.id.hex}", "percent": 30.0}]
    # a funnel the partner wrote from scratch pays no commission
    mine = TgFlow(workspace_id=partner_ws.id, name="Meu", definition=source.definition)
    db_session.add(mine)
    await db_session.commit()
    own = await service.billing_route(db_session, partner_ws.id, mine.id)
    assert own.origin == "own_funnel" and own.chief_user_id is None


async def _chief_loop(db, chief_ws, name="Loop Chefe", videos=("a.mp4",)) -> InstagramLoop:
    loop = InstagramLoop(workspace_id=chief_ws.id, name=name, interval_min_minutes=10, interval_max_minutes=20,
                         daily_limit_per_account=5, post_type="reels", status="active")
    db.add(loop)
    await db.flush()
    for filename in videos:
        video = InstagramMedia(workspace_id=chief_ws.id, storage_path=f"{chief_ws.id}/{uuid.uuid4()}/{filename}",
                               filename=filename, mime_type="video/mp4", media_type="video", size_bytes=10)
        db.add(video)
        await db.flush()
        db.add(InstagramLoopMedia(loop_id=loop.id, media_id=video.id))
    await db.commit()
    return loop


@pytest.mark.anyio
async def test_share_with_one_partner_or_everyone(client, db_session, owner, apis, storage) -> None:
    chief, chief_ws = owner
    ana, ana_ws, _ = await _partner(db_session, owner, accepted=True)
    bia, bia_ws = await _make_owner(db_session, "bia")
    db_session.add(Affiliation(chief_user_id=chief.id, affiliate_user_id=bia.id, participation_percent=Decimal("30"),
                               accepted_percent=Decimal("30"), accepted_at=utc_now()))
    stranger, _ = await _make_owner(db_session, "estranho")
    await db_session.commit()
    loop = await _chief_loop(db_session, chief_ws)

    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    partners = (await client.get("/api/partners/mine")).json()["partners"]
    assert {p["id"] for p in partners} == {str(ana.id), str(bia.id)}
    flow = (await client.post("/api/bots/flows", headers=headers, json={"name": "Funil Ana", "definition": _flow()})).json()
    # only the chief's own partners can be picked
    bad = await client.post(f"/api/partners/flows/{flow['id']}/share", headers=headers,
                            json={"shared": True, "partner_ids": [str(stranger.id)]})
    assert bad.status_code == 422
    # funnel + loop for Ana only: the loop goes to the same partner
    ok = await client.post(f"/api/partners/flows/{flow['id']}/share", headers=headers,
                           json={"shared": True, "partner_ids": [str(ana.id)], "loop_id": str(loop.id)})
    assert ok.status_code == 200 and ok.json()["shared_with"] == [str(ana.id)], ok.text
    await db_session.refresh(loop)
    assert loop.shared is True and loop.shared_with == [str(ana.id)]

    await _as(client, "bia@example.com")
    shared = (await client.get("/api/partners/shared")).json()
    assert shared["flows"] == [] and shared["loops"] == []
    assert (await client.get("/api/bots/flows/list")).json()["shared_flows"] == []
    assert (await client.post(f"/api/partners/shared/flows/{flow['id']}/use", headers=await _as(client, "bia@example.com"))).status_code == 404
    assert (await service.billing_route(db_session, bia_ws.id, uuid.UUID(flow["id"]))).allowed is False

    await _as(client, "socio@example.com")
    shared = (await client.get("/api/partners/shared")).json()
    assert [f["name"] for f in shared["flows"]] == ["Funil Ana"] and shared["flows"][0]["loop_name"] == "Loop Chefe"
    assert (await service.billing_route(db_session, ana_ws.id, uuid.UUID(flow["id"]))).allowed is True

    # then the chief shares the loop with everyone
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    assert (await client.post(f"/api/partners/loops/{loop.id}/share", headers=headers, json={"shared": True})).json()["shared_with"] is None
    await _as(client, "bia@example.com")
    assert [l["name"] for l in (await client.get("/api/partners/shared")).json()["loops"]] == ["Loop Chefe"]


@pytest.mark.anyio
async def test_linked_loop_follows_the_chief_and_posts_only_with_partner_accounts(foreign_keys, client, db_session, owner, storage) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner, accepted=True)
    from sqlalchemy import text
    assert (await db_session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
    loop = await _chief_loop(db_session, chief_ws, videos=("1.mp4", "2.mp4"))
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    assert (await client.post(f"/api/partners/loops/{loop.id}/share", headers=headers,
                              json={"shared": True, "partner_ids": [str(partner.id)]})).status_code == 200

    # the shared loop shows up by itself in the partner's area: same media, zero accounts
    headers = await _as(client, "socio@example.com")
    assert (await client.get("/api/partners/shared")).status_code == 200
    mine = (await client.get("/api/loops")).json()["loops"]
    assert len(mine) == 1 and mine[0]["linked"] is True and mine[0]["linked_available"] is True
    assert mine[0]["accounts"] == [] and mine[0]["media_count"] == 2 and mine[0]["status"] == "active"
    copy_id = mine[0]["id"]
    # media and schedule come from the chief; the partner only picks accounts
    edit = {"name": "x", "interval_min_minutes": 1, "interval_max_minutes": 1, "daily_limit_per_account": 1,
            "post_type": "reels", "media_ids": [], "account_ids": [], "auto_folder_ids": [str(uuid.uuid4())]}
    put = await client.put(f"/api/loops/{copy_id}", headers=headers, json=edit)
    assert put.status_code == 409, put.text
    assert (await client.post(f"/api/loops/{copy_id}/clone", headers=headers)).status_code == 409
    assert (await client.delete(f"/api/loops/{copy_id}", headers=headers)).status_code == 409

    # the chief adds a video and changes the interval: the copy follows on the next sync
    extra = InstagramMedia(workspace_id=chief_ws.id, storage_path=f"{chief_ws.id}/n/3.mp4", filename="3.mp4",
                           mime_type="video/mp4", media_type="video", size_bytes=10)
    db_session.add(extra)
    await db_session.flush()
    db_session.add(InstagramLoopMedia(loop_id=loop.id, media_id=extra.id))
    first = await db_session.scalar(select(InstagramLoopMedia).where(InstagramLoopMedia.loop_id == loop.id,
                                                                     InstagramLoopMedia.media_id != extra.id))
    await db_session.delete(first)
    loop.interval_min_minutes, loop.interval_max_minutes = 30, 40
    # ...and puts one caption and one Reels cover on every video
    cover = InstagramMedia(workspace_id=chief_ws.id, storage_path=f"{chief_ws.id}/c/capa.jpg", filename="capa.jpg",
                           mime_type="image/jpeg", media_type="image", size_bytes=10, is_cover=True)
    db_session.add(cover)
    await db_session.flush()
    loop.caption_mode, loop.caption = "all", "Legenda do chefe"
    loop.cover_mode, loop.cover_media_id = "all", cover.id
    await db_session.commit()
    await service.sync_all_shared_loops(db_session)
    copy = await db_session.get(InstagramLoop, uuid.UUID(copy_id), populate_existing=True)
    assert (copy.interval_min_minutes, copy.interval_max_minutes) == (30, 40)
    assert (copy.caption_mode, copy.caption, copy.cover_mode) == ("all", "Legenda do chefe", "all")
    copied_cover = await db_session.get(InstagramMedia, copy.cover_media_id)
    assert copied_cover.workspace_id == partner_ws.id and copied_cover.is_cover and copied_cover.template_media_id == cover.id
    await service.sync_all_shared_loops(db_session)  # a second sync reuses the copied cover
    await db_session.refresh(copy)
    assert copy.cover_media_id == copied_cover.id
    names = set(await db_session.scalars(
        select(InstagramMedia.filename).join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
        .where(InstagramLoopMedia.loop_id == copy.id)
    ))
    assert len(names) == 2 and "3.mp4" in names
    assert all(dst.startswith(str(partner_ws.id)) for _src, dst in storage)

    # the chief stops sharing: the copy pauses and cannot be turned back on
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    await client.post(f"/api/partners/loops/{loop.id}/share", headers=headers, json={"shared": False})
    await service.sync_all_shared_loops(db_session)
    await db_session.refresh(copy)
    assert copy.status == "paused"
    headers = await _as(client, "socio@example.com")
    assert (await client.patch(f"/api/loops/{copy_id}/status", headers=headers, json={"enabled": True})).status_code == 409
    assert (await client.delete(f"/api/loops/{copy_id}", headers=headers)).status_code == 204


@pytest.mark.anyio
async def test_chief_shares_from_the_partner_row(client, db_session, owner) -> None:
    chief, chief_ws = owner
    ana, _ana_ws, ana_link = await _partner(db_session, owner, accepted=True)
    bia, _ = await _make_owner(db_session, "bia")
    bia_link = Affiliation(chief_user_id=chief.id, affiliate_user_id=bia.id, participation_percent=Decimal("30"))
    db_session.add(bia_link)
    loop = await _chief_loop(db_session, chief_ws)
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    flow = (await client.post("/api/bots/flows", headers=headers, json={"name": "Funil", "definition": _flow()})).json()

    on = await client.post(f"/api/partners/{ana_link.id}/shares", headers=headers, json={"kind": "flow", "id": flow["id"], "shared": True})
    assert on.status_code == 200 and on.json()["shared_with"] == [str(ana.id)], on.text
    await client.post(f"/api/partners/{bia_link.id}/shares", headers=headers, json={"kind": "flow", "id": flow["id"], "shared": True})
    off = await client.post(f"/api/partners/{ana_link.id}/shares", headers=headers, json={"kind": "flow", "id": flow["id"], "shared": False})
    assert off.json()["shared_with"] == [str(bia.id)]
    # a loop shared with everyone: removing one partner keeps the others
    await client.post(f"/api/partners/loops/{loop.id}/share", headers=headers, json={"shared": True})
    off = await client.post(f"/api/partners/{bia_link.id}/shares", headers=headers, json={"kind": "loop", "id": str(loop.id), "shared": False})
    assert off.json() == {"id": str(loop.id), "shared": True, "shared_with": [str(ana.id)]}
    off = await client.post(f"/api/partners/{ana_link.id}/shares", headers=headers, json={"kind": "loop", "id": str(loop.id), "shared": False})
    assert off.json()["shared"] is False
    # another chief's partner row is out of reach
    assert (await client.post(f"/api/partners/{uuid.uuid4()}/shares", headers=headers,
                              json={"kind": "loop", "id": str(loop.id), "shared": True})).status_code == 404

@pytest.mark.anyio
async def test_partners_ranking_shows_positions_but_never_revenue(client, db_session, owner) -> None:
    from tests.test_wallet import _paid

    chief, chief_ws = owner
    partner, partner_ws, _ = await _partner(db_session, owner, accepted=True)
    other, other_ws = await _make_owner(db_session, "outro")
    db_session.add(Affiliation(chief_user_id=chief.id, affiliate_user_id=other.id, participation_percent=Decimal("10")))
    await db_session.commit()
    for _ in range(2):
        await _paid(db_session, partner_ws)
    await _paid(db_session, chief_ws)

    await _as(client, "socio@example.com")
    response = await client.get("/api/bots/partners-ranking?period=today")
    assert response.status_code == 200, response.text
    members = response.json()["members"]
    assert [(m["nickname"], m["position"], m["is_me"]) for m in members][:2] == [("socio", 1, True), (chief.nickname, 2, False)]
    assert members[2]["nickname"] == "outro" and members[2]["has_sales"] is False
    assert "19.9" not in response.text and "39.8" not in response.text and "revenue" not in response.text

    # someone outside the partnership only sees themselves
    await _make_owner(db_session, "solo")
    await _as(client, "solo@example.com")
    alone = (await client.get("/api/bots/partners-ranking")).json()["members"]
    assert [m["nickname"] for m in alone] == ["solo"]


@pytest.mark.anyio
async def test_activity_log_lists_leads_pix_and_sales(client, db_session, owner) -> None:
    from tests.test_wallet import _paid

    _, chief_ws = owner
    await _paid(db_session, chief_ws)
    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    response = await client.get("/api/bots/activity")
    assert response.status_code == 200, response.text
    kinds = sorted(item["kind"] for item in response.json()["items"])
    assert kinds == ["lead", "pix", "sale"]
    sale = next(item for item in response.json()["items"] if item["kind"] == "sale")
    assert sale["amount"] == 19.9 and sale["bot"] == "b"
