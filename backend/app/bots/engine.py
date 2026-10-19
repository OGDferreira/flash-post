"""Runs a lead through the flow: /start -> (+18) -> welcome -> offer -> (order bump) -> PIX
-> delivery -> upsells; leads that do not pay get the downsell sequence.

Telegram updates and payment webhooks only *record* intent and schedule
``TgJob`` rows; messages that must wait (welcome delays, PIX expiry, the end of
a subscription) are executed by ``run_due_jobs`` from the worker. Every state
change is a conditional UPDATE so a redelivered update, a double tap or a
webhook racing the "Já paguei" button never pays or delivers twice.
"""

import base64
import io
import html
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import smokepay
from app.bots.flow_schema import Block, CustomOffer, Delivery, DownsellStep, FlowDefinition, OrderBump, Plan, UpsellStep
from app.bots.richtext import sanitize
from app.bots.telegram import InputFile, TelegramClient, TelegramError
from app.partners.service import billing_route
from app.core.config import get_settings
from app.core.crypto import decrypt_value
from app.core.time import BRAZIL_TIME_ZONE
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


def greeting(now: datetime | None = None) -> str:
    hour = (now or utcnow()).astimezone(BRAZIL_TIME_ZONE).hour
    return "Bom dia" if 5 <= hour < 12 else "Boa tarde" if 12 <= hour < 18 else "Boa noite"


def render(
    text: str | None, lead: TgLead, plan: str | None = None, amount: Decimal | None = None,
    bot: TgBot | None = None, extra: dict[str, str] | None = None,
) -> str:
    """Owner copy -> valid Telegram HTML with the variables filled (lead data escaped)."""
    if not text:
        return ""
    text = sanitize(text)
    values = {
        "{nome}": html.escape(lead.first_name or "você"),
        "{username}": html.escape(f"@{lead.username}" if lead.username else (lead.first_name or "")),
        "{plano}": html.escape(plan or ""),
        "{valor}": brl(amount) if amount is not None else "",
        "{saudacao}": greeting(),
        "{bot.nome}": html.escape(bot.name if bot else ""),
        "{bot.username}": html.escape(f"@{bot.username}" if bot else ""),
        **{key: html.escape(value) for key, value in (extra or {}).items()},
    }
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def button(text: str, style: str = "default", **action: object) -> dict:
    """Inline button; ``style`` colors it in Telegram apps from Feb 2026 on (ignored before)."""
    data: dict = {"text": text, **action}
    if style and style != "default":
        data["style"] = style
    return data


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
    # A bot may run a funnel shared by the chief: its media live in the funnel's workspace.
    workspaces = {bot.workspace_id}
    if bot.flow_id:
        flow_workspace = await db.scalar(select(TgFlow.workspace_id).where(TgFlow.id == bot.flow_id))
        if flow_workspace:
            workspaces.add(flow_workspace)
    rows = {
        m.id: m
        for m in await db.scalars(
            select(TgMedia).where(TgMedia.id.in_(ids), TgMedia.workspace_id.in_(workspaces))
        )
    }
    return [rows[i] for i in ids if i in rows]


def _cache_kind(media: TgMedia) -> str:
    return {"video": "video", "audio": "voice"}.get(media.kind, "photo")


async def store_in_cache(tg: TelegramClient, bot: TgBot, media: TgMedia) -> str | None:
    """Upload the file to the bot's cache channel/group (a CDN-like backup) and keep
    Telegram's file_id, so leads always get the file by id instead of a fresh upload."""
    if not bot.cache_chat_id:
        return None
    method, field = _SEND[_cache_kind(media)]
    file = InputFile(media.file_name, await load_media_bytes(media), media.content_type)
    try:
        message = await tg.send_media(method, field, int(bot.cache_chat_id), file, silent=True)
    except TelegramError as exc:  # lost admin rights or the chat is gone: upload straight to the lead
        logger.warning("Media cache upload failed for bot %s: %s", bot.id, exc)
        return None
    _remember_file_id(bot, media, message, field)
    return (media.file_ids or {}).get(str(bot.id))


async def _source(tg: TelegramClient, bot: TgBot, media: TgMedia, kind: str | None = None) -> str | InputFile:
    cached = (media.file_ids or {}).get(str(bot.id))
    if cached:
        return cached
    # The cache only holds the default kind of each file (a video note needs its own upload).
    if kind in (None, _cache_kind(media)):
        file_id = await store_in_cache(tg, bot, media)
        if file_id:
            return file_id
    return InputFile(media.file_name, await load_media_bytes(media), media.content_type)


def _forget_file_id(bot: TgBot, media: TgMedia) -> None:
    media.file_ids = {k: v for k, v in (media.file_ids or {}).items() if k != str(bot.id)}


def _stale_file(exc: TelegramError) -> bool:
    text = exc.description.lower()
    return exc.status == 400 and ("file" in text or "wrong remote" in text)


