"""End-to-end bot journeys with fake Telegram and SmokePay servers."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import engine, http
from app.core.config import get_settings
from app.models import TgGroup, TgJob, TgLead, TgMedia, TgOrder, TgSubscription

TOKEN = "123456:AAFakeTokenForTests_abcdefghij"
WEBHOOK_SECRET = "whsec_test"
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()
GROUP_ID = -1001234567890


def _form_fields(request: httpx.Request) -> dict:
    """Text fields of a multipart Telegram call (files are skipped)."""
    fields = {}
    for part in request.content.split(b"--" + request.headers["content-type"].split("boundary=")[1].encode()):
        head, _, value = part.partition(b"\r\n\r\n")
        if b"filename=" in head or b'name="' not in head:
            continue
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        text = value.rstrip(b"\r\n").decode()
        try:
            fields[name] = json.loads(text) if text[:1] in "{[" else text
        except ValueError:
            fields[name] = text
    return fields


def pix_message(apis: "FakeApis") -> dict:
    """Last message carrying the PIX code (photo caption or plain text)."""
    for method, body in reversed(apis.calls):
        text = body.get("caption") if method == "sendPhoto" else body.get("text") if method == "sendMessage" else None
        if text and "<code>" in text:
            return {**body, "text": text}
    raise AssertionError("no PIX message sent")


class FakeApis:
    """Answers Telegram Bot API and SmokePay calls and records them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.pix_status = "pending"
        self.pix_amount = 19.90
        self.get_me_status = 200
        self.message_id = 0
        self.member_status = "administrator"
        self.refuse_fixed_splits = False  # answer 400 to a charge with a fixed-amount split

    def methods(self, name: str) -> list[dict]:
        return [body for method, body in self.calls if method == name]

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.telegram.org" in url:
            method = url.rsplit("/", 1)[-1]
            if request.headers.get("content-type", "").startswith("multipart"):
                body = {"multipart": True, **_form_fields(request)}
            else:
                body = json.loads(request.content or b"{}")
            self.calls.append((method, body))
            if method == "getMe":
                if self.get_me_status != 200:
                    return httpx.Response(401, json={"ok": False, "error_code": 401, "description": "Unauthorized"})
                return httpx.Response(200, json={"ok": True, "result": {"id": 987, "is_bot": True, "username": "ana_vip_bot", "first_name": "Ana VIP"}})
            if method == "getChat":
                if body.get("chat_id") == "@canal_cache":
                    return httpx.Response(200, json={"ok": True, "result": {"id": -1009990001, "type": "channel", "title": "Cache da Ana"}})
                return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})
            if method == "getChatMember":
                return httpx.Response(200, json={"ok": True, "result": {"status": self.member_status, "user": {"id": 987}}})
            if method == "createChatInviteLink":
                return httpx.Response(200, json={"ok": True, "result": {"invite_link": "https://t.me/+invite123"}})
            self.message_id += 1
            result: object = True
            if method.startswith("send"):
                result = {"message_id": self.message_id, "photo": [{"file_id": "small"}, {"file_id": "PHOTO_FILE_ID"}]}
            if method == "sendMediaGroup":
                self.message_id += 1
                result = [{"message_id": self.message_id - 1}, {"message_id": self.message_id}]
            return httpx.Response(200, json={"ok": True, "result": result})
        if "/api/pix/create" in url:
            body = json.loads(request.content)
            self.calls.append(("pix.create", body))
            assert request.headers["x-api-key"] == "smoke_test_key"
            if self.refuse_fixed_splits and any("amount" in rule for rule in body.get("splits", [])):
                return httpx.Response(400, json={"success": False, "error": "splits inválidos"})
            return httpx.Response(201, json={"success": True, "transaction": {
                "id": f"tx-{body['external_id']}", "txid": "g1", "external_id": body["external_id"], "amount": body["amount"],
                "fee": 1.0, "net_amount": body["amount"] - 1, "status": "pending",
                "pix_copia_cola": "00020126PIXCODE", "qr_code_base64": f"data:image/png;base64,{PNG}",
                "expires_at": "2030-01-01T00:00:00Z",
            }})
        if "/api/pix/" in url:
            self.calls.append(("pix.get", {"id": url.rsplit("/", 1)[-1]}))
            return httpx.Response(200, json={"id": "tx-1", "status": self.pix_status, "amount": self.pix_amount, "payer_name": "Comprador"})
        raise AssertionError(f"unexpected request {url}")


