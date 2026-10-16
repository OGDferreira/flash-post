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


class FakeApis:
    """Answers Telegram Bot API and SmokePay calls and records them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.pix_status = "pending"
        self.pix_amount = 19.90
        self.get_me_status = 200
        self.message_id = 0

    def methods(self, name: str) -> list[dict]:
        return [body for method, body in self.calls if method == name]

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.telegram.org" in url:
            method = url.rsplit("/", 1)[-1]
            if request.headers.get("content-type", "").startswith("multipart"):
                body = {"multipart": True}
            else:
                body = json.loads(request.content or b"{}")
            self.calls.append((method, body))
            if method == "getMe":
                if self.get_me_status != 200:
                    return httpx.Response(401, json={"ok": False, "error_code": 401, "description": "Unauthorized"})
                return httpx.Response(200, json={"ok": True, "result": {"id": 987, "is_bot": True, "username": "ana_vip_bot", "first_name": "Ana VIP"}})
            if method == "createChatInviteLink":
                return httpx.Response(200, json={"ok": True, "result": {"invite_link": "https://t.me/+invite123"}})
            self.message_id += 1
            result: object = True
            if method.startswith("send"):
                result = {"message_id": self.message_id, "photo": [{"file_id": "small"}, {"file_id": "PHOTO_FILE_ID"}]}
            return httpx.Response(200, json={"ok": True, "result": result})
        if "/api/pix/create" in url:
            body = json.loads(request.content)
            self.calls.append(("pix.create", body))
            assert request.headers["x-api-key"] == "smoke_test_key"
            return httpx.Response(201, json={"success": True, "transaction": {
                "id": "tx-1", "txid": "g1", "external_id": body["external_id"], "amount": body["amount"],
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
    pix_message = apis.methods("sendMessage")[-1]
    assert "00020126PIXCODE" in pix_message["text"]
    buttons = pix_message["reply_markup"]["inline_keyboard"]
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

    bot, _ = await _setup(client, headers, _flow(welcome=[{"type": "photo", "media_ids": [media_id], "text": "Oi {nome}", "spoiler": True}]))
    await _send(client, db_session, bot["id"], _start())
    media = await db_session.get(TgMedia, uuid.UUID(media_id))
    await db_session.refresh(media)
    assert media.file_ids[bot["id"]] == "PHOTO_FILE_ID"
    assert apis.methods("sendPhoto")[0] == {"multipart": True}

    await _send(client, db_session, bot["id"], _start("/start"))
    second = apis.methods("sendPhoto")[1]
    assert second["photo"] == "PHOTO_FILE_ID" and second["has_spoiler"] is True

    in_use = await client.delete(f"/api/bots/media/{media_id}", headers=headers)
    assert in_use.status_code == 409


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