async def warm_cache(db: AsyncSession, tg: TelegramClient, bot: TgBot) -> int:
    """Put every file of the bot's funnel in the cache chat ahead of the first lead."""
    flow = await load_flow(db, bot)
    if flow is None or not bot.cache_chat_id:
        return 0
    stored = 0
    for media in await _media_rows(db, bot, sorted(flow.media_ids(), key=str)):
        if (media.file_ids or {}).get(str(bot.id)):
            continue
        if await store_in_cache(tg, bot, media):
            stored += 1
            await db.commit()
    return stored


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
) -> dict:
    if kind not in _SEND:  # a "photo/video" block follows the uploaded file
        kind = "video" if media.kind == "video" else "photo"
    method, field = _SEND[kind]

    async def send(source: str | InputFile) -> dict:
        return await tg.send_media(
            method,
            field,
            chat_id,
            source,
            caption=caption,
            reply_markup=reply_markup,
            spoiler=spoiler and kind in ("photo", "video"),
            protect=protect,
        )

    source = await _source(tg, bot, media, kind)
    try:
        message = await send(source)
    except TelegramError as exc:
        if isinstance(source, InputFile) or not _stale_file(exc):
            raise
        _forget_file_id(bot, media)  # the cached id went bad: upload again
        message = await send(await _source(tg, bot, media, kind))
    _remember_file_id(bot, media, message, field)
    return message


async def send_album(
    db: AsyncSession, tg: TelegramClient, bot: TgBot, chat_id: int, medias: list[TgMedia],
    caption: str | None, spoiler: bool = False, protect: bool = False,
) -> list:
    items, files = [], {}
    for index, media in enumerate(medias):
        kind = "video" if media.kind == "video" else "photo"
        source = await _source(tg, bot, media, kind)
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
    messages = messages if isinstance(messages, list) else []
    for media, message in zip(medias, messages):
        _remember_file_id(bot, media, message, "video" if media.kind == "video" else "photo")
    return messages


async def send_medias(
    db: AsyncSession, tg: TelegramClient, bot: TgBot, chat_id: int, media_ids: list[uuid.UUID],
    spoiler: bool = False, caption: str | None = None, reply_markup: dict | None = None,
) -> bool:
    """Send up to 3 media before a message. Returns True when ``caption`` and
    ``reply_markup`` rode on the media (a single photo/video with a short caption)."""
    medias = await _media_rows(db, bot, media_ids)
    if not medias:
        return False
    if len(medias) == 1:
        media = medias[0]
        fits = caption is not None and len(caption) <= 1024
        kind = "voice" if media.kind == "audio" else media.kind
        await send_media_message(
            db, tg, bot, chat_id, kind, media, caption if fits else None, reply_markup if fits else None, spoiler=spoiler,
        )
        return fits
    if all(m.kind != "audio" for m in medias):
        await send_album(db, tg, bot, chat_id, medias, None, spoiler=spoiler)
    else:
        for media in medias:
            await send_media_message(db, tg, bot, chat_id, "voice" if media.kind == "audio" else media.kind, media, spoiler=spoiler)
    return False


async def send_media_then_text(
    db: AsyncSession, tg: TelegramClient, bot: TgBot, chat_id: int, media_ids: list[uuid.UUID],
    spoiler: bool, text: str, reply_markup: dict | None,
) -> None:
    """The SharkBot pattern: media first, then the message carrying the buttons."""
    if await send_medias(db, tg, bot, chat_id, media_ids, spoiler, text, reply_markup):
        return
    if text or reply_markup:
        await tg.send_message(chat_id, text or "👇", reply_markup)


async def send_block(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, block: Block) -> None:
    caption = render(block.text, lead, bot=bot)
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
    """Send the welcome right away; blocks after a delay (and what follows them)
    are queued as jobs with their delays."""
    await cancel_lead_jobs(db, lead, ("send_block", "send_offer"))
    tg = telegram(bot)
    run = utcnow()
    nonce = secrets.token_hex(4)
    lead.stage = "welcome"
    immediate = True
    for index, block in enumerate(flow.welcome):
        # The first block always answers /start right away; delays only space the next ones.
        delay = block.delay_seconds if index else 0
        immediate = immediate and delay == 0
        run += timedelta(seconds=delay, microseconds=index)
        if immediate:
            await send_block(db, tg, bot, lead, block)
        else:
            await schedule(db, bot, "send_block", run, f"welcome:{lead.id}:{nonce}:{index}", lead, {"index": index})
    if immediate:
        await send_offer(db, tg, bot, lead, flow)
    else:
        # Microsecond offset keeps the offer after the last block.
        run += timedelta(microseconds=len(flow.welcome) + 1)
        await schedule(db, bot, "send_offer", run, f"offer:{lead.id}:{nonce}", lead)
    if flow.downsells_no_pix:
        await schedule_downsells(db, bot, lead, flow, "no_pix")


def _extra_rows(flow: FlowDefinition) -> list[list[dict]]:
    rows = [[button(item.label, url=str(item.url))] for item in flow.offer.redirect_buttons]
    if flow.support_username:
        rows.append([button("💬 Suporte", url=f"https://t.me/{flow.support_username}")])
    return rows


def plans_keyboard(flow: FlowDefinition) -> dict:
    rows = []
    for plan in flow.plans:
        label = plan.button_text or f"{plan.name} · {brl(plan.price)}"
        rows.append([button(label, plan.button_style, callback_data=f"plan:{plan.id}")])
    return {"inline_keyboard": rows}


