"""Partners: commission acceptance, SmokePay split, shared templates, isolation."""

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

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

    # the partner's own bot: charge in the partner's subaccount, 30% to the chief's
    bot, _flow_out = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    created = apis.methods("pix.create")[-1]
    assert created["shop_id"] == f"fp-{partner_ws.id.hex}"
    assert created["splits"] == [{"shop_id": f"fp-{chief_ws.id.hex}", "percent": 30.0}]
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.split_percent == Decimal("30.00") and order.split_chief_user_id == chief.id
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
    assert "Nova venda" in notices[(partner.id, "sale")]
    assert "R$ 5,67" in notices[(chief.id, "commission")]  # sent once: the resent webhook added nothing

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
    # not accepted: own subaccount, no split
    route = await service.billing_route(db_session, partner_ws.id)
    assert route.shop_ref == f"fp-{partner_ws.id.hex}" and route.splits == []
    link.accepted_percent, link.accepted_at = Decimal("30"), utc_now()
    await db_session.commit()
    # chief is the platform owner (Super Admin): commission to the main account
    chief.platform_role = "SUPER_ADMIN"
    await db_session.commit()
    route = await service.billing_route(db_session, partner_ws.id)
    assert route.splits == [{"parent": True, "percent": 30.0}]
    assert route.preview(Decimal("100.00")) == (Decimal("30.00"), Decimal("70.00"))
    # the platform owner's own charges stay on the main account
    assert (await service.billing_route(db_session, chief_ws.id)).shop_ref is None


@pytest.mark.anyio
async def test_shared_loop_and_funnel_are_copied_never_changed(client, db_session, owner, apis, storage) -> None:
    chief, chief_ws = owner
    partner, partner_ws, link = await _partner(db_session, owner)
    stranger, _ = await _make_owner(db_session, "estranho")

    media = InstagramMedia(workspace_id=chief_ws.id, storage_path=f"{chief_ws.id}/m1/video.mp4", filename="video.mp4",
                           mime_type="video/mp4", media_type="video", size_bytes=10)
    loop = InstagramLoop(workspace_id=chief_ws.id, name="Loop Chefe", interval_min_minutes=10, interval_max_minutes=20,
                         daily_limit_per_account=5, post_type="reels", status="active")
    private = InstagramLoop(workspace_id=chief_ws.id, name="Privado", interval_min_minutes=10, interval_max_minutes=20,
                            daily_limit_per_account=5, post_type="reels")
    db_session.add_all([media, loop, private])
    await db_session.flush()
    db_session.add(InstagramLoopMedia(loop_id=loop.id, media_id=media.id))
    photo = TgMedia(workspace_id=chief_ws.id, kind="photo", file_name="a.jpg", content_type="image/jpeg", size_bytes=5,
                    storage_path=f"{chief_ws.id}/p1/a.jpg", file_ids={"x": "y"})
    db_session.add(photo)
    await db_session.commit()

    chief_headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    flow = await client.post("/api/bots/flows", headers=chief_headers, json={
        "name": "Funil Chefe", "definition": _flow(welcome=[{"type": "photo", "media_ids": [str(photo.id)], "text": "Oi"}])})
    assert flow.status_code == 201, flow.text
    flow_id = flow.json()["id"]
    assert (await client.post(f"/api/partners/loops/{loop.id}/share", headers=chief_headers, json={"shared": True})).status_code == 200
    assert (await client.post(f"/api/partners/flows/{flow_id}/share", headers=chief_headers, json={"shared": True})).status_code == 200

    # partner must accept the commission first
    headers = await _as(client, "socio@example.com")
    shared = (await client.get("/api/partners/shared")).json()
    assert [l["name"] for l in shared["loops"]] == ["Loop Chefe"] and shared["accepted"] is False
    blocked = await client.post(f"/api/partners/shared/loops/{loop.id}/use", headers=headers)
    assert blocked.status_code == 403
    await client.post("/api/partners/me/accept", headers=headers, json={"percent": "30"})
    used = await client.post(f"/api/partners/shared/loops/{loop.id}/use", headers=headers)
    assert used.status_code == 201, used.text
    assert (await client.post(f"/api/partners/shared/loops/{private.id}/use", headers=headers)).status_code == 404

    await db_session.commit()
    copy = await db_session.get(InstagramLoop, uuid.UUID(used.json()["id"]))
    assert copy.workspace_id == partner_ws.id and copy.status == "paused" and copy.template_loop_id == loop.id
    assert not await db_session.scalar(select(InstagramLoopAccount.loop_id).where(InstagramLoopAccount.loop_id == copy.id))
    copied_media = await db_session.scalar(
        select(InstagramMedia).join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
        .where(InstagramLoopMedia.loop_id == copy.id))
    assert copied_media.workspace_id == partner_ws.id and copied_media.id != media.id
    assert (media.storage_path, copied_media.storage_path) in storage

    used_flow = await client.post(f"/api/partners/shared/flows/{flow_id}/use", headers=headers)
    assert used_flow.status_code == 201, used_flow.text
    mine = (await client.get(f"/api/bots/flows/{used_flow.json()['id']}")).json()
    welcome_media = mine["definition"]["welcome"][0]["media_ids"][0]
    assert welcome_media != str(photo.id)
    assert mine["definition"]["plans"][0]["delivery"]["group_chat_id"] == 0  # partner picks their own group
    saved = await client.put(f"/api/bots/flows/{mine['id']}", headers=headers,
                             json={"name": "Meu funil", "definition": {**mine["definition"], "support_username": "socio"}})
    assert saved.status_code == 200, saved.text
    await db_session.commit()
    notices = list(await db_session.scalars(select(AppNotification.kind).where(AppNotification.user_id == chief.id)))
    assert "partner-flow-changed" in notices
    original = await db_session.get(TgFlow, uuid.UUID(flow_id))
    await db_session.refresh(original)
    assert original.name == "Funil Chefe" and original.definition["welcome"][0]["media_ids"] == [str(photo.id)]

    # someone who is not this chief's partner sees nothing and copies nothing
    other = await _as(client, "estranho@example.com")
    assert (await client.get("/api/partners/shared")).json()["available"] is False
    assert (await client.post(f"/api/partners/shared/flows/{flow_id}/use", headers=other)).status_code == 404
    assert (await client.get(f"/api/partners/{link.id}/operations")).status_code == 404


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
