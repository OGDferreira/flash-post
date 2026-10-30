"""Super Admin: every operation's loops, bots and funnels, funnel ranking by
template, bot conversion and revenue/commissions per user. Never returns tokens."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import case, func, select, update

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, SuperAdminUser, require_csrf
from app.core.time import utc_now
from app.models import (
    Affiliation,
    InstagramLoop,
    InstagramLoopAccount,
    InstagramPublicationJob,
    SystemSetting,
    TgBot,
    TgFlow,
    TgLead,
    TgMedia,
    TgOrder,
    User,
    Workspace,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.partners.service import (
    PLATFORM_FEE_KEY,
    TRANSACTION_FEE_KEY,
    default_transaction_fee,
    platform_fee_setting,
    transaction_fee_for,
)

router = APIRouter(prefix="/api/admin", tags=["platform administration"])


def _f(value) -> float:
    return round(float(value or 0), 2)


@router.get("/operations")
async def operations(
    _admin: SuperAdminUser, db: DbSession, period: AnalyticsPeriod = "30d",
    start_date: date | None = None, end_date: date | None = None,
) -> dict:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    users = {u.id: u for u in await db.scalars(select(User))}
    workspaces = {w.id: w for w in await db.scalars(select(Workspace))}
    links = {l.affiliate_user_id: l for l in await db.scalars(select(Affiliation).where(Affiliation.status == "ACTIVE"))}
    chiefs = {l.chief_user_id for l in links.values()}

    def owner_name(workspace_id) -> str:
        ws = workspaces.get(workspace_id)
        user = users.get(ws.owner_id) if ws else None
        return user.full_name if user else "—"

    def hierarchy(user_id) -> str:
        if user_id in links:
            return "partner"
        return "chief" if user_id in chiefs else "independent"

    in_period = (TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.paid_at < end)

    # bots: leads, PIX generated and paid, revenue, conversion
    bots = list(await db.scalars(select(TgBot).order_by(TgBot.created_at)))
    flows = {f.id: f for f in await db.scalars(select(TgFlow))}
    leads = dict((await db.execute(
        select(TgLead.bot_id, func.count(TgLead.id)).where(TgLead.created_at >= start, TgLead.created_at < end).group_by(TgLead.bot_id)
    )).all())
    order_stats = {
        bot_id: (int(gen), int(paid), _f(revenue))
        for bot_id, gen, paid, revenue in (await db.execute(
            select(
                TgOrder.bot_id,
                func.count(TgOrder.id),
                func.coalesce(func.sum(case((TgOrder.status == "paid", 1), else_=0)), 0),
                func.coalesce(func.sum(case((TgOrder.status == "paid", TgOrder.amount), else_=0)), 0),
            ).where(TgOrder.created_at >= start, TgOrder.created_at < end).group_by(TgOrder.bot_id)
        )).all()
    }
    bot_rows = []
    for bot in bots:
        generated, paid, revenue = order_stats.get(bot.id, (0, 0, 0.0))
        lead_count = int(leads.get(bot.id, 0))
        bot_rows.append({
            "id": str(bot.id), "name": bot.name, "username": bot.username, "status": bot.status,
            "owner": owner_name(bot.workspace_id), "flow_name": flows[bot.flow_id].name if bot.flow_id in flows else None,
            "leads": lead_count, "pix_generated": generated, "sales": paid, "revenue": revenue,
            "conversion": round(100 * paid / lead_count, 1) if lead_count else 0.0,
            "pix_conversion": round(100 * paid / generated, 1) if generated else 0.0,
        })
    bot_rows.sort(key=lambda r: r["revenue"], reverse=True)

    # funnel ranking, grouped by the original template across partners
    def root(flow_id):
        seen, current = set(), flows.get(flow_id)
        while current and current.template_flow_id in flows and current.template_flow_id not in seen:
            seen.add(current.id)
            current = flows[current.template_flow_id]
        return current
    per_flow = (await db.execute(
        select(TgOrder.flow_id, TgOrder.workspace_id, func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0))
        .where(*in_period).group_by(TgOrder.flow_id, TgOrder.workspace_id)
    )).all()
    ranking: dict[uuid.UUID, dict] = {}
    for flow_id, workspace_id, sales, revenue in per_flow:
        origin = root(flow_id)
        if origin is None:
            continue
        entry = ranking.setdefault(origin.id, {
            "id": str(origin.id), "name": origin.name, "owner": owner_name(origin.workspace_id),
            "shared": bool(origin.shared), "sales": 0, "revenue": 0.0, "operations": set(),
        })
        entry["sales"] += int(sales)
        entry["revenue"] = round(entry["revenue"] + _f(revenue), 2)
        entry["operations"].add(workspace_id)
    funnel_rows = sorted(
        ({**e, "operations": len(e["operations"])} for e in ranking.values()), key=lambda r: r["revenue"], reverse=True
    )

    # revenue and commissions per user (owner of each workspace)
    gross = {
        ws_id: (_f(total), _f(fees), _f(paid_out))
        for ws_id, total, fees, paid_out in (await db.execute(
            select(
                TgOrder.workspace_id, func.coalesce(func.sum(TgOrder.amount), 0),
                func.coalesce(func.sum(TgOrder.gateway_fee), 0), func.coalesce(func.sum(TgOrder.split_amount), 0),
            ).where(*in_period).group_by(TgOrder.workspace_id)
        )).all()
    }
    received = dict((await db.execute(
        select(TgOrder.split_chief_user_id, func.coalesce(func.sum(TgOrder.split_amount), 0))
        .where(*in_period, TgOrder.split_chief_user_id.is_not(None)).group_by(TgOrder.split_chief_user_id)
    )).all())
    fee_default = await default_transaction_fee(db)
    user_rows = []
    for ws in workspaces.values():
        owner = users.get(ws.owner_id)
        if owner is None:
            continue
        total, fees, paid_out = gross.get(ws.id, (0.0, 0.0, 0.0))
        link = links.get(owner.id)
        user_rows.append({
            "user_id": str(owner.id), "name": owner.full_name, "email": owner.email, "hierarchy": hierarchy(owner.id),
            "chief": users[link.chief_user_id].full_name if link and link.chief_user_id in users else None,
            "commission_percent": _f(link.participation_percent) if link else None,
            "revenue": total, "fees": fees, "commission_paid": paid_out, "commission_received": _f(received.get(owner.id)),
            # the user's own per-sale fee override (None = uses the default) and the fee actually applied
            "transaction_fee": str(owner.transaction_fee) if owner.transaction_fee is not None else None,
            "transaction_fee_effective": str(transaction_fee_for(owner, fee_default)),
        })
    user_rows.sort(key=lambda r: r["revenue"], reverse=True)

    # loops of every operation
    loops = list(await db.scalars(select(InstagramLoop).order_by(InstagramLoop.created_at)))
    accounts = dict((await db.execute(
        select(InstagramLoopAccount.loop_id, func.count(InstagramLoopAccount.account_id)).group_by(InstagramLoopAccount.loop_id)
    )).all())
    published_at = func.coalesce(InstagramPublicationJob.published_at, InstagramPublicationJob.updated_at)
    posts = dict((await db.execute(
        select(InstagramPublicationJob.loop_id, func.count(InstagramPublicationJob.id))
        .where(InstagramPublicationJob.status == "published", published_at >= start, published_at < end)
        .group_by(InstagramPublicationJob.loop_id)
    )).all())
    loop_rows = [
        {
            "id": str(loop.id), "name": loop.name, "owner": owner_name(loop.workspace_id), "status": loop.status,
            "accounts": int(accounts.get(loop.id, 0)), "posts": int(posts.get(loop.id, 0)),
            "shared": bool(loop.shared), "from_template": loop.template_loop_id is not None,
        }
        for loop in loops
    ]
    return {
        "period_label": period_label(start, end),
        "users": user_rows, "bots": bot_rows, "funnels": funnel_rows, "loops": loop_rows,
    }


# ------------------------------------------------------------------ funnels (Super Admin sees everything)


@router.post("/bots/{bot_id}/token", dependencies=[Depends(require_csrf)])
async def bot_token(bot_id: uuid.UUID, _admin: SuperAdminUser, db: DbSession, response: Response) -> dict:
    """Super Admin: a user's bot token (asked one bot at a time, never listed or logged)."""
    from app.core.crypto import decrypt_value

    bot = await db.get(TgBot, bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    try:
        token = decrypt_value(bot.encrypted_token)
    except (RuntimeError, ValueError):
        raise HTTPException(status_code=503, detail="Não foi possível ler o token deste bot.") from None
    response.headers["Cache-Control"] = "no-store"
    return {"username": bot.username, "token": token}


@router.get("/flows")
async def all_flows(_admin: SuperAdminUser, db: DbSession) -> dict:
    users = {u.id: u for u in await db.scalars(select(User))}
    workspaces = {w.id: w for w in await db.scalars(select(Workspace))}
    bots = dict((await db.execute(select(TgBot.flow_id, func.count(TgBot.id)).group_by(TgBot.flow_id))).all())
    rows = []
    for flow in await db.scalars(select(TgFlow).order_by(TgFlow.updated_at.desc())):
        ws = workspaces.get(flow.workspace_id)
        owner = users.get(ws.owner_id) if ws else None
        definition = flow.definition or {}
        rows.append({
            "id": str(flow.id), "name": flow.name, "owner": owner.full_name if owner else "—",
            "shared": bool(flow.shared), "bots": int(bots.get(flow.id, 0)),
            "plans": len(definition.get("plans") or []), "upsells": len(definition.get("upsells") or []),
            "downsells": len(definition.get("downsells") or []),
            "updated_at": flow.updated_at.isoformat() if flow.updated_at else None,
        })
    return {"flows": rows}


async def _flow(db, flow_id: uuid.UUID) -> TgFlow:
    flow = await db.get(TgFlow, flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    return flow


@router.get("/flows/{flow_id}")
async def flow_detail(flow_id: uuid.UUID, _admin: SuperAdminUser, db: DbSession) -> dict:
    """Full funnel (copy, media) of any account. Bot tokens are never part of a funnel."""
    from app.bots.portable import _flow_media
    from app.bots.router import _definition_out

    flow = await _flow(db, flow_id)
    medias = await _flow_media(db, flow)
    return {
        "id": str(flow.id), "name": flow.name, "definition": _definition_out(flow.definition),
        "media": [
            {"id": str(m.id), "kind": m.kind, "file_name": m.file_name, "content_type": m.content_type, "size_bytes": m.size_bytes}
            for m in medias
        ],
    }


@router.get("/flows/{flow_id}/media/{media_id}/preview")
async def flow_media_preview(flow_id: uuid.UUID, media_id: uuid.UUID, _admin: SuperAdminUser, db: DbSession) -> dict:
    from app.instagram.storage import SupabaseStorage

    flow = await _flow(db, flow_id)
    media = await db.get(TgMedia, media_id)
    if media is None or media.workspace_id != flow.workspace_id:
        raise HTTPException(status_code=404, detail="Mídia não encontrada.")
    return {"url": await SupabaseStorage.from_settings().create_signed_url(media.storage_path)}


@router.get("/flows/{flow_id}/export")
async def admin_export_flow(flow_id: uuid.UUID, _admin: SuperAdminUser, db: DbSession) -> Response:
    from app.bots import portable
    from app.bots.router import _download

    flow = await _flow(db, flow_id)
    return _download(await portable.export_flow(db, flow), flow.name)


@router.post("/flows/{flow_id}/import-code", dependencies=[Depends(require_csrf)])
async def admin_flow_code(flow_id: uuid.UUID, _admin: SuperAdminUser, db: DbSession) -> dict:
    from app.bots import portable

    flow = await _flow(db, flow_id)
    return {"code": portable.make_code(flow.id), "valid_days": portable.CODE_TTL_SECONDS // 86400}


# ------------------------------------------------------------------ platform fee


class PlatformFee(BaseModel):
    type: Literal["percent", "fixed"]
    value: Decimal = Field(ge=0, le=99, decimal_places=2)


@router.get("/platform-fee")
async def get_platform_fee(_admin: SuperAdminUser, db: DbSession) -> dict:
    fee = await platform_fee_setting(db)
    return {"type": fee["type"], "value": float(fee["value"])}


@router.put("/platform-fee", dependencies=[Depends(require_csrf)])
async def set_platform_fee(payload: PlatformFee, admin: SuperAdminUser, db: DbSession) -> dict:
    row = await db.get(SystemSetting, PLATFORM_FEE_KEY)
    value = {"type": payload.type, "value": str(payload.value.quantize(Decimal("0.01")))}
    if row is None:
        db.add(SystemSetting(key=PLATFORM_FEE_KEY, value=value, updated_by_user_id=admin.id))
    else:
        row.value, row.updated_by_user_id = value, admin.id
    await db.commit()
    return {"type": payload.type, "value": float(payload.value)}


# ------------------------------------------------------------------ sale receipt ("contracheque")

ORIGIN_LABELS = {
    "main": "Venda própria da plataforma",
    "own_funnel": "Funil próprio do vendedor",
    "shared_funnel": "Funil compartilhado (comissão do chefe)",
    "owner_all": "Funil compartilhado (100% do dono)",
}


@router.get("/orders/{order_id}/receipt")
async def sale_receipt(order_id: uuid.UUID, _admin: SuperAdminUser, db: DbSession) -> dict:
    """Everything that happened to one sale's money: gross, the gateway fee, the Flash fee, the
    platform fee, the chief's commission (and its base) and what was left to the seller."""
    order = await db.get(TgOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Venda não encontrada.")
    workspace = await db.get(Workspace, order.workspace_id)
    seller = await db.get(User, workspace.owner_id) if workspace else None
    chief = await db.get(User, order.split_chief_user_id) if order.split_chief_user_id else None

    def value(amount: Decimal | None) -> float | None:
        return float(amount) if amount is not None else None

    cent = Decimal("0.01")
    gross = order.amount
    net = order.net_amount
    if net is None and order.gateway_fee is not None:
        net = (gross - order.gateway_fee).quantize(cent)
    flash_fee = order.transaction_fee or Decimal("0.00")
    platform_extra = Decimal("0.00")
    if order.platform_fee is not None and order.origin == "own_funnel":
        platform_extra = max(Decimal("0.00"), (order.platform_fee - flash_fee).quantize(cent))
    base = (net - flash_fee - platform_extra).quantize(cent) if net is not None else None
    platform_total = (flash_fee + platform_extra).quantize(cent)
    return {
        "id": str(order.id),
        "offer_name": order.offer_name,
        "status": order.status,
        "origin": order.origin,
        "origin_label": ORIGIN_LABELS.get(order.origin or "", "Venda"),
        "gateway": order.gateway,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "gross": value(gross),
        "gateway_fee": value(order.gateway_fee),
        "gateway_net": value(net),
        "flash_fee": value(flash_fee),
        "platform_fee": value(platform_extra),
        "commission_base": value(base),
        "chief": {
            "name": chief.full_name,
            "percent": value(order.split_percent),
            "amount": value(order.split_amount),
        } if chief else None,
        "seller": {
            "name": seller.full_name if seller else "—",
            "amount": value(order.partner_net),
        },
        "platform_total": value(platform_total),
    }


# ------------------------------------------------------------------ per-sale fee (Flash Bot)


class TransactionFeeDefault(BaseModel):
    value: Decimal = Field(ge=0, le=999, decimal_places=2)
    # When true, also clears every user's personal fee so the new default applies to everyone.
    clear_overrides: bool = False


@router.get("/transaction-fee")
async def get_transaction_fee(_admin: SuperAdminUser, db: DbSession) -> dict:
    return {"default": float(await default_transaction_fee(db))}


@router.put("/transaction-fee", dependencies=[Depends(require_csrf)])
async def set_transaction_fee_default(payload: TransactionFeeDefault, admin: SuperAdminUser, db: DbSession) -> dict:
    """The per-sale fee for everyone without a personal override (optionally reset all overrides)."""
    amount = payload.value.quantize(Decimal("0.01"))
    row = await db.get(SystemSetting, TRANSACTION_FEE_KEY)
    value = {"value": str(amount)}
    if row is None:
        db.add(SystemSetting(key=TRANSACTION_FEE_KEY, value=value, updated_by_user_id=admin.id))
    else:
        row.value, row.updated_by_user_id = value, admin.id
    cleared = 0
    if payload.clear_overrides:
        result = await db.execute(
            update(User).where(User.transaction_fee.is_not(None)).values(transaction_fee=None)
        )
        cleared = result.rowcount or 0
    await db.commit()
    return {"default": float(amount), "cleared_overrides": cleared}


# ------------------------------------------------------------------ award photos

AWARD_TYPES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG", "image/webp": b"RIFF"}
AWARD_MAX_BYTES = 8 * 1024 * 1024


@router.get("/awards")
async def list_awards(_admin: SuperAdminUser, db: DbSession) -> dict:
    from app.wallet.router import DEFAULT_AWARD_IMAGES, GOAL_PRIZES, GOALS, custom_award_image_urls

    urls = await custom_award_image_urls(db)
    return {
        "items": [
            {
                "amount": int(g), "prize": GOAL_PRIZES[int(g)], "custom": int(g) in urls,
                "image_url": urls.get(int(g)) or DEFAULT_AWARD_IMAGES.get(int(g)),
            }
            for g in GOALS
        ]
    }


async def _save_award_paths(db, admin_id, paths: dict[int, str]) -> None:
    from app.wallet.router import AWARD_IMAGES_KEY

    value = {str(k): v for k, v in paths.items()}
    row = await db.get(SystemSetting, AWARD_IMAGES_KEY)
    if row is None:
        db.add(SystemSetting(key=AWARD_IMAGES_KEY, value=value, updated_by_user_id=admin_id))
    else:
        row.value, row.updated_by_user_id = value, admin_id
    await db.commit()


@router.put("/awards/{amount}/image", dependencies=[Depends(require_csrf)])
async def upload_award_image(amount: int, request: Request, admin: SuperAdminUser, db: DbSession) -> dict:
    from app.instagram.storage import SupabaseStorage
    from app.wallet.router import GOALS, award_image_paths

    if Decimal(amount) not in GOALS:
        raise HTTPException(status_code=404, detail="Meta não encontrada.")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in AWARD_TYPES:
        raise HTTPException(status_code=415, detail="Envie uma imagem JPG, PNG ou WEBP.")
    content = b""
    async for chunk in request.stream():
        content += chunk
        if len(content) > AWARD_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Imagem maior que 8 MB.")
    if not content.startswith(AWARD_TYPES[content_type]):
        raise HTTPException(status_code=415, detail="O conteúdo do arquivo não é uma imagem válida.")
    ext = content_type.split("/")[1].replace("jpeg", "jpg")
    path = f"awards/{amount}-{uuid.uuid4().hex[:10]}.{ext}"
    try:
        await SupabaseStorage.from_settings().upload(path, content, content_type)
    except Exception:
        raise HTTPException(status_code=502, detail="Não foi possível salvar a imagem.") from None
    paths = await award_image_paths(db)
    paths[amount] = path
    await _save_award_paths(db, admin.id, paths)
    return {"amount": amount, "saved": True}


@router.delete("/awards/{amount}/image", dependencies=[Depends(require_csrf)])
async def remove_award_image(amount: int, admin: SuperAdminUser, db: DbSession) -> dict:
    from app.wallet.router import award_image_paths

    paths = await award_image_paths(db)
    paths.pop(amount, None)
    await _save_award_paths(db, admin.id, paths)
    return {"amount": amount, "saved": True}