@pytest.fixture
def apis(monkeypatch):
    fake = FakeApis()
    http.set_transport(httpx.MockTransport(fake.handler))
    settings = get_settings()
    monkeypatch.setattr(settings, "smokepay_api_key", SecretStr("smoke_test_key"))
    monkeypatch.setattr(settings, "smokepay_webhook_secret", SecretStr(WEBHOOK_SECRET))
    yield fake
    http.set_transport(None)


async def _csrf(client: AsyncClient) -> str:
    return (await client.get("/api/auth/csrf")).json()["csrf_token"]


async def _login(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": await _csrf(client)}


def _flow(**overrides) -> dict:
    definition = {
        "welcome": [{"type": "text", "text": "Oi, {nome}!"}],
        "offer": {"text": "Escolha 👇"},
        "plans": [{
            "id": "vip", "name": "VIP Mensal", "price": "19.90", "duration_days": 30,
            "delivery": {"type": "group", "group_chat_id": GROUP_ID},
        }],
        "payment": {"expiration_minutes": 15},
    }
    definition.update(overrides)
    return definition


async def _setup(client: AsyncClient, headers: dict, definition: dict | None = None) -> tuple[dict, dict]:
    flow = await client.post("/api/bots/flows", headers=headers, json={"name": "Funil Ana", "definition": definition or _flow()})
    assert flow.status_code == 201, flow.text
    bot = await client.post("/api/bots", headers=headers, json={"token": TOKEN, "flow_id": flow.json()["id"]})
    assert bot.status_code == 201, bot.text
    return bot.json(), flow.json()


_update_ids = iter(range(1, 10_000))


async def _send(client: AsyncClient, db: AsyncSession, bot_id: str, update: dict, update_id: int | None = None) -> httpx.Response:
    from app.models import TgBot

    bot = await db.get(TgBot, uuid.UUID(bot_id))
    await db.refresh(bot)
    body = {"update_id": update_id or next(_update_ids), **update}
    return await client.post(f"/api/bots/telegram/{bot_id}", headers={"X-Telegram-Bot-Api-Secret-Token": bot.webhook_secret}, json=body)


def _start(text: str = "/start ig_ana") -> dict:
    user = {"id": 555, "is_bot": False, "first_name": "Lucas", "username": "lucas"}
    return {"message": {"message_id": 1, "from": user, "chat": {"id": 555, "type": "private"}, "text": text}}


def _tap(data: str) -> dict:
    user = {"id": 555, "is_bot": False, "first_name": "Lucas"}
    return {"callback_query": {"id": "cb1", "from": user, "data": data, "message": {"message_id": 9, "chat": {"id": 555, "type": "private"}}}}


def _signed(payload: dict, secret: str = WEBHOOK_SECRET, ts: int | None = None) -> tuple[bytes, dict]:
    raw = json.dumps(payload).encode()
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, {"x-webhook-signature": f"t={ts},v1={sig}", "content-type": "application/json"}


def _paid_event(order_id: uuid.UUID, amount: float = 19.90) -> dict:
    return {"event": "payment.confirmed", "transaction_id": "tx-1", "external_id": f"tgo_{order_id}",
            "status": "paid", "amount": amount, "fee": 1.0, "net_amount": amount - 1, "payer_name": "Comprador"}


async def _admin_in_group(client, db, bot_id: str) -> None:
    update = {"my_chat_member": {
        "chat": {"id": GROUP_ID, "type": "supergroup", "title": "VIP da Ana"},
        "from": {"id": 1}, "date": 0,
        "old_chat_member": {"status": "member", "user": {"id": 987}},
        "new_chat_member": {"status": "administrator", "user": {"id": 987}, "can_invite_users": True},
    }}
    assert (await _send(client, db, bot_id, update)).status_code == 200


@pytest.mark.anyio
async def test_connect_bot_registers_webhook_and_rejects_bad_tokens(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers)
    assert bot["username"] == "ana_vip_bot"
    webhook = apis.methods("setWebhook")[0]
    assert webhook["url"] == f"http://testserver/api/bots/telegram/{bot['id']}"
    assert len(webhook["secret_token"]) >= 32
    assert "callback_query" in webhook["allowed_updates"]

    again = await client.post("/api/bots", headers=headers, json={"token": TOKEN})
    assert again.status_code == 409
    apis.get_me_status = 401
    bad = await client.post("/api/bots", headers=headers, json={"token": "999:BadTokenBadTokenBadToken"})
    assert bad.status_code == 422
    assert "BotFather" in bad.json()["detail"]
    # the token never leaks back
    listed = (await client.get("/api/bots")).json()["bots"]
    assert TOKEN not in json.dumps(listed)


@pytest.mark.anyio
async def test_flow_validation_requires_a_delivery(client, owner, apis) -> None:
    headers = await _login(client)
    plan = {"id": "p1", "name": "Pack", "price": "9.90"}
    response = await client.post("/api/bots/flows", headers=headers, json={"name": "x", "definition": {"plans": [plan]}})
    assert response.status_code == 422
    assert "entrega" in response.json()["detail"]
    cheap = await client.post("/api/bots/flows", headers=headers, json={"name": "x", "definition": {
        "plans": [{**plan, "price": "0.50"}], "default_delivery": {"type": "default", "text": "ok"}}})
    assert cheap.status_code == 422  # SmokePay minimum is R$ 1,00


@pytest.mark.anyio
async def test_save_flow_bumps_version_and_lists_usage(client, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    definition = _flow(age_gate={"enabled": True})
    saved = await client.put(f"/api/bots/flows/{flow['id']}", headers=headers, json={"name": "Funil novo", "definition": definition})
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == flow["version"] + 1
    assert saved.json()["definition"]["age_gate"]["enabled"] is True
    listed = (await client.get("/api/bots/flows/list")).json()["flows"]
    assert [(f["name"], f["bots"]) for f in listed] == [("Funil novo", 1)]
    copy = await client.post(f"/api/bots/flows/{flow['id']}/duplicate", headers=headers)
    assert copy.status_code == 201 and copy.json()["name"] == "Funil novo (cópia)"
    assert (await client.delete(f"/api/bots/flows/{flow['id']}", headers=headers)).status_code == 204
    bots = (await client.get("/api/bots")).json()["bots"]
    assert bots[0]["id"] == bot["id"] and bots[0]["flow_id"] is None


@pytest.mark.anyio
async def test_full_journey_start_pix_webhook_and_vip_invite(client, db_session: AsyncSession, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers)
    await _admin_in_group(client, db_session, bot["id"])
    group = await db_session.scalar(select(TgGroup))
    assert group.title == "VIP da Ana" and group.can_invite

    # /start: welcome then offer with the plan button
    assert (await _send(client, db_session, bot["id"], _start())).status_code == 200
    messages = apis.methods("sendMessage")
    assert messages[0]["text"] == "Oi, Lucas!"
    assert messages[1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "plan:vip"
    lead = await db_session.scalar(select(TgLead))
    assert lead.source == "ig_ana"

    # same update delivered twice is processed once
    before = len(apis.calls)
    assert (await _send(client, db_session, bot["id"], _start(), update_id=777)).status_code == 200
    after_first = len(apis.calls)
    assert (await _send(client, db_session, bot["id"], _start(), update_id=777)).status_code == 200
    assert len(apis.calls) == after_first > before

    # choose the plan: PIX created with idempotent external id, QR + copy button sent
    assert (await _send(client, db_session, bot["id"], _tap("plan:vip"))).status_code == 200
    created = apis.methods("pix.create")[0]
    order = await db_session.scalar(select(TgOrder))
    assert created["amount"] == 19.9 and created["external_id"] == f"tgo_{order.id}"
    assert created["expiration"] == 900
    assert created["webhook_url"] == "http://testserver/api/bots/pay/smokepay"
    sent = pix_message(apis)
    assert "00020126PIXCODE" in sent["text"]
    buttons = sent["reply_markup"]["inline_keyboard"]
    assert buttons[0][0]["copy_text"]["text"] == "00020126PIXCODE"
    assert buttons[1][0]["callback_data"] == f"chk:{order.id}"
    # tapping the plan again reuses the pending PIX
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert len(apis.methods("pix.create")) == 1

    # forged webhook is rejected; the signed one pays and delivers once
    raw, sig = _signed(_paid_event(order.id), secret="wrong")
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 401
    raw, sig = _signed(_paid_event(order.id))
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "paid" and order.payer_name == "Comprador"
    invites = apis.methods("createChatInviteLink")
    assert len(invites) == 1 and invites[0]["member_limit"] == 1 and invites[0]["chat_id"] == GROUP_ID
    join = apis.methods("sendMessage")[-1]
    assert join["reply_markup"]["inline_keyboard"][0][0]["url"] == "https://t.me/+invite123"
    sub = await db_session.scalar(select(TgSubscription))
    days = (engine.aware(sub.ends_at) - datetime.now(timezone.utc)).days
    assert 29 <= days <= 30

    summary = (await client.get("/api/bots/summary")).json()
    assert summary["pix_paid"] == 1 and summary["revenue"] == "19.90" and summary["leads"] == 1
    orders = (await client.get("/api/bots/orders/list")).json()["orders"]
    assert orders[0]["status"] == "paid" and orders[0]["source"] == "ig_ana"

    analytics = (await client.get("/api/bots/analytics?period=today")).json()
    assert analytics["funis"] and analytics["funis"][0]["sales"] == 1 and analytics["funis"][0]["revenue"] == 19.9
    assert analytics["planos"] and analytics["planos"][0]["sales"] == 1 and analytics["planos"][0]["revenue"] == 19.9

    # subscription end removes the member without a permanent ban
    await db_session.execute(update(TgSubscription).values(ends_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await db_session.execute(update(TgJob).where(TgJob.kind == "end_subscription").values(run_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await db_session.commit()
    await engine.run_due_jobs(db_session)
    assert apis.methods("banChatMember")[0]["user_id"] == 555
    assert apis.methods("unbanChatMember")[0]["only_if_banned"] is True
    await db_session.refresh(sub)
    assert sub.status == "expired"


@pytest.mark.anyio
async def test_wrong_amount_goes_to_review_without_delivery(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    order = await db_session.scalar(select(TgOrder))
    raw, sig = _signed(_paid_event(order.id, amount=1.00))
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    assert order.status == "review"
    assert not apis.methods("createChatInviteLink")


@pytest.mark.anyio
async def test_check_button_and_expiry(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(
        plans=[{"id": "pk", "name": "Pack", "price": "19.90", "duration_days": None,
                "delivery": {"type": "default", "text": "Seu pack 💕", "link": {"label": "Abrir", "url": "https://example.com/pack"}}}],
    ))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:pk"))
    order = await db_session.scalar(select(TgOrder))

    # not paid yet: alert, still pending
    await _send(client, db_session, bot["id"], _tap(f"chk:{order.id}"))
    answer = apis.methods("answerCallbackQuery")[-1]
    assert answer["show_alert"] is True
    await db_session.refresh(order)
    assert order.status == "pending"

    # paid at the gateway: the button approves and delivers
    apis.pix_status = "paid"
    await _send(client, db_session, bot["id"], _tap(f"chk:{order.id}"))
    await db_session.refresh(order)
    assert order.status == "paid"
    link_message = apis.methods("sendMessage")[-1]
    assert link_message["reply_markup"]["inline_keyboard"][0][0]["url"] == "https://example.com/pack"


@pytest.mark.anyio
async def test_unpaid_pix_expires_with_regenerate_button(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await db_session.execute(update(TgJob).where(TgJob.kind == "expire_order").values(run_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await db_session.commit()
    await engine.run_due_jobs(db_session)
    order = await db_session.scalar(select(TgOrder))
    await db_session.refresh(order)
    assert order.status == "expired"
    expired = apis.methods("sendMessage")[-1]
    assert expired["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "plan:vip"


@pytest.mark.anyio
async def test_age_gate_and_secret_check(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(age_gate={"enabled": True}))
    forged = await client.post(f"/api/bots/telegram/{bot['id']}", headers={"X-Telegram-Bot-Api-Secret-Token": "nope"}, json={"update_id": 1})
    assert forged.status_code == 401

    await _send(client, db_session, bot["id"], _start())
    gate = apis.methods("sendMessage")[-1]
    assert gate["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "age:ok"
    assert len(apis.methods("sendMessage")) == 1  # nothing else before confirming
    await _send(client, db_session, bot["id"], _tap("age:ok"))
    lead = await db_session.scalar(select(TgLead))
    await db_session.refresh(lead)
    assert lead.age_confirmed_at is not None
    assert apis.methods("sendMessage")[1]["text"] == "Oi, Lucas!"


@pytest.mark.anyio
async def test_media_blocks_upload_once_then_reuse_file_id(client, db_session, owner, apis, monkeypatch) -> None:
    from app.instagram.storage import SupabaseStorage

    async def fake_upload(self, path, content, content_type):
        return None

    async def fake_bytes(media):
        return b"\xff\xd8\xffjpeg"

    monkeypatch.setattr(SupabaseStorage, "from_settings", classmethod(lambda cls: cls("https://x.supabase.co", "k")))
    monkeypatch.setattr(SupabaseStorage, "upload", fake_upload)
    monkeypatch.setattr(engine, "load_media_bytes", fake_bytes)
    headers = await _login(client)
    uploaded = await client.post(
        "/api/bots/media?filename=foto.jpg",
        headers={**headers, "content-type": "image/jpeg"},
        content=b"\xff\xd8\xff" + b"0" * 100,
    )
    assert uploaded.status_code == 201, uploaded.text
    media_id = uploaded.json()["id"]
    wrong = await client.post("/api/bots/media?filename=x.jpg", headers={**headers, "content-type": "image/jpeg"}, content=b"not a jpeg")
    assert wrong.status_code == 415
    # an iPhone .MOV (QuickTime) is kept as an MP4 video
    mov = await client.post(
        "/api/bots/media?filename=IMG_0370.MOV",
        headers={**headers, "content-type": "video/quicktime"},
        content=b"\x00\x00\x00\x14ftypqt  " + b"0" * 100,
    )
    assert mov.status_code == 201, mov.text
    assert mov.json()["kind"] == "video" and mov.json()["file_name"] == "IMG_0370.mp4" and mov.json()["content_type"] == "video/mp4"

    bot, _ = await _setup(client, headers, _flow(welcome=[{"type": "photo", "media_ids": [media_id], "text": "Oi {nome}", "spoiler": True}]))
    await _send(client, db_session, bot["id"], _start())
    media = await db_session.get(TgMedia, uuid.UUID(media_id))
    await db_session.refresh(media)
    assert media.file_ids[bot["id"]] == "PHOTO_FILE_ID"
    assert apis.methods("sendPhoto")[0]["multipart"] is True

    await _send(client, db_session, bot["id"], _start("/start"))
    second = apis.methods("sendPhoto")[1]
    assert second["photo"] == "PHOTO_FILE_ID" and second["has_spoiler"] is True

    in_use = await client.delete(f"/api/bots/media/{media_id}", headers=headers)
    assert in_use.status_code == 409


@pytest.mark.anyio
async def test_media_cache_chat_requires_admin_and_holds_the_uploads(client, db_session, owner, apis, monkeypatch) -> None:
    from app.instagram.storage import SupabaseStorage

    async def fake_upload(self, path, content, content_type):
        return None

    async def fake_bytes(media):
        return b"\xff\xd8\xffjpeg"

    monkeypatch.setattr(SupabaseStorage, "from_settings", classmethod(lambda cls: cls("https://x.supabase.co", "k")))
    monkeypatch.setattr(SupabaseStorage, "upload", fake_upload)
    monkeypatch.setattr(engine, "load_media_bytes", fake_bytes)
    headers = await _login(client)
    uploaded = await client.post(
        "/api/bots/media?filename=foto.jpg", headers={**headers, "content-type": "image/jpeg"}, content=b"\xff\xd8\xff" + b"0" * 100,
    )
    media_id = uploaded.json()["id"]
    bot, _ = await _setup(client, headers, _flow(welcome=[{"type": "photo", "media_ids": [media_id], "text": "Oi"}]))

    unknown = await client.patch(f"/api/bots/{bot['id']}", headers=headers, json={"cache_chat_id": GROUP_ID})
    assert unknown.status_code == 422
    await _admin_in_group(client, db_session, bot["id"])
    apis.member_status = "member"
    not_admin = await client.patch(f"/api/bots/{bot['id']}", headers=headers, json={"cache_chat_id": GROUP_ID})
    assert not_admin.status_code == 422 and "admin" in not_admin.json()["detail"]
    apis.member_status = "administrator"
    saved = await client.patch(f"/api/bots/{bot['id']}", headers=headers, json={"cache_chat_id": GROUP_ID})
    assert saved.status_code == 200 and saved.json()["cache_chat_id"] == GROUP_ID

    # The warm-up job uploads the funnel's files to the cache chat, silently.
    await engine.run_due_jobs(db_session)
    cached = apis.methods("sendPhoto")
    assert len(cached) == 1 and cached[0]["chat_id"] == str(GROUP_ID) and cached[0]["multipart"] is True
    assert cached[0]["disable_notification"] == "true"
    media = await db_session.get(TgMedia, uuid.UUID(media_id))
    await db_session.refresh(media)
    assert media.file_ids[bot["id"]] == "PHOTO_FILE_ID"

    # The lead gets the file by id: no new upload.
    await _send(client, db_session, bot["id"], _start())
    to_lead = apis.methods("sendPhoto")[-1]
    assert to_lead["chat_id"] == 555 and to_lead["photo"] == "PHOTO_FILE_ID"

    check = await client.post(f"/api/bots/{bot['id']}/cache/check", headers=headers)
    assert check.status_code == 200 and check.json() == {"ok": True, "cached": 1, "total": 1}
    cleared = await client.patch(f"/api/bots/{bot['id']}", headers=headers, json={"clear_cache_chat": True})
    assert cleared.json()["cache_chat_id"] is None


@pytest.mark.anyio
async def test_other_workspaces_cannot_touch_bots(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    # unauthenticated access is refused
    client.cookies.clear()
    assert (await client.get("/api/bots")).status_code in (401, 403)
    assert (await client.get(f"/api/bots/flows/{flow['id']}")).status_code in (401, 403)


def test_signature_window_and_format() -> None:
    from app.bots.smokepay import verify_signature

    settings = get_settings()
    original = settings.smokepay_webhook_secret
    settings.smokepay_webhook_secret = SecretStr("s")
    try:
        raw = b'{"a":1}'
        ts = 1_700_000_000
        sig = hmac.new(b"s", f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
        assert verify_signature(raw, f"t={ts},v1={sig}", now=ts + 10)
        assert not verify_signature(raw, f"t={ts},v1={sig}", now=ts + 400)  # replay window
        assert not verify_signature(raw + b" ", f"t={ts},v1={sig}", now=ts)  # body changed
        assert not verify_signature(raw, None, now=ts)
        assert not verify_signature(raw, "garbage", now=ts)
    finally:
        settings.smokepay_webhook_secret = original


def test_brl_formatting() -> None:
    assert engine.brl(Decimal("19.9")) == "R$ 19,90"
    assert engine.brl(Decimal("1234.5")) == "R$ 1.234,50"


@pytest.mark.anyio
async def test_groups_the_bot_joined_before_connecting_are_learned(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers)
    assert "channel_post" in apis.methods("setWebhook")[0]["allowed_updates"]

    # any message in a group, or a post in a channel, makes the bot learn it (Telegram never sent my_chat_member)
    group_message = {"message": {"message_id": 5, "date": 0, "chat": {"id": GROUP_ID, "type": "supergroup", "title": "VIP da Ana"},
                                 "from": {"id": 42, "first_name": "Ana"}, "text": "oi"}}
    assert (await _send(client, db_session, bot["id"], group_message)).status_code == 200
    channel_post = {"channel_post": {"message_id": 6, "date": 0, "chat": {"id": -1001112223334, "type": "channel", "title": "Backup"}, "text": "x"}}
    assert (await _send(client, db_session, bot["id"], channel_post)).status_code == 200
    groups = (await client.get("/api/bots/groups/list")).json()["groups"]
    assert {(g["title"], g["type"]) for g in groups} == {("VIP da Ana", "supergroup"), ("Backup", "channel")}
    assert len(apis.methods("getChatMember")) == 2
    await _send(client, db_session, bot["id"], {**group_message, "message": {**group_message["message"], "message_id": 7}})
    assert len(apis.methods("getChatMember")) == 2  # already known: no new lookup

    # or the owner types the @, the t.me link or the id
    linked = await client.post(f"/api/bots/{bot['id']}/groups/link", headers=headers, json={"chat": "https://t.me/canal_cache"})
    assert linked.status_code == 200, linked.text
    assert linked.json()["title"] == "Cache da Ana" and linked.json()["type"] == "channel"
    assert (await client.post(f"/api/bots/{bot['id']}/groups/link", headers=headers, json={"chat": "@naoexiste"})).status_code == 422
    assert (await client.post(f"/api/bots/{bot['id']}/groups/link", headers=headers, json={"chat": "lixo !!"})).status_code == 422
    apis.member_status = "left"
    gone = await client.post(f"/api/bots/{bot['id']}/groups/link", headers=headers, json={"chat": "@canal_cache"})
    assert gone.status_code == 422