def offer_keyboard(flow: FlowDefinition) -> dict | None:
    if flow.offer.cta_enabled and flow.plans:
        rows = [[button(flow.offer.cta_label, flow.offer.cta_style, callback_data="plans")]]
    else:
        rows = plans_keyboard(flow)["inline_keyboard"]
    if flow.previews.enabled and flow.previews.media_ids:
        rows.append([button(flow.previews.label, flow.previews.style, callback_data="prev")])
    rows += _extra_rows(flow)
    return {"inline_keyboard": rows} if rows else None


async def send_offer(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition) -> None:
    """Welcome screen: up to 3 media, the message, then the buttons (or a secondary message with them)."""
    offer = flow.offer
    keyboard = offer_keyboard(flow)
    text = render(offer.text, lead, bot=bot)
    if offer.secondary_enabled:
        await send_media_then_text(db, tg, bot, lead.chat_id, offer.media_ids, offer.spoiler, text, None)
        if keyboard:
            await tg.send_message(lead.chat_id, render(offer.secondary_text, lead, bot=bot) or "👇", keyboard)
    else:
        if not text and keyboard:
            text = render(offer.plans_text, lead, bot=bot)
        await send_media_then_text(db, tg, bot, lead.chat_id, offer.media_ids, offer.spoiler, text, keyboard)
    lead.stage = "offered"


async def send_plans(tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition) -> None:
    """Answer to the CTA button."""
    if flow.plans:
        await tg.send_message(lead.chat_id, render(flow.offer.plans_text, lead, bot=bot) or "👇", plans_keyboard(flow))


# ---------------------------------------------------------------- previews


def duration_text(seconds: int) -> str:
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} hora" if hours == 1 else f"{hours} horas"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minuto" if minutes == 1 else f"{minutes} minutos"
    return f"{seconds} segundos"


async def _previews_open(db: AsyncSession, lead: TgLead) -> bool:
    return bool(await db.scalar(
        select(TgJob.id).where(TgJob.lead_id == lead.id, TgJob.kind == "delete_messages", TgJob.status == "pending").limit(1)
    ))


async def send_previews(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition) -> None:
    """Send the preview media (protected, no forwarding) and schedule their deletion."""
    previews = flow.previews
    medias = await _media_rows(db, bot, previews.media_ids)
    if not medias:
        return
    caption = render(previews.text, lead, bot=bot, extra={"{tempo}": duration_text(previews.delete_after_seconds)}) or None
    sent: list[dict] = []
    if len(medias) > 1 and all(m.kind != "audio" for m in medias):
        sent += await send_album(db, tg, bot, lead.chat_id, medias, caption if caption and len(caption) <= 1024 else None,
                                 spoiler=previews.spoiler, protect=True)
        if caption and len(caption) > 1024:
            sent.append(await tg.send_message(lead.chat_id, caption, protect=True))
    else:
        for position, media in enumerate(medias):
            text = caption if position == 0 and caption and len(caption) <= 1024 else None
            sent.append(await send_media_message(
                db, tg, bot, lead.chat_id, "voice" if media.kind == "audio" else media.kind, media, text,
                spoiler=previews.spoiler, protect=True,
            ))
    ids = [int(m["message_id"]) for m in sent if isinstance(m, dict) and m.get("message_id")]
    if ids:
        await schedule(
            db, bot, "delete_messages", utcnow() + timedelta(seconds=previews.delete_after_seconds),
            f"prevdel:{lead.id}:{secrets.token_hex(6)}", lead, {"chat_id": lead.chat_id, "message_ids": ids},
        )


# ---------------------------------------------------------------- order bump, downsell, upsell


async def send_bump_question(
    db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, plan: Plan, bump: OrderBump,
    answers: tuple[str, str] | None = None,
) -> None:
    """``answers``: callback data of the yes/no buttons (default: the flow plan's ``bump:y|n:<id>``)."""
    yes, no = answers or (f"bump:y:{plan.id}", f"bump:n:{plan.id}")
    text = render(bump.text, lead, plan.name, plan.price, bot, {"{bump}": bump.name, "{bump_valor}": brl(bump.price)})
    keyboard = {"inline_keyboard": [
        [button(f"{bump.accept_label} (+{brl(bump.price)})", "success", callback_data=yes)],
        [button(bump.decline_label, callback_data=no)],
    ]}
    await send_media_then_text(db, tg, bot, lead.chat_id, bump.media_ids, False, text, keyboard)


def discounted(price: Decimal, step: DownsellStep) -> Decimal:
    if step.discount_type == "percent":
        value = price * (Decimal("100") - step.discount_value) / Decimal("100")
    else:
        value = price - step.discount_value
    return max(value.quantize(Decimal("0.01")), Decimal("1.00"))  # SmokePay minimum


# Each downsell sequence: job kind, job key prefix, button prefix and offer id letter.
DOWNSELL = {
    "pix": ("send_downsell", "downsell", "dplan", "d"),
    "no_pix": ("send_downsell_np", "downsellnp", "nplan", "n"),
}


