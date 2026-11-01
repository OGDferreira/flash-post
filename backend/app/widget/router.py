"""iPhone home-screen widget (Scriptable): today's Flash numbers for one operation.

The script carries a read-only token made in Configurações; only its SHA-256 is stored, and
making a new one (copying the script again) turns the old one off. The token reads these
numbers and nothing else.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from app.auth.dependencies import AuthenticatedUser, DbSession, require_csrf
from app.core.time import day_bounds_utc
from app.analytics.periods import user_time_zone
from app.models import InstagramAccountDailyViews, TgOrder, User
from app.models.sharkbot import SharkTransaction
from app.partners.service import owner_workspace

router = APIRouter(prefix="/api/widget", tags=["widget"])
CENT = Decimal("0.01")
WidgetTheme = Literal["claro", "escuro", "pb", "roxo", "galaxia", "rosa", "flores"]


class ThemeChoice(BaseModel):
    theme: WidgetTheme


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


async def _token_user(db, authorization: str | None, token: str | None) -> User:
    raw = (authorization or "").removeprefix("Bearer ").strip() or (token or "").strip()
    user = await db.scalar(select(User).where(User.widget_token_hash == _digest(raw))) if raw.startswith("fpw_") else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Widget desconectado: copie o script de novo em Configurações.")
    return user


@router.get("/theme")
async def get_theme(user: AuthenticatedUser) -> dict:
    return {"theme": user.widget_theme}


@router.put("/theme", dependencies=[Depends(require_csrf)])
async def set_theme(payload: ThemeChoice, user: AuthenticatedUser, db: DbSession) -> dict:
    """Picked with a tap in Configurações: the widget takes it on its next refresh."""
    user.widget_theme = payload.theme
    await db.commit()
    return {"theme": user.widget_theme}


@router.post("/theme/phone")
async def set_theme_from_phone(
    payload: ThemeChoice, db: DbSession, authorization: str | None = Header(default=None)
) -> dict:
    """Picked with a tap on the phone (the widget's own view). The widget token may change
    only this look, nothing else."""
    user = await _token_user(db, authorization, None)
    user.widget_theme = payload.theme
    await db.commit()
    return {"theme": user.widget_theme}


@router.get("/today")
async def today(
    db: DbSession,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None, max_length=120),
) -> dict:
    user = await _token_user(db, authorization, token)
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
    # SharkBot sales reported by its webhook today: they count in the sales and the total.
    shark_rows = (await db.execute(
        select(SharkTransaction.paid_at, SharkTransaction.amount).where(
            SharkTransaction.workspace_id == workspace.id, SharkTransaction.status == "paid",
            SharkTransaction.paid_at >= midnight, SharkTransaction.paid_at < tomorrow,
        )
    )).all()
    # Flash Post: Meta's views of the operation's Instagram accounts today.
    views = int(await db.scalar(
        select(func.coalesce(func.sum(InstagramAccountDailyViews.views), 0)).where(
            InstagramAccountDailyViews.workspace_id == workspace.id, InstagramAccountDailyViews.day == now.date(),
        )
    ) or 0)
    hours = [Decimal("0")] * 24
    commission_hours = [Decimal("0")] * 24
    revenue = profit = commissions = Decimal("0")
    for paid_at, amount, kept in paid_rows:
        moment = paid_at if paid_at.tzinfo else paid_at.replace(tzinfo=timezone.utc)
        hours[moment.astimezone(zone).hour] += Decimal(amount)
        revenue += Decimal(amount)
        profit += Decimal(kept)
    shark = Decimal("0")
    for paid_at, amount in shark_rows:
        moment = paid_at if paid_at.tzinfo else paid_at.replace(tzinfo=timezone.utc)
        hours[moment.astimezone(zone).hour] += Decimal(amount or 0)
        shark += Decimal(amount or 0)
    for paid_at, amount in commission_rows:
        moment = paid_at if paid_at.tzinfo else paid_at.replace(tzinfo=timezone.utc)
        commission_hours[moment.astimezone(zone).hour] += Decimal(amount)
        commissions += Decimal(amount)
    profit += commissions
    # Super Admin: the Flash fee collected today on every paid sale of the platform.
    is_admin = user.platform_role == "SUPER_ADMIN"
    fees = Decimal("0")
    if is_admin:
        fees = Decimal(await db.scalar(
            select(func.coalesce(func.sum(TgOrder.transaction_fee), 0)).where(
                TgOrder.status == "paid", TgOrder.paid_at >= midnight, TgOrder.paid_at < tomorrow,
            )
        ) or 0)
    running = crunning = Decimal("0")
    series, commission_series = [], []
    for hour in range(now.hour + 1):  # cumulative up to now
        running += hours[hour]
        crunning += commission_hours[hour]
        series.append(float(running.quantize(CENT)))
        commission_series.append(float(crunning.quantize(CENT)))
    sales = revenue + shark
    total = sales + commissions + fees if is_admin else sales
    return {
        "name": "Flash",
        "theme": user.widget_theme,
        "sales": float(sales.quantize(CENT)),  # Flash + SharkBot
        "sales_count": len(paid_rows) + len(shark_rows),
        "shark_revenue": float(shark.quantize(CENT)),
        "shark_sales": len(shark_rows),
        "views": views,
        "pix_generated": generated,
        "pix_paid": len(paid_rows),
        "revenue": float(revenue.quantize(CENT)),
        "profit": float(profit.quantize(CENT)),
        "commissions": float(commissions.quantize(CENT)),
        "series": series,
        "commission_series": commission_series,
        "fees": float(fees.quantize(CENT)),
        # Super Admin: sales + commissions + fees; everyone else: the sales
        "total": float(total.quantize(CENT)),
        "is_admin": is_admin,
        "updated_at": now.strftime("%H:%M"),
    }
