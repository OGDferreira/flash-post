"""Bot panel API (owner only) plus the public Telegram and SmokePay webhooks."""

import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.dependencies import AuthenticatedUser, DbSession, OwnerAccess, require_csrf
from app.bots import engine, portable, smokepay
from app.bots.flow_schema import FlowDefinition, default_flow
from app.bots.telegram import TelegramClient, TelegramError
from app.core.config import get_settings
from app.core.crypto import encrypt_value
from app.core.database import get_session_factory
from app.models import TgBot, TgCampaign, TgFlow, TgGroup, TgLead, TgMedia, TgOrder, TgSubscription, TgUpdateSeen, User, Workspace
from app.partners.service import accepted, notify_user, owner_workspace, partner_link, shared_funnel_access, shares_with
from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.bots.stats import conversion_stats, partners_ranking_of
from app.core.time import utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bots", tags=["Bots"])
csrf = [Depends(require_csrf)]

MEDIA_TYPES = {
    "image/jpeg": ("photo", 10 * 1024 * 1024),
    "image/png": ("photo", 10 * 1024 * 1024),
    "image/webp": ("photo", 10 * 1024 * 1024),
    "video/mp4": ("video", 50 * 1024 * 1024),
    "audio/ogg": ("audio", 20 * 1024 * 1024),
    "audio/mpeg": ("audio", 20 * 1024 * 1024),
    "audio/mp4": ("audio", 20 * 1024 * 1024),
}


# ---------------------------------------------------------------- schemas


class BotCreate(BaseModel):
    token: Annotated[str, Field(min_length=20, max_length=200, pattern=r"^\d+:[A-Za-z0-9_-]+$")]
    flow_id: uuid.UUID | None = None


class BotUpdate(BaseModel):
    flow_id: uuid.UUID | None = None
    clear_flow: bool = False
    is_active: bool | None = None
    delivery_group_chat_id: int | None = None
    clear_delivery_group: bool = False


class FlowCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    definition: dict[str, Any] | None = None


class FlowUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    definition: dict[str, Any]


def _bot_out(bot: TgBot, stats: dict | None = None) -> dict:
    return {
        "id": str(bot.id),
        "username": bot.username,
        "name": bot.name,
        "flow_id": str(bot.flow_id) if bot.flow_id else None,
        "delivery_group_chat_id": bot.delivery_group_chat_id,
        "is_active": bot.is_active,
        "status": bot.status,
        "last_error": bot.last_error,
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
        **(stats or {"leads": 0, "sales": 0, "revenue": "0.00"}),
    }


def _definition_out(raw: dict) -> dict:
    """Older flows lack the newer keys; hand the editor the full shape with defaults."""
    try:
        return FlowDefinition.model_validate(raw).model_dump(mode="json")
    except ValidationError:
        return raw


def _flow_out(flow: TgFlow, bots: int = 0, protected: bool = False) -> dict:
    return {
        "id": str(flow.id),
        "name": flow.name,
        "protected": protected,
        # a copy received from a chief runs, but its content never reaches the partner
        "definition": None if protected else _definition_out(flow.definition),
        "version": flow.version,
        "bots": bots,
        "updated_at": flow.updated_at.isoformat() if flow.updated_at else None,
        "shared": bool(flow.shared),
        "shared_with": [str(t) for t in flow.shared_with] if flow.shared and flow.shared_with is not None else None,
        "shared_loop_id": str(flow.shared_loop_id) if flow.shared_loop_id else None,
        "from_template": flow.template_flow_id is not None,
    }


async def _is_received_copy(db, flow: TgFlow) -> bool:
    if flow.template_flow_id is None:
        return False
    template = await db.get(TgFlow, flow.template_flow_id)
    return template is not None and template.workspace_id != flow.workspace_id


async def _readable(db, flow_id: uuid.UUID, access) -> TgFlow:
    """A funnel of this operation whose content the owner may read, copy or edit."""
    flow = await _owned(db, TgFlow, flow_id, access)
    if await _is_received_copy(db, flow):
        raise HTTPException(status_code=403, detail="Funil recebido do seu sócio: pode ser usado no bot, mas não pode ser aberto, copiado ou exportado.")
    return flow