async def schedule_downsells(db: AsyncSession, bot: TgBot, lead: TgLead, flow: FlowDefinition, sequence: str = "pix") -> None:
    """Queue the whole sequence once per lead; each step re-checks that the lead still qualifies."""
    kind, key, _, _ = DOWNSELL[sequence]
    run = utcnow()
    for index, step in enumerate(flow.downsell_steps(sequence)):
        run += timedelta(minutes=step.delay_minutes)
        await schedule(db, bot, kind, run, f"{key}:{lead.id}:{index}", lead, {"index": index})


async def _has_paid(db: AsyncSession, lead: TgLead) -> bool:
    return bool(await db.scalar(select(TgOrder.id).where(TgOrder.lead_id == lead.id, TgOrder.status == "paid").limit(1)))


def custom_offer_plan(index: int, offer: CustomOffer) -> Plan:
    return Plan(id=f"ds{index}", name=offer.name, price=offer.price, duration_days=offer.duration_days, delivery=offer.delivery)


async def send_downsell(
    db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition, index: int, sequence: str = "pix",
) -> None:
    steps = flow.downsell_steps(sequence)
    if not 0 <= index < len(steps) or await _has_paid(db, lead):
        return
    if sequence == "no_pix" and await db.scalar(select(TgOrder.id).where(TgOrder.lead_id == lead.id).limit(1)):
        return  # generated a PIX meanwhile: the "Pix gerado" sequence takes over
    prefix = DOWNSELL[sequence][2]
    step = steps[index]
    if step.custom_offer:
        offer = step.custom_offer
        rows = [[button(f"🔥 {offer.name} · {brl(offer.price)}", step.button_style, callback_data=f"{prefix}:{index}:@")]]
    else:
        plans = [p for p in flow.plans if not step.plan_ids or p.id in step.plan_ids]
        if not plans:
            return
        rows = [
            [button(f"🔥 {p.name} por {brl(discounted(p.price, step))} (antes {brl(p.price)})", step.button_style,
                    callback_data=f"{prefix}:{index}:{p.id}")]
            for p in plans
        ]
    off = f"{step.discount_value.normalize():f}%" if step.discount_type == "percent" else brl(step.discount_value)
    text = render(step.text, lead, bot=bot, extra={"{desconto}": off})
    await send_media_then_text(db, tg, bot, lead.chat_id, step.media_ids, step.spoiler, text, {"inline_keyboard": rows})
    lead.stage = "downsell"


def upsell_plan(index: int, step: UpsellStep) -> Plan:
    return Plan(id=f"up{index}", name=step.name, price=step.price, duration_days=step.duration_days, delivery=step.delivery)


async def schedule_upsell(db: AsyncSession, bot: TgBot, lead: TgLead, flow: FlowDefinition, index: int, chain: str) -> None:
    """``chain`` (the first order of the series) keys the jobs so double taps never repeat a step."""
    if 0 <= index < len(flow.upsells):
        run = utcnow() + timedelta(minutes=flow.upsells[index].delay_minutes)
        await schedule(db, bot, "send_upsell", run, f"upsell:{chain}:{index}", lead, {"index": index, "chain": chain})


async def send_upsell(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition, index: int, chain: str) -> None:
    if not 0 <= index < len(flow.upsells):
        return
    step = flow.upsells[index]
    text = render(step.text, lead, step.name, step.price, bot)
    rows = [[button(f"{step.accept_label} · {brl(step.price)}", step.accept_style, callback_data=f"up:{index}:{chain}")]]
    # One step per purchase: the next step only follows a payment of this one
    # (approve_order) or an explicit "no" tap. Hidden decline = wait for the payment.
    if not step.hide_decline:
        rows.append([button(step.decline_label, callback_data=f"upn:{index}:{chain}")])
    await send_media_then_text(db, tg, bot, lead.chat_id, step.media_ids, step.spoiler, text, {"inline_keyboard": rows})


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
    if job.kind in ("send_block", "send_offer", "send_downsell", "send_downsell_np", "send_upsell"):
        flow = await load_flow(db, bot)
        if flow is None or lead is None:
            return
        index = int(job.payload.get("index", -1))
        if job.kind == "send_block":
            if 0 <= index < len(flow.welcome):
                await send_block(db, tg, bot, lead, flow.welcome[index])
        elif job.kind == "send_offer":
            await send_offer(db, tg, bot, lead, flow)
        elif job.kind == "send_downsell":
            await send_downsell(db, tg, bot, lead, flow, index, "pix")
        elif job.kind == "send_downsell_np":
            await send_downsell(db, tg, bot, lead, flow, index, "no_pix")
        else:
            await send_upsell(db, tg, bot, lead, flow, index, str(job.payload.get("chain", "")))
    elif job.kind == "create_pix":
        flow = await load_flow(db, bot)
        resolved = resolve_offer(flow, str(job.payload.get("data", ""))) if flow and lead else "gone"
        if isinstance(resolved, str):
            return
        plan, options = resolved
        await create_order(db, tg, bot, lead, flow, plan, **options)
    elif job.kind == "expire_order":
        await expire_order(db, tg, bot, uuid.UUID(job.payload["order_id"]))
    elif job.kind == "end_subscription":
        await end_subscription(db, tg, bot, uuid.UUID(job.payload["subscription_id"]))
    elif job.kind == "warm_cache":
        await warm_cache(db, tg, bot)
    elif job.kind == "delete_messages":
        await tg.delete_messages(int(job.payload["chat_id"]), [int(i) for i in job.payload.get("message_ids") or []])


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


