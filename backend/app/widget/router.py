"""iPhone home-screen widget (Scriptable): today's Flash numbers for one operation.

The script carries a read-only token made in Configurações; only its SHA-256 is stored, and
making a new one (copying the script again) turns the old one off. The token reads these
numbers and nothing else.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import and_, func, select

from app.auth.dependencies import AuthenticatedUser, DbSession, require_csrf
from app.core.time import day_bounds_utc
from app.analytics.periods import user_time_zone
from app.models import TgOrder, User
from app.partners.service import owner_workspace

router = APIRouter(prefix="/api/widget", tags=["widget"])
CENT = Decimal("0.01")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/token", dependencies=[Depends(require_csrf)])
async def new_token(user: AuthenticatedUser, db: DbSession) -> dict:
    if await owner_workspace(db, user.id) is None:
        raise HTTPException(status_code=403, detail="O widget mostra a operação do dono da conta.")
    token = "fpw_" + secrets.token_urlsafe(32)
    user.widget_token_hash = _digest(token)
    await db.commit()
    return {"token": token}


@router.get("/today")
async def today(
    db: DbSession,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None, max_length=120),
) -> dict:
    raw = (authorization or "").removeprefix("Bearer ").strip() or (token or "").strip()
    user = await db.scalar(select(User).where(User.widget_token_hash == _digest(raw))) if raw.startswith("fpw_") else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Widget desconectado: copie o script de novo em Configurações.")
    workspace = await owner_workspace(db, user.id)
    if workspace is None:
        raise HTTPException(status_code=403, detail="Sem operação.")
    zone = await user_time_zone(db, workspace.id, user.id)
    now = datetime.now(zone)
    midnight, tomorrow = day_bounds_utc(now.date(), zone)
    from app.bots.hidden import not_hidden_bot

    own = and_(TgOrder.workspace_id == workspace.id, not_hidden_bot(TgOrder.bot_id))
    generated = await db.scalar(
        select(func.count(TgOrder.id)).where(own, TgOrder.created_at >= midnight, TgOrder.created_at < tomorrow,
            TgOrder.gateway_transaction_id.is_not(None), TgOrder.gateway_transaction_id != "")
    ) or 0
    paid_rows = (await db.execute(
        select(TgOrder.paid_at, TgOrder.amount, func.coalesce(TgOrder.partner_net, TgOrder.net_amount, TgOrder.amount))
        .where(own, TgOrder.status == "paid", TgOrder.paid_at >= midnight, TgOrder.paid_at < tomorrow,
            TgOrder.gateway_transaction_id.is_not(None), TgOrder.gateway_transaction_id != "")
    )).all()
    # commissions earned today from partners' sales count as profit too (per hour, for the chart)
    commission_rows = (await db.execute(
        select(TgOrder.paid_at, TgOrder.split_amount).where(
            TgOrder.split_chief_user_id == user.id, TgOrder.status == "paid",
            TgOrder.paid_at >= midnight, TgOrder.paid_at < tomorrow, TgOrder.split_amount.is_not(None),
        )
    )).all()
    hours = [Decimal("0")] * 24
    commission_hours = [Decimal("0")] * 24
    revenue = profit = commissions = Decimal("0")
    for paid_at, amount, kept in paid_rows:
        moment = paid_at if paid_at.tzinfo else paid_at.replace(tzinfo=timezone.utc)
        hours[moment.astimezone(zone).hour] += Decimal(amount)
        revenue += Decimal(amount)
        profit += Decimal(kept)
    for paid_at, amount in commission_rows:
        moment = paid_at if paid_at.tzinfo else paid_at.replace(tzinfo=timezone.utc)
        commission_hours[moment.astimezone(zone).hour] += Decimal(amount)
        commissions += Decimal(amount)
    profit += commissions
    running = crunning = Decimal("0")
    series, commission_series = [], []
    for hour in range(now.hour + 1):  # cumulative up to now
        running += hours[hour]
        crunning += commission_hours[hour]
        series.append(float(running.quantize(CENT)))
        commission_series.append(float(crunning.quantize(CENT)))
    return {
        "name": "Flash",
        "pix_generated": generated,
        "pix_paid": len(paid_rows),
        "revenue": float(revenue.quantize(CENT)),
        "profit": float(profit.quantize(CENT)),
        "commissions": float(commissions.quantize(CENT)),
        "series": series,
        "commission_series": commission_series,
        "is_admin": user.platform_role == "SUPER_ADMIN",
        "updated_at": now.strftime("%H:%M"),
    }
