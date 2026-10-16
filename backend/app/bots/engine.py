"""Runs a lead through the flow: /start -> (+18) -> welcome -> offer -> PIX -> delivery.

Telegram updates and payment webhooks only *record* intent and schedule
``TgJob`` rows; messages that must wait (welcome delays, PIX expiry, the end of
a subscription) are executed by ``run_due_jobs`` from the worker. Every state
change is a conditional UPDATE so a redelivered update, a double tap or a
webhook racing the "Já paguei" button never pays or delivers twice.
"""

import base64
import html
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import smokepay
from app.bots.flow_schema import Block, Delivery, FlowDefinition, Plan
from app.bots.telegram import InputFile, TelegramClient, TelegramError
from app.core.config import get_settings
from app.core.crypto import decrypt_value
from app.models import (
    TgBot,
    TgFlow,
    TgGroup,
    TgJob,
    TgLead,
    TgMedia,
    TgOrder,
    TgSubscription,
)

logger = logging.getLogger(__name__)

ORDER_PREFIX = "tgo_"
INVITE_LINK_TTL = timedelta(hours=24)
JOB_MAX_ATTEMPTS = 5
_SEND = {
    "photo": ("sendPhoto", "photo"),
    "video": ("sendVideo", "video"),
    "voice": ("sendVoice", "voice"),
    "video_note": ("sendVideoNote", "video_note"),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def brl(value: Decimal) -> str:
    whole, cents = f"{value:.2f}".split(".")
    return f"R$ {int(whole):,}".replace(",", ".") + f",{cents}"


def render(text: str | None, lead: TgLead, plan: str | None = None, amount: Decimal | None = None) -> str:
    """Fill variables; lead data is escaped because messages use HTML parse mode."""
    if not text:
        return ""
    values = {
        "{nome}": html.escape(lead.first_name or "você"),
        "{username}": html.escape(f"@{lead.username}" if lead.username else (lead.first_name or "")),
        "{plano}": html.escape(plan or ""),
        "{valor}": brl(amount) if amount is not None else "",
    }
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def telegram(bot: TgBot) -> TelegramClient:
    return TelegramClient(decrypt_value(bot.encrypted_token))


async def load_flow(db: AsyncSession, bot: TgBot) -> FlowDefinition | None:
    if bot.flow_id is None:
        return None
    flow = await db.get(TgFlow, bot.flow_id)
    return FlowDefinition.model_validate(flow.definition) if flow else None


# ---------------------------------------------------------------- media


async def load_media_bytes(media: TgMedia) -> bytes:
    """Download an uploaded file from Supabase Storage (patched in tests)."""
    from app.bots import http
    from app.instagram.storage import SupabaseStorage

    url = await SupabaseStorage.from_settings().create_signed_url(media.storage_path)
    async with http.client(120.0) as session:
        response = await session.get(url)
        response.raise_for_status()
        return response.content


async def _media_rows(db: AsyncSession, bot: TgBot, ids: list[uuid.UUID]) -> list[TgMedia]:
    if not ids:
        return []
    rows = {
        m.id: m
        for m in await db.scalars(
            select(TgMedia).where(TgMedia.id.in_(ids), TgMedia.workspace_id == bot.workspace_id)
        )
    }
    return [rows[i] for i in ids if i in rows]


async def _source(bot: TgBot, media: TgMedia) -> str | InputFile:
    cached = (media.file_ids or {}).get(str(bot.id))
    if cached:
        return cached
    return InputFile(media.file_name, await load_media_bytes(media), media.content_type)


def _remember_file_id(bot: TgBot, media: TgMedia, message: dict, field: str) -> None:
    node = message.get(field)
    if isinstance(node, list):  # photos come in several sizes; keep the largest
        node = node[-1] if node else None
    file_id = node.get("file_id") if isinstance(node, dict) else None
    if file_id:
        media.file_ids = {**(media.file_ids or {}), str(bot.id): file_id}


async def send_media_message(
    db: AsyncSession,
    tg: TelegramClient,
    bot: TgBot,
    chat_id: int,
    kind: str,
    media: TgMedia,
    caption: str | None = None,
    reply_markup: dict | None = None,
    spoiler: bool = False,
    protect: bool = False,
) -> None:
    if kind not in _SEND:  # a "photo/video" block follows the uploaded file
        kind = "video" if media.kind == "video" else "photo"
    method, field = _SEND[kind]
    message = await tg.send_media(
        method,
        field,
        chat_id,
        await _source(bot, media),
        caption=caption,
        reply_markup=reply_markup,
        spoiler=spoiler and kind in ("photo", "video"),
        protect=protect,
    )
    _remember_file_id(bot, media, message, field)


async def send_album(
    db: AsyncSession, tg: TelegramClient, bot: TgBot, chat_id: int, medias: list[TgMedia],
    caption: str | None, spoiler: bool = False, protect: bool = False,
) -> None:
    items, files = [], {}
    for index, media in enumerate(medias):
        source = await _source(bot, media)
        kind = "video" if media.kind == "video" else "photo"
        if isinstance(source, InputFile):
            files[f"file{index}"] = source
            source = f"attach://file{index}"
        item = {"type": kind, "media": source}
        if spoiler:
            item["has_spoiler"] = True
        if index == 0 and caption:
            item.update({"caption": caption, "parse_mode": "HTML"})
        items.append(item)
    messages = await tg.send_media_group(chat_id, items, files, protect=protect)
    for media, message in zip(medias, messages or []):
        _remember_file_id(bot, media, message, "video" if media.kind == "video" else "photo")


async def send_block(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, block: Block) -> None:
    caption = render(block.text, lead)
    if block.type == "text":
        await tg.send_chat_action(lead.chat_id, "typing")
        await tg.send_message(lead.chat_id, caption)
        return
    medias = await _media_rows(db, bot, block.media_ids)
    if not medias:
        if caption:
            await tg.send_message(lead.chat_id, caption)
        return
    if block.type == "album":
        await send_album(db, tg, bot, lead.chat_id, medias, caption, spoiler=block.spoiler)
    else:
        if block.type == "voice":
            await tg.send_chat_action(lead.chat_id, "record_voice")
        await send_media_message(db, tg, bot, lead.chat_id, block.type, medias[0], caption or None, spoiler=block.spoiler)


# ---------------------------------------------------------------- jobs


async def schedule(
    db: AsyncSession, bot: TgBot, kind: str, run_at: datetime, key: str,
    lead: TgLead | None = None, payload: dict | None = None,
) -> None:
    exists = await db.scalar(select(TgJob.id).where(TgJob.idempotency_key == key))
    if exists:
        return
    db.add(
        TgJob(
            workspace_id=bot.workspace_id,
            bot_id=bot.id,
            lead_id=lead.id if lead else None,
            kind=kind,
            payload=payload or {},
            run_at=run_at,
            idempotency_key=key[:200],
        )
    )


async def cancel_lead_jobs(db: AsyncSession, lead: TgLead, kinds: tuple[str, ...]) -> None:
    await db.execute(
        update(TgJob)
        .where(TgJob.lead_id == lead.id, TgJob.status == "pending", TgJob.kind.in_(kinds))
        .values(status="cancelled")
    )


async def start_welcome(db: AsyncSession, bot: TgBot, lead: TgLead, flow: FlowDefinition) -> None:
    """Queue the welcome blocks with their delays, then the offer."""
    await cancel_lead_jobs(db, lead, ("send_block", "send_offer"))
    run = utcnow()
    nonce = secrets.token_hex(4)
    for index, block in enumerate(flow.welcome):
        run += timedelta(seconds=block.delay_seconds, microseconds=index)
        await schedule(db, bot, "send_block", run, f"welcome:{lead.id}:{nonce}:{index}", lead, {"index": index})
    # Microsecond offset keeps the offer after the last block yet due right away when there are no delays.
    run += timedelta(microseconds=len(flow.welcome) + 1)
    await schedule(db, bot, "send_offer", run, f"offer:{lead.id}:{nonce}", lead)
    lead.stage = "welcome"


def plans_keyboard(flow: FlowDefinition) -> dict:
    rows = []
    for plan in flow.plans:
        label = plan.button_text or f"{plan.name} · {brl(plan.price)}"
        rows.append([{"text": label, "callback_data": f"plan:{plan.id}"}])
    return {"inline_keyboard": rows}


async def send_offer(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition) -> None:
    if not flow.plans:
        return
    text = render(flow.offer.text, lead)
    keyboard = plans_keyboard(flow)
    media = (await _media_rows(db, bot, [flow.offer.media_id]))[:1] if flow.offer.media_id else []
    if media:
        await send_media_message(db, tg, bot, lead.chat_id, media[0].kind, media[0], text, keyboard)
    else:
        await tg.send_message(lead.chat_id, text, keyboard)
    lead.stage = "offered"


async def _claim(db: AsyncSession, job: TgJob) -> bool:
    result = await db.execute(
        update(TgJob).where(TgJob.id == job.id, TgJob.status == "pending").values(status="running")
    )
    await db.commit()
    return result.rowcount == 1


async def run_job(db: AsyncSession, job: TgJob) -> None:
    bot = await db.get(TgBot, job.bot_id)
    if bot is None or not bot.is_active:
        return
    lead = await db.get(TgLead, job.lead_id) if job.lead_id else None
    if lead is not None and lead.blocked_bot:
        return
    tg = telegram(bot)
    if job.kind in ("send_block", "send_offer"):
        flow = await load_flow(db, bot)
        if flow is None or lead is None:
            return
        if job.kind == "send_block":
            index = int(job.payload.get("index", -1))
            if 0 <= index < len(flow.welcome):
                await send_block(db, tg, bot, lead, flow.welcome[index])
        else:
            await send_offer(db, tg, bot, lead, flow)
    elif job.kind == "expire_order":
        await expire_order(db, tg, bot, uuid.UUID(job.payload["order_id"]))
    elif job.kind == "end_subscription":
        await end_subscription(db, tg, bot, uuid.UUID(job.payload["subscription_id"]))


async def run_due_jobs(db: AsyncSession, limit: int = 50, lead_id: uuid.UUID | None = None) -> int:
    query = (
        select(TgJob)
        .where(TgJob.status == "pending", TgJob.run_at <= utcnow())
        .order_by(TgJob.run_at, TgJob.created_at)
        .limit(limit)
    )
    if lead_id is not None:
        query = query.where(TgJob.lead_id == lead_id)
    jobs = list(await db.scalars(query))
    done = 0
    for job in jobs:
        if not await _claim(db, job):
            continue
        try:
            await run_job(db, job)
            job.status = "done"
            done += 1
        except TelegramError as exc:
            await _job_failed(db, job, exc)
        except Exception as exc:  # keep the worker alive; the job retries
            logger.exception("Bot job %s failed", job.kind)
            await _job_failed(db, job, exc)
        await db.commit()
    return done


async def _job_failed(db: AsyncSession, job: TgJob, exc: Exception) -> None:
    job.attempts += 1
    job.last_error = str(exc)[:500]
    if isinstance(exc, TelegramError) and exc.blocked and job.lead_id:
        lead = await db.get(TgLead, job.lead_id)
        if lead:
            lead.blocked_bot = True
        job.status = "failed"
    elif job.attempts >= JOB_MAX_ATTEMPTS:
        job.status = "failed"
    else:
        job.status = "pending"
        job.run_at = utcnow() + timedelta(seconds=15 * 2 ** job.attempts)


# ---------------------------------------------------------------- updates


async def upsert_lead(db: AsyncSession, bot: TgBot, user: dict, chat_id: int) -> TgLead:
    lead = await db.scalar(select(TgLead).where(TgLead.bot_id == bot.id, TgLead.tg_user_id == user["id"]))
    if lead is None:
        lead = TgLead(workspace_id=bot.workspace_id, bot_id=bot.id, flow_id=bot.flow_id, tg_user_id=user["id"], chat_id=chat_id)
        db.add(lead)
    lead.first_name = (user.get("first_name") or "")[:255] or None
    lead.username = (user.get("username") or "")[:64] or None
    lead.chat_id = chat_id
    lead.blocked_bot = False
    lead.last_seen_at = utcnow()
    await db.flush()
    return lead


async def handle_update(db: AsyncSession, bot: TgBot, update_data: dict) -> uuid.UUID | None:
    """Apply one Telegram update. Returns the lead whose jobs should run right away."""
    if "my_chat_member" in update_data:
        await _handle_membership(db, bot, update_data["my_chat_member"])
        return None
    flow = await load_flow(db, bot)
    if "message" in update_data:
        message = update_data["message"]
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        text = (message.get("text") or "").strip()
        if chat.get("type") != "private" or not sender or not text.startswith("/start"):
            return None
        lead = await upsert_lead(db, bot, sender, chat["id"])
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and not lead.source:
            lead.source = parts[1][:64]
        if flow is None:
            return None
        if flow.age_gate.enabled and lead.age_confirmed_at is None:
            await telegram(bot).send_message(
                lead.chat_id,
                render(flow.age_gate.text, lead),
                {"inline_keyboard": [[{"text": flow.age_gate.button, "callback_data": "age:ok"}]]},
            )
            lead.stage = "age_gate"
            return None
        await start_welcome(db, bot, lead, flow)
        return lead.id
    if "callback_query" in update_data:
        return await _handle_callback(db, bot, update_data["callback_query"], flow)
    return None


async def _handle_callback(db: AsyncSession, bot: TgBot, query: dict, flow: FlowDefinition | None) -> uuid.UUID | None:
    tg = telegram(bot)
    data = query.get("data") or ""
    sender = query.get("from") or {}
    chat_id = ((query.get("message") or {}).get("chat") or {}).get("id") or sender.get("id")
    if not sender or flow is None:
        await tg.answer_callback(query["id"])
        return None
    lead = await upsert_lead(db, bot, sender, chat_id)
    if data == "age:ok":
        await tg.answer_callback(query["id"])
        if lead.age_confirmed_at is None:
            lead.age_confirmed_at = utcnow()
            await start_welcome(db, bot, lead, flow)
            return lead.id
        return None
    if data.startswith("plan:"):
        plan = flow.plan(data[5:])
        if plan is None:
            await tg.answer_callback(query["id"], "Este plano não está mais disponível.")
            return None
        await tg.answer_callback(query["id"], "Gerando seu Pix…")
        await create_order(db, tg, bot, lead, flow, plan)
        return None
    if data.startswith("chk:"):
        try:
            order_id = uuid.UUID(data[4:])
        except ValueError:
            await tg.answer_callback(query["id"])
            return None
        order = await db.get(TgOrder, order_id)
        if order is None or order.lead_id != lead.id:
            await tg.answer_callback(query["id"])
            return None
        if order.status == "pending":
            await check_order(db, order)
        if order.status == "paid":
            await tg.answer_callback(query["id"], "Pagamento confirmado! ✅")
        else:
            await tg.answer_callback(query["id"], flow.payment.pending_text, alert=True)
        return None
    await tg.answer_callback(query["id"])
    return None


async def _handle_membership(db: AsyncSession, bot: TgBot, event: dict) -> None:
    chat = event.get("chat") or {}
    if chat.get("type") not in ("group", "supergroup", "channel"):
        return
    member = event.get("new_chat_member") or {}
    status = member.get("status")
    group = await db.scalar(select(TgGroup).where(TgGroup.bot_id == bot.id, TgGroup.chat_id == chat["id"]))
    if status in ("left", "kicked"):
        if group is not None:
            await db.delete(group)
        return
    if group is None:
        group = TgGroup(workspace_id=bot.workspace_id, bot_id=bot.id, chat_id=chat["id"], title="", chat_type=chat["type"])
        db.add(group)
    group.title = (chat.get("title") or str(chat["id"]))[:255]
    group.chat_type = chat["type"]
    group.can_invite = status == "creator" or (status == "administrator" and bool(member.get("can_invite_users")))


# ---------------------------------------------------------------- payments


def payment_webhook_url() -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/bots/pay/smokepay"


async def create_order(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition, plan: Plan) -> TgOrder | None:
    now = utcnow()
    order = await db.scalar(
        select(TgOrder).where(
            TgOrder.lead_id == lead.id, TgOrder.offer_id == plan.id, TgOrder.status == "pending",
            TgOrder.expires_at > now,
        ).order_by(TgOrder.created_at.desc())
    )
    if order is None:
        order = TgOrder(
            workspace_id=bot.workspace_id, bot_id=bot.id, lead_id=lead.id, flow_id=bot.flow_id,
            offer_id=plan.id, offer_name=plan.name, offer_snapshot=plan.model_dump(mode="json"),
            amount=plan.price, expires_at=now + timedelta(minutes=flow.payment.expiration_minutes),
        )
        db.add(order)
        await db.flush()
        try:
            charge = await smokepay.create_pix(
                amount=plan.price,
                external_id=f"{ORDER_PREFIX}{order.id}",
                description=f"{bot.name} · {plan.name}",
                webhook_url=payment_webhook_url(),
                expiration_seconds=flow.payment.expiration_minutes * 60,
            )
        except smokepay.SmokepayError as exc:
            order.status = "failed"
            bot.last_error = f"Gateway: {exc}"[:500]
            await db.commit()
            await tg.send_message(lead.chat_id, "Não consegui gerar o Pix agora. Tente de novo em alguns instantes.")
            await notify_owners(db, bot, "⚠️ Falha ao gerar Pix", f"@{bot.username}: {str(exc)[:120]}", "bot-gateway")
            return None
        order.gateway_transaction_id = charge.transaction_id or None
        order.gateway_fee = charge.fee
        order.net_amount = charge.net_amount
        order.pix_copy_paste = charge.copy_paste
        await schedule(db, bot, "expire_order", order.expires_at, f"expire:{order.id}", lead, {"order_id": str(order.id)})
        await db.commit()
        qr = charge.qr_code_base64
    else:
        qr = None
    lead.stage = "pix"
    caption = render(flow.payment.pix_text, lead, plan.name, order.amount)
    if qr and "," in qr:
        try:
            png = base64.b64decode(qr.split(",", 1)[1])
            await tg.send_media("sendPhoto", "photo", lead.chat_id, InputFile("pix.png", png, "image/png"), caption)
            caption = ""
        except (ValueError, TelegramError):
            pass
    code = order.pix_copy_paste or ""
    keyboard = {
        "inline_keyboard": [
            [{"text": flow.payment.copy_button, "copy_text": {"text": code[:256]}}],
            [{"text": flow.payment.check_button, "callback_data": f"chk:{order.id}"}],
        ]
    }
    if len(code) > 256:  # copy_text is limited to 256 chars; fall back to tap-to-copy text
        keyboard["inline_keyboard"].pop(0)
    body = (caption + "\n\n" if caption else "") + f"<code>{html.escape(code)}</code>"
    await tg.send_message(lead.chat_id, body, keyboard)
    return order


async def check_order(db: AsyncSession, order: TgOrder) -> None:
    """Ask SmokePay directly (the "Já paguei" button and the reconciliation job)."""
    try:
        charge = await smokepay.get_pix(f"{ORDER_PREFIX}{order.id}")
    except smokepay.SmokepayError:
        return
    if charge.status == "paid":
        await approve_order(db, order.id, charge.amount, charge.payer_name, charge.fee, charge.net_amount)
        await db.refresh(order)


async def approve_order(
    db: AsyncSession, order_id: uuid.UUID, paid_amount: Decimal, payer_name: str | None = None,
    fee: Decimal | None = None, net: Decimal | None = None,
) -> bool:
    """Mark paid and deliver. Returns False when another call already handled it."""
    order = await db.get(TgOrder, order_id)
    if order is None:
        return False
    if abs(Decimal(paid_amount) - order.amount) > Decimal("0.01"):
        await db.execute(
            update(TgOrder).where(TgOrder.id == order_id, TgOrder.status.in_(("pending", "expired"))).values(status="review")
        )
        await db.commit()
        logger.warning("Order %s paid with a different amount; left for review.", order_id)
        return False
    result = await db.execute(
        update(TgOrder)
        .where(TgOrder.id == order_id, TgOrder.status.in_(("pending", "expired", "failed")))
        .values(status="paid", paid_at=utcnow(), payer_name=(payer_name or "")[:255] or None,
                gateway_fee=fee if fee is not None else TgOrder.gateway_fee,
                net_amount=net if net is not None else TgOrder.net_amount)
    )
    await db.commit()
    if result.rowcount != 1:
        return False
    await db.refresh(order)
    bot = await db.get(TgBot, order.bot_id)
    lead = await db.get(TgLead, order.lead_id)
    if bot is None or lead is None:
        return True
    lead.stage = "paid"
    await db.execute(update(TgJob).where(TgJob.idempotency_key == f"expire:{order.id}").values(status="cancelled"))
    tg = telegram(bot)
    flow = await load_flow(db, bot)
    plan = Plan.model_validate(order.offer_snapshot)
    try:
        if flow:
            await tg.send_message(lead.chat_id, render(flow.payment.approved_text, lead, plan.name, order.amount))
        delivery = plan.delivery or (flow.default_delivery if flow else None)
        if delivery:
            await deliver(db, tg, bot, lead, order, plan, delivery)
        order.delivered_at = utcnow()
    except TelegramError as exc:
        bot.last_error = str(exc)[:500]
        logger.warning("Delivery for order %s failed: %s", order.id, exc)
    await db.commit()
    await notify_owners(
        db, bot, f"💸 Venda aprovada · {brl(order.amount)}", f"{plan.name} · @{bot.username}", f"sale-{order.id}"
    )
    return True


async def deliver(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, order: TgOrder, plan: Plan, delivery: Delivery) -> None:
    text = render(delivery.text, lead, plan.name, order.amount)
    if delivery.type == "group":
        await _deliver_group(db, tg, bot, lead, order, plan, delivery, text)
        return
    protect = delivery.type == "pack"
    medias = await _media_rows(db, bot, delivery.media_ids)
    if text:
        await tg.send_message(lead.chat_id, text, protect=protect)
    for start in range(0, len(medias), 10):
        chunk = medias[start:start + 10]
        if len(chunk) == 1:
            await send_media_message(db, tg, bot, lead.chat_id, chunk[0].kind, chunk[0], protect=protect)
        else:
            await send_album(db, tg, bot, lead.chat_id, chunk, None, protect=protect)
    if delivery.link:
        await tg.send_message(
            lead.chat_id, delivery.link.label,
            {"inline_keyboard": [[{"text": delivery.link.label, "url": str(delivery.link.url)}]]},
            protect=protect,
        )


async def _deliver_group(db, tg, bot, lead, order, plan: Plan, delivery: Delivery, text: str) -> None:
    now = utcnow()
    chat_id = int(delivery.group_chat_id)
    subscription = await db.scalar(
        select(TgSubscription).where(
            TgSubscription.lead_id == lead.id, TgSubscription.chat_id == chat_id, TgSubscription.status == "active"
        )
    )
    if subscription is None:
        subscription = TgSubscription(
            workspace_id=bot.workspace_id, bot_id=bot.id, lead_id=lead.id, order_id=order.id,
            chat_id=chat_id, starts_at=now, ends_at=now,
        )
        db.add(subscription)
    # Renewal before the end extends from the current end date.
    base = max(aware(subscription.ends_at) or now, now)
    subscription.ends_at = None if plan.duration_days is None else base + timedelta(days=plan.duration_days)
    subscription.order_id = order.id
    link = await tg.create_invite_link(chat_id, f"FP {order.id.hex[:8]}", int((now + INVITE_LINK_TTL).timestamp()))
    subscription.invite_link = link
    await db.flush()
    if subscription.ends_at is not None:
        await schedule(
            db, bot, "end_subscription", subscription.ends_at,
            f"end:{subscription.id}:{int(subscription.ends_at.timestamp())}", lead,
            {"subscription_id": str(subscription.id)},
        )
    await tg.send_message(
        lead.chat_id,
        text or "Seu acesso está liberado. Toque abaixo para entrar 👇",
        {"inline_keyboard": [[{"text": delivery.join_button_label, "url": link}]]},
    )


async def expire_order(db: AsyncSession, tg: TelegramClient, bot: TgBot, order_id: uuid.UUID) -> None:
    order = await db.get(TgOrder, order_id)
    if order is None or order.status != "pending":
        return
    await check_order(db, order)  # last chance: paid right before expiry
    if order.status != "pending":
        return
    order.status = "expired"
    lead = await db.get(TgLead, order.lead_id)
    flow = await load_flow(db, bot)
    if lead and flow:
        await tg.send_message(
            lead.chat_id, render(flow.payment.expired_text, lead, order.offer_name, order.amount),
            {"inline_keyboard": [[{"text": f"🔁 Gerar novo Pix · {order.offer_name}", "callback_data": f"plan:{order.offer_id}"}]]},
        )


async def end_subscription(db: AsyncSession, tg: TelegramClient, bot: TgBot, subscription_id: uuid.UUID) -> None:
    subscription = await db.get(TgSubscription, subscription_id)
    if subscription is None or subscription.status != "active":
        return
    ends = aware(subscription.ends_at)
    if ends is None or ends > utcnow():
        return  # renewed meanwhile; a newer job covers the new date
    lead = await db.get(TgLead, subscription.lead_id)
    subscription.status = "expired"
    if lead is None:
        return
    try:
        await tg.remove_member(subscription.chat_id, lead.tg_user_id)
    except TelegramError as exc:
        logger.info("Could not remove member: %s", exc)
    flow = await load_flow(db, bot)
    if flow and flow.plans:
        await tg.send_message(lead.chat_id, "Seu acesso terminou. Renove para continuar 👇", plans_keyboard(flow))


async def reconcile_pending_orders(db: AsyncSession, limit: int = 25) -> int:
    """Backup for lost webhooks: ask SmokePay about recent pending orders."""
    now = utcnow()
    orders = list(
        await db.scalars(
            select(TgOrder)
            .where(TgOrder.status == "pending", TgOrder.created_at <= now - timedelta(seconds=90), TgOrder.expires_at > now - timedelta(minutes=10))
            .order_by(TgOrder.created_at)
            .limit(limit)
        )
    )
    for order in orders:
        await check_order(db, order)
    return len(orders)


# ---------------------------------------------------------------- owner pushes


async def notify_owners(db: AsyncSession, bot: TgBot, title: str, body: str, tag: str) -> None:
    """Best effort: a push failure must never undo a sale or a delivery."""
    try:
        from app.bots import http
        from app.models import PushSubscription, WorkspaceMember
        from app.core.security import WorkspaceRole
        from app.notifications.milestones import push_to
        from app.notifications.webpush import get_vapid_keys

        owners = select(WorkspaceMember.user_id).where(
            WorkspaceMember.workspace_id == bot.workspace_id,
            WorkspaceMember.role == WorkspaceRole.OWNER.value,
            WorkspaceMember.status == "ACTIVE",
        )
        subscriptions = list(
            await db.scalars(
                select(PushSubscription).where(
                    PushSubscription.workspace_id == bot.workspace_id, PushSubscription.user_id.in_(owners)
                )
            )
        )
        if not subscriptions:
            return
        keys = await get_vapid_keys(db)
        async with http.client(15.0) as session:
            await push_to(db, subscriptions, {"title": title, "body": body, "url": "/bots", "tag": tag}, keys, session, tag[:32])
        await db.commit()
    except Exception:
        logger.exception("Bot push notification failed")