async def follow_lead_jobs(db: AsyncSession, lead_id: uuid.UUID, horizon_seconds: int = 120) -> None:
    """Run a lead's jobs as each comes due (welcome delays, PIX) instead of waiting
    for the worker tick; jobs further out than ``horizon_seconds`` stay with the worker."""
    import asyncio

    deadline = utcnow() + timedelta(seconds=horizon_seconds)
    while True:
        await run_due_jobs(db, lead_id=lead_id)
        next_at = await db.scalar(
            select(TgJob.run_at)
            # Preview deletions are not worth holding the update open; the worker tick runs them.
            .where(TgJob.lead_id == lead_id, TgJob.status == "pending", TgJob.kind != "delete_messages")
            .order_by(TgJob.run_at)
            .limit(1)
        )
        if next_at is None:
            return
        if next_at.tzinfo is None:
            next_at = next_at.replace(tzinfo=timezone.utc)
        if next_at > deadline:
            return
        await db.commit()  # release the connection while waiting
        await asyncio.sleep(max(0.0, (next_at - utcnow()).total_seconds()) + 0.05)


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
                render(flow.age_gate.text, lead, bot=bot),
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
    if data == "plans":
        await tg.answer_callback(query["id"])
        await send_plans(tg, bot, lead, flow)
        return None
    if data == "prev":
        if not (flow.previews.enabled and flow.previews.media_ids):
            await tg.answer_callback(query["id"], "As prévias não estão disponíveis agora.")
            return None
        if await _previews_open(db, lead):
            await tg.answer_callback(query["id"], "Suas prévias já estão abertas 👀")
            return None
        await tg.answer_callback(query["id"])
        await send_previews(db, tg, bot, lead, flow)
        return lead.id
    if data.startswith(("rmk:", "rmkb:")):
        from app.bots.campaigns import handle_campaign_tap

        return await handle_campaign_tap(db, tg, bot, lead, flow, query["id"], data)
    if data.startswith("plan:"):
        plan = flow.plan(data[5:])
        bump = flow.bump_for(plan) if plan is not None else None
        if plan is not None and bump is not None:
            await tg.answer_callback(query["id"])
            await send_bump_question(db, tg, bot, lead, plan, bump)
            return None
    if data.startswith("upn:"):
        parts = data.split(":", 2)
        index = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else -1
        if not 0 <= index < len(flow.upsells):
            await tg.answer_callback(query["id"], "Esta oferta não está mais disponível.")
            return None
        await tg.answer_callback(query["id"])
        await schedule_upsell(db, bot, lead, flow, index + 1, parts[2])
        return lead.id
    if data.startswith(("plan:", "bump:", "dplan:", "nplan:", "up:")):
        resolved = resolve_offer(flow, data)
        if isinstance(resolved, str):
            await tg.answer_callback(query["id"], resolved)
            return None
        # Telegram already got its 200 (updates run in the background), so the charge
        # is created right here: no queue round trip before the PIX goes out.
        await tg.answer_callback(query["id"], "Gerando seu Pix…")
        plan, options = resolved
        started = time.perf_counter()
        await create_order(db, tg, bot, lead, flow, plan, **options)
        logger.info("pix sent in %d ms", (time.perf_counter() - started) * 1000)
        return lead.id
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


def resolve_offer(flow: FlowDefinition, data: str) -> tuple[Plan, dict] | str:
    """Map an offer button to the plan and ``create_order`` options, or an error text."""
    gone = "Esta oferta não está mais disponível."
    if data.startswith("plan:"):
        plan = flow.plan(data[5:])
        return (plan, {}) if plan else "Este plano não está mais disponível."
    if data.startswith("bump:"):
        _, answer, plan_id = (data.split(":", 2) + ["", ""])[:3]
        plan = flow.plan(plan_id)
        if plan is None:
            return "Este plano não está mais disponível."
        return plan, {"bump": flow.bump_for(plan) if answer == "y" else None}
    parts = data.split(":", 2)
    index = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else -1
    if data.startswith(("dplan:", "nplan:")):
        sequence = "pix" if data.startswith("dplan:") else "no_pix"
        letter = DOWNSELL[sequence][3]
        steps = flow.downsell_steps(sequence)
        if sequence == "pix" and not steps and flow.downsells_no_pix:
            # buttons sent before the split, when a "no_pix"-only sequence still used "dplan"
            sequence, letter, steps = "no_pix", DOWNSELL["no_pix"][3], flow.downsells_no_pix
        step = steps[index] if 0 <= index < len(steps) else None
        if step is None:
            return gone
        if parts[2] == "@":
            if not step.custom_offer:
                return gone
            return custom_offer_plan(index, step.custom_offer), {"kind": "downsell", "offer_id": f"{'ds' if sequence == 'pix' else 'dn'}{index}", "retry": data}
        plan = flow.plan(parts[2])
        if plan is None:
            return gone
        return (
            plan.model_copy(update={"price": discounted(plan.price, step)}),
            {"kind": "downsell", "offer_id": f"{plan.id}-{letter}{index}", "retry": data},
        )
    if data.startswith("up:") and 0 <= index < len(flow.upsells):
        return upsell_plan(index, flow.upsells[index]), {
            "kind": "upsell", "offer_id": f"up{index}", "step": index, "chain": parts[2], "retry": data,
        }
    return gone


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
        if bot.cache_chat_id == chat["id"]:
            bot.cache_chat_id = None
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


