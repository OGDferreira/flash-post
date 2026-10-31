"""SharkBot-style flow: welcome media + buttons, CTA, order bump, downsell, upsell."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import engine
from app.bots.richtext import sanitize
from app.models import TgJob, TgLead, TgOrder
from test_telegram_bots import (  # noqa: F401  (apis is a fixture)
    GROUP_ID,
    _flow,
    _login,
    _paid_event,
    _send,
    _setup,
    _signed,
    _start,
    _tap,
    apis,
)

PACK = {"type": "default", "text": "Seu conteúdo 💕", "link": {"label": "Abrir", "url": "https://example.com/c"}}


async def _media(client, headers, monkeypatch, name: str = "foto.jpg") -> str:
    from app.instagram.storage import SupabaseStorage

    async def fake_upload(self, path, content, content_type):
        return None

    async def fake_bytes(media):
        return b"\xff\xd8\xffjpeg"

    monkeypatch.setattr(SupabaseStorage, "from_settings", classmethod(lambda cls: cls("https://x.supabase.co", "k")))
    monkeypatch.setattr(SupabaseStorage, "upload", fake_upload)
    monkeypatch.setattr(engine, "load_media_bytes", fake_bytes)
    uploaded = await client.post(
        f"/api/bots/media?filename={name}", headers={**headers, "content-type": "image/jpeg"}, content=b"\xff\xd8\xff" + b"0" * 64
    )
    assert uploaded.status_code == 201, uploaded.text
    return uploaded.json()["id"]


async def _pay(client, db_session, order: TgOrder) -> None:
    raw, sig = _signed(_paid_event(order.id, amount=float(order.amount)))
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200


async def _run_jobs_now(db_session: AsyncSession) -> None:
    await db_session.execute(update(TgJob).where(TgJob.status == "pending").values(run_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await db_session.commit()
    await engine.run_due_jobs(db_session)


def test_sanitize_keeps_telegram_tags_and_escapes_the_rest() -> None:
    assert sanitize("<b>oi</b> <script>x</script> 1 < 2 & <3") == "<b>oi</b> x 1 &lt; 2 &amp; &lt;3"
    assert sanitize("<b><i>aberto") == "<b><i>aberto</i></b>"
    assert sanitize("<strong>a</strong><tg-spoiler>s</tg-spoiler>") == "<b>a</b><tg-spoiler>s</tg-spoiler>"
    assert sanitize('<a href="javascript:x">l</a><a href="https://t.me/x">t</a>') == 'l<a href="https://t.me/x">t</a>'


@pytest.mark.anyio
async def test_welcome_sends_media_first_then_message_with_colored_buttons(client, db_session, owner, apis, monkeypatch) -> None:
    headers = await _login(client)
    photos = [await _media(client, headers, monkeypatch, f"f{i}.jpg") for i in range(2)]
    flow = _flow(
        welcome=[],
        offer={"text": "{saudacao}, <b>{nome}</b>! Sou {bot.nome}", "media_ids": photos,
               "redirect_buttons": [{"label": "Instagram", "url": "https://instagram.com/ana"}]},
        support_username="@ana_suporte",
    )
    flow["plans"][0]["button_style"] = "success"
    bot, _ = await _setup(client, headers, flow)
    await _send(client, db_session, bot["id"], _start())

    # two photos go first as an album, then the message carrying the buttons
    assert len(apis.methods("sendMediaGroup")) == 1
    message = apis.methods("sendMessage")[-1]
    assert message["text"].startswith(("Bom dia", "Boa tarde", "Boa noite"))
    assert "<b>Lucas</b>! Sou Ana VIP" in message["text"]
    rows = message["reply_markup"]["inline_keyboard"]
    assert rows[0][0] == {"text": "VIP Mensal · R$ 19,90", "callback_data": "plan:vip", "style": "success"}
    assert rows[1][0] == {"text": "Instagram", "url": "https://instagram.com/ana"}
    assert rows[2][0]["url"] == "https://t.me/ana_suporte"


@pytest.mark.anyio
async def test_cta_and_secondary_message(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(
        welcome=[], offer={"text": "Oi {nome}", "secondary_enabled": True, "secondary_text": "Toque abaixo",
                           "cta_enabled": True, "cta_label": "Ver planos", "plans_text": "Planos:"},
    ))
    await _send(client, db_session, bot["id"], _start())
    first, second = apis.methods("sendMessage")[-2:]
    assert first["text"] == "Oi Lucas" and "reply_markup" not in first
    assert second["text"] == "Toque abaixo"
    assert second["reply_markup"]["inline_keyboard"] == [[{"text": "Ver planos", "callback_data": "plans", "style": "success"}]]
    await _send(client, db_session, bot["id"], _tap("plans"))
    plans = apis.methods("sendMessage")[-1]
    assert plans["text"] == "Planos:" and plans["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "plan:vip"


@pytest.mark.anyio
async def test_order_bump_adds_to_a_single_pix_and_delivers_both(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    flow = _flow(welcome=[], order_bump={"name": "Pack extra", "price": "5.00", "delivery": PACK})
    flow["plans"][0]["delivery"] = {"type": "default", "text": "Acesso VIP"}
    bot, _ = await _setup(client, headers, flow)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    question = apis.methods("sendMessage")[-1]
    assert "Pack extra" in question["text"] and "+R$ 5,00" in question["text"]
    assert question["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "bump:y:vip"
    assert not apis.methods("pix.create")

    await _send(client, db_session, bot["id"], _tap("bump:y:vip"))
    created = apis.methods("pix.create")[0]
    assert created["amount"] == 24.9
    order = await db_session.scalar(select(TgOrder))
    assert order.offer_name == "VIP Mensal + Pack extra"
    apis.pix_amount = 24.90
    await _pay(client, db_session, order)
    texts = [m["text"] for m in apis.methods("sendMessage")]
    assert "Acesso VIP" in texts and "Seu conteúdo 💕" in texts


@pytest.mark.anyio
async def test_declining_the_bump_charges_only_the_plan(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[], order_bump={"name": "Extra", "price": "5.00", "delivery": PACK}))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("bump:n:vip"))
    assert apis.methods("pix.create")[0]["amount"] == 19.9


@pytest.mark.anyio
async def test_downsell_offers_discount_and_stops_after_payment(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[], downsells=[
        {"delay_minutes": 10, "text": "Última chance: {desconto} off!", "discount_type": "percent", "discount_value": "50"},
        {"delay_minutes": 20, "text": "Agora vai", "discount_type": "fixed", "discount_value": "5"},
    ]))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    jobs = list(await db_session.scalars(select(TgJob).where(TgJob.kind == "send_downsell").order_by(TgJob.run_at)))
    assert len(jobs) == 2
    # tapping the plan again does not queue a second series
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert len(list(await db_session.scalars(select(TgJob).where(TgJob.kind == "send_downsell")))) == 2

    await db_session.execute(update(TgJob).where(TgJob.id == jobs[0].id).values(run_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await db_session.commit()
    await engine.run_due_jobs(db_session)
    offer = apis.methods("sendMessage")[-1]
    assert offer["text"] == "Última chance: 50% off!"
    button = offer["reply_markup"]["inline_keyboard"][0][0]
    assert button["callback_data"] == "dplan:0:vip" and "R$ 9,95" in button["text"]

    await _send(client, db_session, bot["id"], _tap("dplan:0:vip"))
    await db_session.commit()  # drop the session's old read snapshot
    discounted = await db_session.scalar(select(TgOrder).where(TgOrder.kind == "downsell"))
    assert discounted.amount == engine.Decimal("9.95") and apis.methods("pix.create")[-1]["amount"] == 9.95
    apis.pix_amount = 9.95
    await _pay(client, db_session, discounted)
    await db_session.commit()
    second = await db_session.get(TgJob, jobs[1].id)
    await db_session.refresh(second)
    assert second.status == "cancelled"


@pytest.mark.anyio
async def test_upsell_after_payment_accept_and_decline_move_through_the_sequence(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(
        welcome=[],
        plans=[{"id": "vip", "name": "VIP", "price": "19.90", "delivery": {"type": "default", "text": "VIP ok"}}],
        upsells=[
            {"name": "Chamada de vídeo", "price": "49.90", "text": "Quer uma chamada?", "delivery": {"type": "default", "text": "Chamada agendada"}},
            {"name": "Pack fotos", "price": "9.90", "delay_minutes": 5, "text": "Pack?", "delivery": PACK},
        ],
    ))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    order = await db_session.scalar(select(TgOrder))
    await _pay(client, db_session, order)
    await _run_jobs_now(db_session)
    upsell = apis.methods("sendMessage")[-1]
    assert upsell["text"] == "Quer uma chamada?"
    accept, decline = (row[0] for row in upsell["reply_markup"]["inline_keyboard"])
    chain = order.id.hex
    assert accept["callback_data"] == f"up:0:{chain}" and accept["style"] == "success" and "R$ 49,90" in accept["text"]
    assert decline["callback_data"] == f"upn:0:{chain}"

    # buying the upsell delivers it and moves to step 2
    await _send(client, db_session, bot["id"], _tap(f"up:0:{chain}"))
    await db_session.commit()  # drop the session's old read snapshot
    up_order = await db_session.scalar(select(TgOrder).where(TgOrder.kind == "upsell"))
    assert apis.methods("pix.create")[-1]["amount"] == 49.9
    apis.pix_amount = 49.90
    await _pay(client, db_session, up_order)
    assert "Chamada agendada" in [m["text"] for m in apis.methods("sendMessage")]
    # no wait at all: the next step goes out with the payment, even with a delay set
    assert apis.methods("sendMessage")[-1]["text"] == "Pack?"
    # an upsell follows every payment, so no "payment approved" message is sent
    assert not any(m["text"].startswith("Pagamento aprovado") for m in apis.methods("sendMessage"))
    # declining the last step just ends the series (double tap is harmless)
    await _send(client, db_session, bot["id"], _tap(f"upn:1:{chain}"))
    await _send(client, db_session, bot["id"], _tap(f"upn:1:{chain}"))
    await db_session.commit()
    assert not list(await db_session.scalars(select(TgJob).where(TgJob.kind == "send_upsell", TgJob.status == "pending")))


@pytest.mark.anyio
async def test_flow_summary_and_validation_of_new_sections(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    summary = (await client.get(f"/api/bots/flows/{flow['id']}/summary")).json()
    assert summary == {"leads": 1, "vips": 0, "revenue": "0.00"}

    bad = _flow(downsells=[{"text": "x", "plan_ids": ["nao-existe"]}])
    response = await client.put(f"/api/bots/flows/{flow['id']}", headers=headers, json={"name": "x", "definition": bad})
    assert response.status_code == 422 and "downsell" in response.json()["detail"]
    custom = _flow()
    custom["plans"][0]["bump_mode"] = "custom"
    response = await client.put(f"/api/bots/flows/{flow['id']}", headers=headers, json={"name": "x", "definition": custom})
    assert response.status_code == 422 and "order bump" in response.json()["detail"]

    # phase 1 single offer media is folded into the media list
    old = _flow(offer={"text": "Oi", "media_id": str(uuid.uuid4())})
    from app.bots.flow_schema import FlowDefinition

    assert len(FlowDefinition.model_validate(old).offer.media_ids) == 1
    assert GROUP_ID  # shared fixture constant stays importable
    assert (await db_session.scalar(select(TgLead))).stage == "offered"


@pytest.mark.anyio
async def test_upsell_only_delivery_hidden_decline_and_default_delivery(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(
        welcome=[],
        plans=[{"id": "vip", "name": "VIP", "price": "19.90", "delivery": {"type": "upsell"}}],
        default_delivery={"type": "default", "text": "Entrega padrão"},
        upsells=[
            {"name": "Extra 1", "price": "9.90", "text": "Oferta 1", "hide_decline": True},  # default delivery
            {"name": "Extra 2", "price": "5.00", "delay_minutes": 5, "text": "Oferta 2",
             "delivery": {"type": "default", "text": "Extra 2 ok"}},
        ],
    ))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    order = await db_session.scalar(select(TgOrder))
    await _pay(client, db_session, order)
    # the "upsell" delivery hands over nothing, it only starts the sequence
    assert "Entrega padrão" not in [m["text"] for m in apis.methods("sendMessage")]
    await _run_jobs_now(db_session)
    first = apis.methods("sendMessage")[-1]
    assert first["text"] == "Oferta 1" and len(first["reply_markup"]["inline_keyboard"]) == 1  # no "no" button
    # hidden decline: nothing else is sent until this step is paid (one step per payment)
    await _run_jobs_now(db_session)
    assert "Oferta 2" not in [m["text"] for m in apis.methods("sendMessage")]

    # buying step 1 uses the flow's default delivery and only then releases step 2
    await _send(client, db_session, bot["id"], _tap(f"up:0:{order.id.hex}"))
    await db_session.commit()
    up = await db_session.scalar(select(TgOrder).where(TgOrder.kind == "upsell"))
    apis.pix_amount = 9.90
    await _pay(client, db_session, up)
    assert "Entrega padrão" in [m["text"] for m in apis.methods("sendMessage")]
    await _run_jobs_now(db_session)
    assert apis.methods("sendMessage")[-1]["text"] == "Oferta 2"


@pytest.mark.anyio
async def test_delivery_can_skip_the_upsell_sequence(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(
        welcome=[],
        plans=[{"id": "vip", "name": "VIP", "price": "19.90", "delivery": {"type": "default", "text": "ok", "start_upsell": False}}],
        upsells=[{"name": "Extra", "price": "9.90", "text": "Oferta", "delivery": PACK}],
    ))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await _pay(client, db_session, await db_session.scalar(select(TgOrder)))
    await db_session.commit()
    assert not list(await db_session.scalars(select(TgJob).where(TgJob.kind == "send_upsell")))


@pytest.mark.anyio
async def test_downsell_audience_and_custom_offer(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(
        welcome=[],
        default_delivery={"type": "default", "text": "Entrega padrão"},
        downsell_audience=["no_pix"],
        downsells=[{"delay_minutes": 10, "text": "Só pra você",
                    "custom_offer": {"name": "Semana VIP", "price": "7.00", "duration_days": 7}}],
    ))
    # started, never generated a PIX: gets the custom offer
    await _send(client, db_session, bot["id"], _start())
    await _run_jobs_now(db_session)
    offer = apis.methods("sendMessage")[-1]
    assert offer["text"] == "Só pra você"
    assert offer["reply_markup"]["inline_keyboard"] == [[{"text": "🔥 Semana VIP · R$ 7,00", "callback_data": "nplan:0:@", "style": "success"}]]
    await _send(client, db_session, bot["id"], _tap("nplan:0:@"))
    assert apis.methods("pix.create")[-1]["amount"] == 7.0
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.kind == "downsell" and order.offer_name == "Semana VIP"
    apis.pix_amount = 7.00
    await _pay(client, db_session, order)
    assert "Entrega padrão" in [m["text"] for m in apis.methods("sendMessage")]


@pytest.mark.anyio
async def test_no_pix_audience_skips_leads_who_generated_a_pix(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[], downsell_audience=["no_pix"], downsells=[{"text": "Volta!"}]))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))  # generated a PIX
    before = len(apis.methods("sendMessage"))
    await _run_jobs_now(db_session)
    assert "Volta!" not in [m["text"] for m in apis.methods("sendMessage")[before:]]


def test_old_downsell_audience_becomes_two_sequences() -> None:
    from app.bots.flow_schema import FlowDefinition

    steps = [{"text": "Volta!"}]
    both = FlowDefinition.model_validate(_flow(downsell_trigger="start", downsells=steps))
    assert len(both.downsells) == 1 and len(both.downsells_no_pix) == 1
    only_pix = FlowDefinition.model_validate(_flow(downsells=steps))
    assert len(only_pix.downsells) == 1 and only_pix.downsells_no_pix == []
    only_start = FlowDefinition.model_validate(_flow(downsell_audience=["no_pix"], downsells=steps))
    assert only_start.downsells == [] and len(only_start.downsells_no_pix) == 1
    # once split, the saved shape keeps each sequence as it is
    again = FlowDefinition.model_validate(only_start.model_dump(mode="json"))
    assert again.downsells == [] and len(again.downsells_no_pix) == 1 and again.downsell_audience is None


@pytest.mark.anyio
async def test_pix_and_no_pix_downsells_are_separate_sequences(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(
        welcome=[],
        downsells_no_pix=[{"delay_minutes": 5, "text": "Nem gerou o Pix?", "discount_value": "20"}],
        downsells=[{"delay_minutes": 10, "text": "Seu Pix está esperando", "discount_value": "30"}],
    ))
    await _send(client, db_session, bot["id"], _start())
    await db_session.commit()
    no_pix = list(await db_session.scalars(select(TgJob).where(TgJob.kind == "send_downsell_np")))
    assert len(no_pix) == 1 and not list(await db_session.scalars(select(TgJob).where(TgJob.kind == "send_downsell")))
    await _run_jobs_now(db_session)
    offer = apis.methods("sendMessage")[-1]
    assert offer["text"] == "Nem gerou o Pix?"
    assert offer["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "nplan:0:vip"

    # buying from the "não gerado" offer is the first PIX: that sequence ends, the "gerado" one starts
    await _send(client, db_session, bot["id"], _tap("nplan:0:vip"))
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    assert order.kind == "downsell" and order.offer_id == "vip-n0" and order.amount == engine.Decimal("15.92")
    pix_jobs = list(await db_session.scalars(select(TgJob).where(TgJob.kind == "send_downsell", TgJob.status == "pending")))
    assert len(pix_jobs) == 1
    await _run_jobs_now(db_session)
    offer = apis.methods("sendMessage")[-1]
    assert offer["text"] == "Seu Pix está esperando"
    assert offer["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "dplan:0:vip"


@pytest.mark.anyio
async def test_previews_button_sends_media_that_delete_themselves(client, db_session, owner, apis, monkeypatch) -> None:
    headers = await _login(client)
    photos = [await _media(client, headers, monkeypatch, f"p{i}.jpg") for i in range(2)]
    bot, _ = await _setup(client, headers, _flow(
        welcome=[], previews={"enabled": True, "media_ids": photos, "delete_after_seconds": 120, "label": "Ver prévias"},
    ))
    await _send(client, db_session, bot["id"], _start())
    rows = apis.methods("sendMessage")[-1]["reply_markup"]["inline_keyboard"]
    assert [{"text": "Ver prévias", "callback_data": "prev", "style": "primary"}] in rows

    await _send(client, db_session, bot["id"], _tap("prev"))
    album = apis.methods("sendMediaGroup")[-1]
    assert album["protect_content"] in (True, "true")
    await db_session.commit()
    job = await db_session.scalar(select(TgJob).where(TgJob.kind == "delete_messages"))
    assert job is not None and job.status == "pending" and job.payload["chat_id"] == 555
    # the tap takes the button off that message (the other buttons stay)
    edited = apis.methods("editMessageReplyMarkup")[-1]
    assert edited["message_id"] == 9 and all(
        item.get("callback_data") != "prev" for row in edited["reply_markup"]["inline_keyboard"] for item in row
    )
    # a second tap (an old message) sends nothing new
    await _send(client, db_session, bot["id"], _tap("prev"))
    assert len(apis.methods("sendMediaGroup")) == 1
    await _run_jobs_now(db_session)
    assert apis.methods("deleteMessages")[-1]["chat_id"] == 555
    # ... not even after they were deleted, and later offers come without the button
    await _send(client, db_session, bot["id"], _tap("prev"))
    assert len(apis.methods("sendMediaGroup")) == 1
    await _send(client, db_session, bot["id"], _start())
    rows = apis.methods("sendMessage")[-1]["reply_markup"]["inline_keyboard"]
    assert all(item.get("callback_data") != "prev" for row in rows for item in row)


@pytest.mark.anyio
async def test_short_previews_are_deleted_on_time(client, db_session, owner, apis, monkeypatch) -> None:
    headers = await _login(client)
    photos = [await _media(client, headers, monkeypatch, "p.jpg")]
    bot, _ = await _setup(client, headers, _flow(welcome=[], previews={"enabled": True, "media_ids": photos, "delete_after_seconds": 5}))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("prev"))  # the update stays with them and deletes at 5 s
    assert apis.methods("deleteMessages"), "deleted without waiting for the worker tick"


def test_previews_need_media() -> None:
    from pydantic import ValidationError

    from app.bots.flow_schema import FlowDefinition

    with pytest.raises(ValidationError):
        FlowDefinition.model_validate(_flow(previews={"enabled": True}))


@pytest.mark.anyio
async def test_reconciliation_asks_newest_first_in_parallel_and_approves_paid(client, db_session, owner, apis, monkeypatch) -> None:
    import asyncio

    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[]))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    order = await db_session.scalar(select(TgOrder))
    order.created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    running, peak, asked = 0, 0, []

    async def fake_paid(target: TgOrder):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        asked.append(target.id)
        return (target.amount, "Fulano", None, None) if target.id == order.id else None

    monkeypatch.setattr(engine, "_paid_charge", fake_paid)
    assert await engine.reconcile_pending_orders(db_session) == 1
    await db_session.refresh(order)
    assert asked == [order.id] and order.status == "paid"


@pytest.mark.anyio
async def test_pix_steps_layout_sends_instructions_copy_box_and_buttons(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    flow = _flow(welcome=[])
    flow["payment"] = {"layout": "steps"}
    bot, _ = await _setup(client, headers, flow)
    await _send(client, db_session, bot["id"], _start())
    before = len(apis.methods("sendMessage"))
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    steps, code, last = apis.methods("sendMessage")[before:][-3:]
    assert "Como realizar o pagamento" in steps["text"]
    assert code["text"].startswith("Copie o código abaixo:") and '<pre><code class="language-copy">' in code["text"]
    assert not apis.methods("sendPhoto")
    rows = last["reply_markup"]["inline_keyboard"]
    assert rows[0][0]["callback_data"].startswith("chk:") and "copy_text" in rows[1][0]