async def _usable_flow(db, flow_id: uuid.UUID, access) -> TgFlow:
    """A funnel of this operation, or one the chief shared with this partner (run only, never read)."""
    flow = await db.get(TgFlow, flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Não encontrado.")
    if flow.workspace_id != access.workspace.id and await shared_funnel_access(db, flow, access.workspace.id) is None:
        raise HTTPException(status_code=404, detail="Não encontrado.")
    return flow


async def _owned(db, model, item_id: uuid.UUID, access) -> Any:
    item = await db.get(model, item_id)
    if item is None or item.workspace_id != access.workspace.id:
        raise HTTPException(status_code=404, detail="Não encontrado.")
    return item


def _validate_definition(raw: dict) -> FlowDefinition:
    try:
        return FlowDefinition.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        raise HTTPException(status_code=422, detail=f"{where}: {first.get('msg')}") from None


def _telegram_webhook_url(bot: TgBot) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/bots/telegram/{bot.id}"


# ---------------------------------------------------------------- status


@router.get("/config")
async def bots_config(access: OwnerAccess) -> dict:
    settings = get_settings()
    return {
        "smokepay_configured": settings.smokepay_api_key is not None,
        "smokepay_webhook_configured": settings.smokepay_webhook_secret is not None,
        "payment_webhook_url": engine.payment_webhook_url(),
    }


# ---------------------------------------------------------------- bots


@router.get("")
async def list_bots(access: OwnerAccess, db: DbSession) -> dict:
    bots = list(await db.scalars(select(TgBot).where(TgBot.workspace_id == access.workspace.id).order_by(TgBot.created_at)))
    leads = dict(
        (await db.execute(
            select(TgLead.bot_id, func.count()).where(TgLead.workspace_id == access.workspace.id).group_by(TgLead.bot_id)
        )).all()
    )
    sales = {
        row[0]: (row[1], row[2])
        for row in (await db.execute(
            select(TgOrder.bot_id, func.count(), func.coalesce(func.sum(TgOrder.amount), 0))
            .where(TgOrder.workspace_id == access.workspace.id, TgOrder.status == "paid")
            .group_by(TgOrder.bot_id)
        )).all()
    }
    return {
        "bots": [
            _bot_out(b, {
                "leads": int(leads.get(b.id, 0)),
                "sales": int(sales.get(b.id, (0, 0))[0]),
                "revenue": f"{Decimal(sales.get(b.id, (0, 0))[1]):.2f}",
            })
            for b in bots
        ]
    }


@router.post("", status_code=201, dependencies=csrf)
async def connect_bot(payload: BotCreate, access: OwnerAccess, db: DbSession) -> dict:
    tg = TelegramClient(payload.token)
    try:
        me = await tg.get_me()
    except TelegramError as exc:
        detail = "Token inválido. Copie de novo do @BotFather." if exc.status in (401, 404) else "Telegram indisponível, tente de novo."
        raise HTTPException(status_code=422, detail=detail) from None
    if not me.get("is_bot"):
        raise HTTPException(status_code=422, detail="Este token não é de um bot.")
    if await db.scalar(select(TgBot.id).where(TgBot.tg_bot_id == me["id"])):
        raise HTTPException(status_code=409, detail="Este bot já está conectado.")
    if payload.flow_id:
        await _usable_flow(db, payload.flow_id, access)
    bot = TgBot(
        workspace_id=access.workspace.id,
        flow_id=payload.flow_id,
        tg_bot_id=me["id"],
        username=me.get("username") or str(me["id"]),
        name=(me.get("first_name") or me.get("username") or "Bot")[:128],
        encrypted_token=encrypt_value(payload.token),
        webhook_secret=secrets.token_urlsafe(32),
    )
    db.add(bot)
    await db.flush()
    try:
        await tg.set_webhook(_telegram_webhook_url(bot), bot.webhook_secret)
    except TelegramError as exc:
        bot.status, bot.last_error = "error", str(exc)[:500]
    await db.commit()
    return _bot_out(bot)


_PHOTO_CACHE: dict[uuid.UUID, tuple[float, bytes | None]] = {}
_PHOTO_TTL = 6 * 3600


async def _bot_photo(bot: TgBot) -> bytes | None:
    """Profile photo of the bot from Telegram (small size), cached per process.
    The bot token stays on the server; the browser only sees our URL."""
    cached = _PHOTO_CACHE.get(bot.id)
    if cached and cached[0] > time.time():
        return cached[1]
    from app.bots import http

    tg = engine.telegram(bot)
    content: bytes | None = None
    try:
        photos = await tg.call("getUserProfilePhotos", {"user_id": bot.tg_bot_id, "limit": 1})
        sizes = (photos or {}).get("photos") or []
        if sizes and sizes[0]:
            pick = sizes[0][min(1, len(sizes[0]) - 1)]  # ~160px is enough for an avatar
            file = await tg.call("getFile", {"file_id": pick["file_id"]})
            path = (file or {}).get("file_path")
            if path:
                async with http.client(20.0) as session:
                    response = await session.get(f"https://api.telegram.org/file/bot{tg._token}/{path}")
                if response.status_code == 200:
                    content = response.content
    except (TelegramError, httpx.HTTPError, KeyError, TypeError):
        content = None
    _PHOTO_CACHE[bot.id] = (time.time() + (_PHOTO_TTL if content else 600), content)
    return content


@router.get("/{bot_id}/photo")
async def bot_photo(bot_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> Response:
    bot = await _owned(db, TgBot, bot_id, access)
    content = await _bot_photo(bot)
    if not content:
        raise HTTPException(status_code=404, detail="Sem foto.")
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=21600"})


@router.patch("/{bot_id}", dependencies=csrf)
async def update_bot(bot_id: uuid.UUID, payload: BotUpdate, access: OwnerAccess, db: DbSession) -> dict:
    bot = await _owned(db, TgBot, bot_id, access)
    if payload.clear_flow:
        bot.flow_id = None
    elif payload.flow_id:
        await _usable_flow(db, payload.flow_id, access)
        bot.flow_id = payload.flow_id
    if payload.clear_delivery_group:
        bot.delivery_group_chat_id = None
    elif payload.delivery_group_chat_id is not None:
        group = await db.scalar(
            select(TgGroup).where(TgGroup.bot_id == bot.id, TgGroup.chat_id == payload.delivery_group_chat_id)
        )
        if group is None:
            raise HTTPException(status_code=422, detail="Adicione o robô como admin desse grupo primeiro.")
        bot.delivery_group_chat_id = group.chat_id
    if payload.is_active is not None:
        bot.is_active = payload.is_active
    await db.commit()
    return _bot_out(bot)


@router.post("/{bot_id}/webhook", dependencies=csrf)
async def reconnect_bot(bot_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    bot = await _owned(db, TgBot, bot_id, access)
    try:
        await engine.telegram(bot).set_webhook(_telegram_webhook_url(bot), bot.webhook_secret)
        bot.status, bot.last_error = "online", None
    except TelegramError as exc:
        bot.status, bot.last_error = "error", str(exc)[:500]
    await db.commit()
    return _bot_out(bot)


@router.delete("/{bot_id}", status_code=204, dependencies=csrf)
async def delete_bot(bot_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> None:
    bot = await _owned(db, TgBot, bot_id, access)
    try:
        await engine.telegram(bot).delete_webhook()
    except TelegramError:
        pass
    await db.delete(bot)
    await db.commit()


@router.get("/groups/list")
async def list_groups(access: OwnerAccess, db: DbSession) -> dict:
    rows = await db.execute(
        select(TgGroup, TgBot.username).join(TgBot, TgBot.id == TgGroup.bot_id)
        .where(TgGroup.workspace_id == access.workspace.id).order_by(TgGroup.title)
    )
    return {
        "groups": [
            {"chat_id": g.chat_id, "title": g.title, "type": g.chat_type, "can_invite": g.can_invite, "bot": username}
            for g, username in rows.all()
        ]
    }


# ---------------------------------------------------------------- flows


@router.get("/flows/list")
async def list_flows(access: OwnerAccess, db: DbSession) -> dict:
    flows = list(await db.scalars(select(TgFlow).where(TgFlow.workspace_id == access.workspace.id).order_by(TgFlow.created_at)))
    usage = dict((await db.execute(
        select(TgBot.flow_id, func.count()).where(TgBot.workspace_id == access.workspace.id).group_by(TgBot.flow_id)
    )).all())
    shared = []
    link = await partner_link(db, access.workspace.owner_id)
    if accepted(link):
        chief_workspace = await owner_workspace(db, link.chief_user_id)
        if chief_workspace is not None:
            # Name only: the chief's funnel content is never sent to a partner.
            shared = [
                {"id": str(f.id), "name": f.name, "shared_from_chief": True}
                for f in await db.scalars(
                    select(TgFlow).where(TgFlow.workspace_id == chief_workspace.id, TgFlow.shared.is_(True)).order_by(TgFlow.name)
                )
                if shares_with(f, access.workspace.owner_id)
            ]
    received = {f.id for f in flows if await _is_received_copy(db, f)}
    return {"flows": [_flow_out(f, int(usage.get(f.id, 0)), f.id in received) for f in flows], "shared_flows": shared}


class ImportCode(BaseModel):
    code: Annotated[str, Field(min_length=10, max_length=300)]


async def _exportable(db, flow_id: uuid.UUID, access) -> TgFlow:
    """Only funnels of this operation; never a copy of a chief's shared funnel."""
    return await _readable(db, flow_id, access)


def _download(data: dict, name: str) -> Response:
    safe = "".join(c for c in name if c.isalnum() or c in " _-").strip().replace(" ", "-") or "funil"
    return Response(
        portable.dumps(data), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe}.flashpost.json"', "Cache-Control": "no-store"},
    )


@router.get("/flows/{flow_id}/export")
async def export_flow(flow_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> Response:
    flow = await _exportable(db, flow_id, access)
    return _download(await portable.export_flow(db, flow), flow.name)


@router.post("/flows/{flow_id}/import-code", dependencies=csrf)
async def flow_import_code(flow_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    flow = await _exportable(db, flow_id, access)
    return {"code": portable.make_code(flow.id), "valid_days": portable.CODE_TTL_SECONDS // 86400}


@router.post("/flows/import", status_code=201, dependencies=csrf)
async def import_flow(request: Request, access: OwnerAccess, db: DbSession) -> dict:
    try:
        data = json.loads(await request.body())
    except ValueError:
        raise HTTPException(status_code=422, detail="Arquivo inválido.") from None
    flow = await portable.import_flow(db, data, access.workspace.id)
    await db.commit()
    await db.refresh(flow)
    return _flow_out(flow)


@router.post("/flows/import-code", status_code=201, dependencies=csrf)
async def import_flow_code(payload: ImportCode, access: OwnerAccess, db: DbSession) -> dict:
    flow = await portable.import_from_code(db, payload.code, access.workspace.id)
    await db.commit()
    await db.refresh(flow)
    return _flow_out(flow)


@router.get("/stats")
async def bot_stats(
    access: OwnerAccess, db: DbSession, period: AnalyticsPeriod = "30d",
    start_date: date | None = None, end_date: date | None = None,
) -> dict:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    data = await conversion_stats(db, access.workspace.id, start, end)
    data["period_label"] = period_label(start, end)
    return data


@router.get("/partners-ranking")
async def partners_ranking(
    access: OwnerAccess, user: AuthenticatedUser, db: DbSession, period: AnalyticsPeriod = "30d",
    start_date: date | None = None, end_date: date | None = None,
) -> dict:
    """Revenue ranking of the chief and their partners. Only positions go out:
    nobody sees how much another member billed (not even the chief)."""
    start, end = period_bounds(period, start_date, end_date, utc_now())
    data = await partners_ranking_of(db, user.id, start, end)
    data["period_label"] = period_label(start, end)
    return data


@router.post("/flows", status_code=201, dependencies=csrf)
async def create_flow(payload: FlowCreate, access: OwnerAccess, db: DbSession) -> dict:
    definition = _validate_definition(payload.definition) if payload.definition else default_flow()
    flow = TgFlow(workspace_id=access.workspace.id, name=payload.name.strip(), definition=definition.model_dump(mode="json"))
    db.add(flow)
    await db.commit()
    return _flow_out(flow)


@router.get("/flows/{flow_id}")
async def get_flow(flow_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    return _flow_out(await _readable(db, flow_id, access))


@router.get("/flows/{flow_id}/summary")
async def flow_summary(flow_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    """Leads, active VIPs and revenue of one flow (all time), like the editor's header card."""
    flow = await _owned(db, TgFlow, flow_id, access)
    leads = await db.scalar(select(func.count(TgLead.id)).where(TgLead.flow_id == flow.id))
    vips = await db.scalar(
        select(func.count(func.distinct(TgSubscription.lead_id)))
        .join(TgLead, TgLead.id == TgSubscription.lead_id)
        .where(TgLead.flow_id == flow.id, TgSubscription.status == "active")
    )
    revenue = await db.scalar(
        select(func.coalesce(func.sum(TgOrder.amount), 0)).where(TgOrder.flow_id == flow.id, TgOrder.status == "paid")
    )
    return {"leads": int(leads or 0), "vips": int(vips or 0), "revenue": f"{Decimal(revenue or 0):.2f}"}


@router.put("/flows/{flow_id}", dependencies=csrf)
async def save_flow(flow_id: uuid.UUID, payload: FlowUpdate, access: OwnerAccess, db: DbSession) -> dict:
    flow = await _readable(db, flow_id, access)
    definition = _validate_definition(payload.definition)
    media_ids = definition.media_ids()
    if media_ids:
        found = set(await db.scalars(
            select(TgMedia.id).where(TgMedia.id.in_(media_ids), TgMedia.workspace_id == access.workspace.id)
        ))
        if found != media_ids:
            raise HTTPException(status_code=422, detail="Alguma mídia do fluxo não existe mais. Envie de novo.")
    flow.name = payload.name.strip()
    flow.definition = definition.model_dump(mode="json")
    flow.version += 1
    await _notify_template_change(db, flow, access.workspace.id)
    await db.commit()
    await db.refresh(flow)  # updated_at is set by the database (onupdate)
    return _flow_out(flow)


async def _notify_template_change(db, flow: TgFlow, workspace_id: uuid.UUID) -> None:
    """A partner changed their copy of a shared funnel: tell the chief (at most hourly).
    The chief's original is never touched."""
    if flow.template_flow_id is None:
        return
    now = engine.utcnow()
    last = flow.customized_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    flow.customized_at = now
    if last is not None and now - last < timedelta(hours=1):
        return
    template = await db.get(TgFlow, flow.template_flow_id)
    if template is None or template.workspace_id == workspace_id:
        return
    chief_workspace = await db.get(Workspace, template.workspace_id)
    partner_workspace = await db.get(Workspace, workspace_id)
    partner = await db.get(User, partner_workspace.owner_id) if partner_workspace else None
    if chief_workspace is None or partner is None:
        return
    await notify_user(
        db, chief_workspace.owner_id, "partner-flow-changed", "Sócio alterou um funil",
        f"{partner.full_name} personalizou a cópia do funil “{template.name}”. O seu original não mudou.", "/feature/affiliates",
    )


@router.post("/flows/{flow_id}/duplicate", status_code=201, dependencies=csrf)
async def duplicate_flow(flow_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    source = await _readable(db, flow_id, access)
    flow = TgFlow(workspace_id=access.workspace.id, name=f"{source.name} (cópia)"[:120], definition=source.definition)
    db.add(flow)
    await db.commit()
    return _flow_out(flow)


@router.delete("/flows/{flow_id}", status_code=204, dependencies=csrf)
async def delete_flow(flow_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> None:
    flow = await _owned(db, TgFlow, flow_id, access)
    # Explicit unlink: the FK's SET NULL is not enforced on every backend (e.g. SQLite).
    for model in (TgBot, TgLead, TgOrder):
        await db.execute(update(model).where(model.flow_id == flow.id).values(flow_id=None))
    await db.execute(delete(TgCampaign).where(TgCampaign.flow_id == flow.id))
    await db.delete(flow)
    await db.commit()


# ---------------------------------------------------------------- media


def _media_out(media: TgMedia) -> dict:
    return {
        "id": str(media.id), "kind": media.kind, "file_name": media.file_name,
        "content_type": media.content_type, "size_bytes": media.size_bytes,
    }


@router.get("/media/list")
async def list_media(access: OwnerAccess, db: DbSession) -> dict:
    rows = await db.scalars(
        select(TgMedia).where(TgMedia.workspace_id == access.workspace.id, TgMedia.locked.is_(False)).order_by(TgMedia.created_at.desc())
    )
    return {"media": [_media_out(m) for m in rows]}


@router.get("/media/{media_id}/preview")
async def preview_media(media_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    from app.instagram.storage import SupabaseStorage

    media = await _owned(db, TgMedia, media_id, access)
    if media.locked:
        raise HTTPException(status_code=403, detail="Mídia protegida do seu sócio: não pode ser vista nem baixada.")
    try:
        url = await SupabaseStorage.from_settings().create_signed_url(media.storage_path)
    except Exception:
        raise HTTPException(status_code=502, detail="Prévia indisponível.") from None
    return {"url": url}


@router.post("/media", status_code=201, dependencies=csrf)
async def upload_media(
    request: Request, access: OwnerAccess, db: DbSession,
    filename: str = Query(min_length=1, max_length=255),
) -> dict:
    from app.instagram.storage import SupabaseStorage, SupabaseStorageError

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    kind_limit = MEDIA_TYPES.get(content_type)
    if kind_limit is None:
        raise HTTPException(status_code=415, detail="Envie JPG, PNG, WEBP, MP4, OGG, MP3 ou M4A.")
    kind, limit = kind_limit
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"Arquivo maior que {limit // (1024 * 1024)} MB.")
        chunks.append(chunk)
    if not size:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    content = b"".join(chunks)
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG"),
        "image/webp": content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        "video/mp4": content[4:8] == b"ftyp",
        "audio/mp4": content[4:8] == b"ftyp",
        "audio/ogg": content.startswith(b"OggS"),
        "audio/mpeg": content.startswith(b"ID3") or content[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
    }
    if not signatures[content_type]:
        raise HTTPException(status_code=415, detail="O conteúdo do arquivo não corresponde ao tipo.")
    safe = PurePosixPath(filename.replace("\\", "/")).name.strip()[:200] or "arquivo"
    media_id = uuid.uuid4()
    path = f"{access.workspace.id}/bots/{media_id}/{safe}"
    try:
        await SupabaseStorage.from_settings().upload(path, content, content_type)
    except (RuntimeError, SupabaseStorageError, httpx.HTTPError) as exc:
        logger.error("Bot media upload failed (%s).", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Não foi possível salvar o arquivo.") from None
    media = TgMedia(
        id=media_id, workspace_id=access.workspace.id, kind=kind, file_name=safe,
        content_type=content_type, size_bytes=size, storage_path=path, file_ids={},
    )
    db.add(media)
    await db.commit()
    return _media_out(media)


@router.delete("/media/{media_id}", status_code=204, dependencies=csrf)
async def delete_media(media_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> None:
    media = await _owned(db, TgMedia, media_id, access)
    flows = await db.scalars(select(TgFlow).where(TgFlow.workspace_id == access.workspace.id))
    if any(media_id in FlowDefinition.model_validate(f.definition).media_ids() for f in flows):
        raise HTTPException(status_code=409, detail="Esta mídia está em uso em um fluxo.")
    await db.delete(media)
    await db.commit()


# ---------------------------------------------------------------- sales


@router.get("/orders/list")
async def list_orders(access: OwnerAccess, db: DbSession, limit: int = Query(50, ge=1, le=200)) -> dict:
    rows = await db.execute(
        select(TgOrder, TgLead, TgBot.username)
        .join(TgLead, TgLead.id == TgOrder.lead_id).join(TgBot, TgBot.id == TgOrder.bot_id)
        .where(TgOrder.workspace_id == access.workspace.id)
        .order_by(TgOrder.created_at.desc()).limit(limit)
    )
    return {
        "orders": [
            {
                "id": str(o.id), "status": o.status, "plan": o.offer_name, "amount": f"{o.amount:.2f}",
                "net_amount": f"{o.net_amount:.2f}" if o.net_amount is not None else None,
                "bot": username, "lead": lead.first_name, "lead_username": lead.username,
                "source": lead.source, "created_at": o.created_at.isoformat() if o.created_at else None,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            }
            for o, lead, username in rows.all()
        ]
    }


@router.get("/summary")
async def summary(access: OwnerAccess, db: DbSession, days: int = Query(1, ge=1, le=90)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    ws = access.workspace.id
    leads = await db.scalar(select(func.count()).select_from(TgLead).where(TgLead.workspace_id == ws, TgLead.created_at >= since))
    generated, paid, revenue = (await db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case((TgOrder.status == "paid", 1), else_=0)), 0),
            func.coalesce(func.sum(case((TgOrder.status == "paid", TgOrder.amount), else_=0)), 0),
        ).where(TgOrder.workspace_id == ws, TgOrder.created_at >= since, TgOrder.status != "failed")
    )).one()
    return {
        "days": days, "leads": int(leads or 0), "pix_generated": int(generated or 0), "pix_paid": int(paid or 0),
        "revenue": f"{Decimal(revenue or 0):.2f}",
        "conversion": round(100 * int(paid or 0) / int(generated), 1) if generated else 0.0,
    }


# ---------------------------------------------------------------- public webhooks


async def _process_update(bot_id: uuid.UUID, update: dict) -> None:
    """Runs after Telegram already got its 200: replies go out straight from here
    (no queue round trip); only delayed messages wait in the job table."""
    started = time.perf_counter()
    async with get_session_factory()() as db:
        bot = await db.get(TgBot, bot_id)
        if bot is None:
            return
        try:
            lead_id = await engine.handle_update(db, bot, update)
            if bot.status != "online":
                bot.status, bot.last_error = "online", None
            await db.commit()
        except TelegramError as exc:
            await db.rollback()
            logger.warning("Bot update failed: %s", exc)
            return
        except Exception:
            await db.rollback()
            logger.exception("Bot update crashed")
            return
        logger.info("bot update handled in %d ms", (time.perf_counter() - started) * 1000)
        if lead_id:
            await engine.follow_lead_jobs(db, lead_id)


@router.post("/telegram/{bot_id}", include_in_schema=False)
async def telegram_webhook(bot_id: uuid.UUID, request: Request, background: BackgroundTasks, db: DbSession) -> dict:
    bot = await db.get(TgBot, bot_id)
    given = request.headers.get("x-telegram-bot-api-secret-token", "")
    if bot is None or not hmac.compare_digest(given, bot.webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid secret.")
    try:
        update = json.loads(await request.body())
        update_id = int(update["update_id"])
    except (ValueError, KeyError, TypeError):
        return {"ok": True}
    if not bot.is_active:
        return {"ok": True}
    try:
        db.add(TgUpdateSeen(bot_id=bot.id, update_id=update_id))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"ok": True}  # redelivery
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Retry.") from None
    background.add_task(_process_update, bot.id, update)
    return {"ok": True}


@router.post("/pay/smokepay", include_in_schema=False)
async def smokepay_webhook(request: Request, db: DbSession) -> dict:
    raw = await request.body()
    if not smokepay.verify_signature(raw, request.headers.get("x-webhook-signature")):
        raise HTTPException(status_code=401, detail="Invalid signature.")  # 4xx stops retries
    try:
        event = json.loads(raw)
    except ValueError:
        return {"ok": True}
    external_id = str(event.get("external_id") or "")
    if event.get("event") != "payment.confirmed" or event.get("status") != "paid" or not external_id.startswith(engine.ORDER_PREFIX):
        return {"ok": True}  # not a bot order (e.g. another integration)
    try:
        order_id = uuid.UUID(external_id[len(engine.ORDER_PREFIX):])
    except ValueError:
        return {"ok": True}
    try:
        await engine.approve_order(
            db, order_id, Decimal(str(event.get("amount"))), event.get("payer_name"),
            Decimal(str(event["fee"])) if event.get("fee") is not None else None,
            Decimal(str(event["net_amount"])) if event.get("net_amount") is not None else None,
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Retry.") from None  # 5xx: SmokePay retries
    return {"ok": True}