def order_parts(order: TgOrder) -> tuple[Plan, OrderBump | None, dict]:
    """Phase 1 stored the bare plan; newer orders wrap it with the bump and series data."""
    snapshot = order.offer_snapshot or {}
    if "plan" in snapshot:
        bump = OrderBump.model_validate(snapshot["bump"]) if snapshot.get("bump") else None
        return Plan.model_validate(snapshot["plan"]), bump, snapshot
    return Plan.model_validate(snapshot), None, {"kind": order.kind}


async def create_order(
    db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, flow: FlowDefinition, plan: Plan,
    *, bump: OrderBump | None = None, kind: str = "plan", offer_id: str | None = None,
    step: int | None = None, chain: str | None = None, retry: str | None = None,
) -> TgOrder | None:
    now = utcnow()
    amount = plan.price + (bump.price if bump else Decimal("0"))
    offer_id = offer_id or (f"{plan.id}+bump" if bump else plan.id)
    name = f"{plan.name} + {bump.name}" if bump else plan.name
    order = await db.scalar(
        select(TgOrder).where(
            TgOrder.lead_id == lead.id, TgOrder.offer_id == offer_id, TgOrder.amount == amount,
            TgOrder.status == "pending", TgOrder.expires_at > now,
        ).order_by(TgOrder.created_at.desc())
    )
    first_pix = order is None and not await db.scalar(select(TgOrder.id).where(TgOrder.lead_id == lead.id).limit(1))
    timings: dict[str, float] = {}
    mark = time.perf_counter()
    if order is None:
        await tg.send_chat_action(lead.chat_id, "upload_photo")  # the lead sees activity while the gateway answers
        route = await billing_route(db, bot.workspace_id, bot.flow_id)
        if not route.allowed:  # a shared funnel that is no longer available to this bot
            await tg.send_message(lead.chat_id, "Esta oferta não está disponível no momento.")
            await notify_owners(db, bot, "⚠️ Funil indisponível", f"@{bot.username}: o funil compartilhado não está mais liberado.", "bot-flow")
            return None
        snapshot = {
            "plan": plan.model_dump(mode="json"), "bump": bump.model_dump(mode="json") if bump else None,
            "kind": kind, "step": step, "chain": chain, "retry": retry or f"plan:{plan.id}",
        }
        order = TgOrder(
            workspace_id=bot.workspace_id, bot_id=bot.id, lead_id=lead.id, flow_id=bot.flow_id, kind=kind,
            offer_id=offer_id[:64], offer_name=name[:120], offer_snapshot=snapshot,
            amount=amount, expires_at=now + timedelta(minutes=flow.payment.expiration_minutes),
        )
        db.add(order)
        await db.flush()
        order.origin = route.origin
        order.shop_ref = route.shop_ref
        order.split_chief_user_id = route.chief_user_id
        order.split_percent = route.percent
        qr: str | None = None
        timings["prepare"] = time.perf_counter() - mark
        mark = time.perf_counter()
        if not await _charge_with_snakepay(db, bot, order, route, amount):
            try:
                charge = await smokepay.create_pix(
                    amount=amount,
                    external_id=f"{ORDER_PREFIX}{order.id}",
                    description=f"{bot.name} · {name}",
                    webhook_url=payment_webhook_url(),
                    expiration_seconds=flow.payment.expiration_minutes * 60,
                    shop_id=route.shop_ref,
                    splits=route.splits,
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
            if route.percent is not None:
                commission, partner = route.preview(charge.net_amount)
                order.split_amount = charge.split_total if charge.split_total is not None else commission
                order.partner_net = charge.owner_net if charge.owner_net is not None else partner
            elif route.splits:  # platform fee only (partner's own funnel)
                fee = charge.split_total if charge.split_total is not None else route.platform_fee(charge.net_amount)
                order.platform_fee = fee
                if charge.owner_net is not None:
                    order.partner_net = charge.owner_net
                elif fee is not None and charge.net_amount is not None:
                    order.partner_net = charge.net_amount - fee
            order.pix_copy_paste = charge.copy_paste
            qr = charge.qr_code_base64
        timings["gateway"] = time.perf_counter() - mark
        mark = time.perf_counter()
        await schedule(db, bot, "expire_order", order.expires_at, f"expire:{order.id}", lead, {"order_id": str(order.id)})
        if first_pix:
            # Generated a PIX: the "Pix não gerado" sequence stops, the "Pix gerado" one starts.
            await cancel_lead_jobs(db, lead, ("send_downsell_np",))
            if kind in ("plan", "downsell") and flow.downsells:
                await schedule_downsells(db, bot, lead, flow, "pix")
        await db.commit()
        timings["save"] = time.perf_counter() - mark
        mark = time.perf_counter()
    else:
        qr = None
    lead.stage = "pix"
    caption = render(flow.payment.pix_text, lead, order.offer_name, order.amount, bot)
    code = order.pix_copy_paste or ""
    keyboard = {
        "inline_keyboard": [
            [{"text": flow.payment.copy_button, "copy_text": {"text": code[:256]}}],
            [{"text": flow.payment.check_button, "callback_data": f"chk:{order.id}"}],
        ]
    }
    if len(code) > 256:  # copy_text is limited to 256 chars; fall back to tap-to-copy text
        keyboard["inline_keyboard"].pop(0)
    if flow.support_username:
        keyboard["inline_keyboard"].append([button("💬 Suporte", url=f"https://t.me/{flow.support_username}")])
    body = (caption + "\n\n" if caption else "") + f"<code>{html.escape(code)}</code>"
    png = pix_qr_png(code, qr)
    try:
        if png:
            try:
                if len(body) <= 1024:  # QR, text, code and buttons in one message
                    await tg.send_media("sendPhoto", "photo", lead.chat_id, InputFile("pix.png", png, "image/png"), body, keyboard)
                    return order
                await tg.send_media("sendPhoto", "photo", lead.chat_id, InputFile("pix.png", png, "image/png"), caption)
                body = f"<code>{html.escape(code)}</code>"
            except TelegramError:
                pass
        await tg.send_message(lead.chat_id, body, keyboard)
        return order
    finally:
        timings["telegram"] = time.perf_counter() - mark
        logger.info("pix steps: %s", " ".join(f"{k}={v * 1000:.0f}ms" for k, v in timings.items()))


# Workspaces whose SnakePay split was just refused (bad ShopID): SmokePay charges their
# sales for a while instead of paying for one more refused call on every Pix.
SNAKEPAY_PAUSE_SECONDS = 600
_snakepay_paused: dict[uuid.UUID, float] = {}


async def _charge_with_snakepay(db: AsyncSession, bot: TgBot, order: TgOrder, route, amount: Decimal) -> bool:
    """Charge with SnakePay when the operation chose it and every share can be paid
    (see app/bots/gateways.py). False = use SmokePay, also when SnakePay refuses."""
    from app.bots import gateways, snakepay
    from app.models import Workspace

    workspace = await db.get(Workspace, bot.workspace_id)
    if workspace is None:
        return False
    flow = await db.get(TgFlow, bot.flow_id) if bot.flow_id else None
    plan = await gateways.snakepay_plan(db, workspace, route, amount, flow)
    if plan is None:
        return False
    paused = _snakepay_paused.get(bot.workspace_id, 0.0)
    if paused > time.monotonic():
        return False  # refused a moment ago: go straight to SmokePay instead of waiting on a new refusal
    try:
        try:
            charge = await snakepay.create_charge(
                amount=amount, external_reference=f"{ORDER_PREFIX}{order.id}", split=plan.split or None
            )
        except snakepay.SnakepayError as first:
            # A 400 creates no charge, so one retry is safe: the API may want the ShopID in
            # the other spelling (snakepay_<hex> vs dashed UUID).
            if first.status != 400 or not plan.split:
                raise
            logger.warning("SnakePay refused the split (%s); retrying with the other ShopID format.", first)
            plan.split = [{**item, "recipient_id": snakepay.alternate_recipient(item["recipient_id"])} for item in plan.split]
            charge = await snakepay.create_charge(
                amount=amount, external_reference=f"{ORDER_PREFIX}{order.id}", split=plan.split
            )
            plan.seller_recipient = snakepay.alternate_recipient(plan.seller_recipient) if plan.seller_recipient else None
            plan.chief_recipient = snakepay.alternate_recipient(plan.chief_recipient) if plan.chief_recipient else None
    except snakepay.SnakepayError as exc:
        # The sale must not be lost: SmokePay charges this order instead.
        logger.warning(
            "SnakePay charge failed (%s) for workspace %s with %d split recipient(s); falling back to SmokePay.",
            exc, bot.workspace_id, len(plan.split),
        )
        bot.last_error = f"SnakePay: {exc}"[:500]
        if exc.status == 400:  # bad ShopID/split: the next sales would be refused the same way
            _snakepay_paused[bot.workspace_id] = time.monotonic() + SNAKEPAY_PAUSE_SECONDS
        return False
    _snakepay_paused.pop(bot.workspace_id, None)
    gateways.apply_snake_charge(order, route, plan, charge)
    return True


def pix_qr_png(code: str, fallback_b64: str | None = None) -> bytes | None:
    """Large, sharp QR (crisp square modules, ~1000px) from the copy-paste code;
    falls back to the gateway image when the code is missing."""
    if code:
        try:
            import segno

            qr = segno.make(code, error="m", micro=False)
            width = qr.symbol_size(border=4)[0]
            out = io.BytesIO()
            qr.save(out, kind="png", scale=max(8, 1000 // width), border=4)
            return out.getvalue()
        except Exception:  # pragma: no cover - library missing or odd payload
            logger.warning("QR generation failed; using the gateway image")
    if fallback_b64:
        try:
            return base64.b64decode(fallback_b64.split(",", 1)[-1])
        except ValueError:
            return None
    return None


async def check_order(db: AsyncSession, order: TgOrder) -> None:
    """Ask the gateway directly (the "Já paguei" button and the reconciliation job)."""
    if order.gateway == "snakepay":
        from app.bots import snakepay

        if not order.gateway_transaction_id:
            return
        try:
            snake = await snakepay.get_charge(order.gateway_transaction_id)
        except snakepay.SnakepayError:
            return
        if snake.status == "paid":
            net = snake.net_amount
            fee = (snake.amount - net).quantize(Decimal("0.01")) if snake.amount is not None and net is not None else None
            await approve_order(db, order.id, snake.amount or order.amount, None, fee, net)
            await db.refresh(order)
        return
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
    if order.split_percent is not None and order.net_amount is not None and order.partner_net is None:
        commission = (order.net_amount * order.split_percent / Decimal(100)).quantize(Decimal("0.01"))
        order.split_amount, order.partner_net = commission, order.net_amount - commission
    bot = await db.get(TgBot, order.bot_id)
    lead = await db.get(TgLead, order.lead_id)
    if bot is None or lead is None:
        return True
    lead.stage = "paid"
    await db.execute(update(TgJob).where(TgJob.idempotency_key == f"expire:{order.id}").values(status="cancelled"))
    await cancel_lead_jobs(db, lead, ("send_downsell", "send_downsell_np"))
    tg = telegram(bot)
    flow = await load_flow(db, bot)
    plan, bump, info = order_parts(order)
    delivery = plan.delivery or (flow.default_delivery if flow else None)
    try:
        if flow:
            await tg.send_message(lead.chat_id, render(flow.payment.approved_text, lead, order.offer_name, order.amount, bot))
        if delivery and delivery.type != "upsell":
            await deliver(db, tg, bot, lead, order, plan, delivery)
        if bump:
            await deliver(db, tg, bot, lead, order, plan.model_copy(update={"name": bump.name}), bump.delivery)
        order.delivered_at = utcnow()
    except TelegramError as exc:
        bot.last_error = str(exc)[:500]
        logger.warning("Delivery for order %s failed: %s", order.id, exc)
    if flow and flow.upsells:
        if info.get("kind") == "upsell":
            await schedule_upsell(db, bot, lead, flow, int(info.get("step") or 0) + 1, str(info.get("chain") or order.id.hex))
        elif delivery is None or delivery.type == "upsell" or delivery.start_upsell:
            await schedule_upsell(db, bot, lead, flow, 0, order.id.hex)
    await db.commit()
    await notify_sale(db, bot, order)
    return True


async def notify_sale(db: AsyncSession, bot: TgBot, order: TgOrder) -> None:
    """In-app notice + push for the seller, and the chief's commission when split. Best effort."""
    from app.models import User, Workspace
    from app.partners.service import notify_user

    try:
        workspace = await db.get(Workspace, bot.workspace_id)
        net = order.partner_net if order.partner_net is not None else order.net_amount
        if workspace is not None:
            # Short, like the gateways' own alerts: "Nova venda!" / "Você recebeu R$ 7,70".
            await notify_user(
                db, workspace.owner_id, "sale", "⚡ Nova venda!",
                f"Você recebeu {brl(net if net is not None else order.amount)} 🤑", "/feature/bots",
            )
        if order.split_chief_user_id and order.split_amount:
            seller = await db.get(User, workspace.owner_id) if workspace else None
            first = (seller.full_name.split() or ["sócio"])[0] if seller else "sócio"
            await notify_user(
                db, order.split_chief_user_id, "commission", "💰 Comissão recebida!",
                f"Você recebeu {brl(order.split_amount)} 🤑 da venda de {first}", "/carteira",
            )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Sale notification failed")


async def deliver(db: AsyncSession, tg: TelegramClient, bot: TgBot, lead: TgLead, order: TgOrder, plan: Plan, delivery: Delivery) -> None:
    text = render(delivery.text, lead, plan.name, order.amount, bot)
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
    if bot.delivery_group_chat_id and (
        chat_id == 0 or await db.scalar(select(TgFlow.workspace_id).where(TgFlow.id == bot.flow_id)) != bot.workspace_id
    ):
        chat_id = int(bot.delivery_group_chat_id)  # partner's own group for a shared funnel
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
        retry = (order.offer_snapshot or {}).get("retry") or f"plan:{order.offer_id}"
        await tg.send_message(
            lead.chat_id, render(flow.payment.expired_text, lead, order.offer_name, order.amount, bot),
            {"inline_keyboard": [[button(f"🔁 Gerar novo Pix · {order.offer_name}"[:64], callback_data=retry[:64])]]},
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
            await push_to(db, subscriptions, {"title": title, "body": body, "url": "/bots", "tag": tag, "brand": "flashbot"}, keys, session, tag[:32])
        await db.commit()
    except Exception:
        logger.exception("Bot push notification failed")


def resume_snakepay() -> None:
    """Gateway settings changed: try SnakePay again on the next sale."""
    _snakepay_paused.clear()
