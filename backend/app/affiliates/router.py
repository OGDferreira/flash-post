"""Invite codes, affiliate links and the chief's view of their affiliates.

Rules enforced here (never only in the UI):
* every affiliate has exactly one chief (unique index on affiliate_user_id);
* nobody can be their own chief, and chains can never loop;
* an affiliate keeps their own workspace and never sees the chief's data;
* a chief can only read aggregate numbers of their *direct* affiliates;
* the participation is a reference calculation. Falcon Post makes no payouts.
"""

import base64
import hashlib
import hmac
import secrets
import time
from datetime import date, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.hidden import not_hidden_bot

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label, user_time_zone
from app.auth.dependencies import AuthenticatedUser, DbSession, OwnerAccess, require_csrf
from app.core.config import get_settings
from app.core.time import APP_TIME_ZONE_NAME, BRAZIL_TIME_ZONE, utc_now
from app.models import (
    Affiliation,
    InstagramAccount,
    InstagramMediaInsight,
    InstagramPublicationJob,
    TgLead,
    TgOrder,
    User,
    Workspace,
    WorkspaceMember,
)
from app.partners.service import notify_user
from app.shark.metrics import CRITERIA, compute_shark_metrics, window

router = APIRouter(prefix="/api/affiliates", tags=["Affiliates"])

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
_CODE_LENGTH = 10
_MAX_CHAIN_DEPTH = 50

PARTICIPATION_BASIS = (
    "Participação = receita aprovada do filiado no período (compras pagas com valor informado, "
    "valor bruto, sem descontar taxas, impostos ou custos) × percentual definido por você. "
    "É um valor de referência. Nas vendas do Falcon Bot, o percentual definido pelo sócio que convida "
    "é separado automaticamente pelo gateway (split) e aparece em “Comissão recebida”."
)


def normalize_code(value: str) -> str:
    return "".join(value.split()).replace("-", "").upper()


def _new_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


async def ensure_invite_code(db: AsyncSession, user: User, *, rotate: bool = False) -> str:
    if user.invite_code and not rotate:
        return user.invite_code
    for _ in range(8):
        code = _new_code()
        if not await db.scalar(select(User.id).where(User.invite_code == code)):
            user.invite_code = code
            await db.flush()
            return code
    raise HTTPException(status_code=503, detail="Não foi possível gerar o código agora.")


async def owns_workspace(db: AsyncSession, user_id: UUID) -> bool:
    return bool(
        await db.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.role == "OWNER",
                WorkspaceMember.status == "ACTIVE",
            )
        )
    )


async def chief_chain_contains(db: AsyncSession, start_user_id: UUID, target_user_id: UUID) -> bool:
    """True when ``target`` is ``start`` or one of ``start``'s chiefs, however high."""
    current: UUID | None = start_user_id
    seen: set[UUID] = set()
    for _ in range(_MAX_CHAIN_DEPTH):
        if current is None:
            return False
        if current == target_user_id:
            return True
        if current in seen:  # corrupted data: treat as a loop, refuse the link
            return True
        seen.add(current)
        current = await db.scalar(
            select(Affiliation.chief_user_id).where(Affiliation.affiliate_user_id == current)
        )
    return True  # absurdly deep chain: refuse


async def find_chief(db: AsyncSession, code: str) -> User:
    normalized = normalize_code(code)
    chief = await db.scalar(select(User).where(User.invite_code == normalized)) if normalized else None
    if chief is None or not chief.is_active:
        raise HTTPException(status_code=422, detail="Código de convite inválido.")
    return chief


async def link_affiliate(db: AsyncSession, code: str, affiliate: User) -> Affiliation:
    """Create the link or raise a 4xx. The caller commits."""
    chief = await find_chief(db, code)
    if chief.id == affiliate.id:
        raise HTTPException(status_code=422, detail="Você não pode usar o seu próprio código de convite.")
    if await db.scalar(select(Affiliation.id).where(Affiliation.affiliate_user_id == affiliate.id)):
        raise HTTPException(status_code=409, detail="Você já está vinculado a um chefe.")
    if await db.scalar(
        select(Affiliation.id).where(Affiliation.affiliate_user_id == chief.id, Affiliation.status == "ACTIVE")
    ):
        raise HTTPException(status_code=422, detail="Este código é de um sócio e serve só para novos cadastros.")
    if await chief_chain_contains(db, chief.id, affiliate.id):
        raise HTTPException(
            status_code=422, detail="Este vínculo criaria um ciclo entre chefe e filiado."
        )
    link = Affiliation(chief_user_id=chief.id, affiliate_user_id=affiliate.id)
    db.add(link)
    return link


# --------------------------------------------------------------- invite terms
_TERMS_TTL_SECONDS = 30 * 24 * 3600


def _terms_key() -> bytes:
    secret = get_settings().session_secret
    if secret is None:
        raise HTTPException(status_code=503, detail="Servidor sem chave de assinatura.")
    return hashlib.sha256(b"invite-terms:" + secret.get_secret_value().encode()).digest()


def make_invite_terms(chief_id: UUID, percent: Decimal) -> str:
    """Signed "this chief offers X%": the invitee cannot change it in the URL."""
    payload = f"{chief_id.hex}.{percent.quantize(Decimal('0.01'))}.{int(time.time()) + _TERMS_TTL_SECONDS}"
    signature = hmac.new(_terms_key(), payload.encode(), hashlib.sha256).hexdigest()[:20]
    return base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode().rstrip("=")


def read_invite_terms(token: str) -> tuple[UUID, Decimal] | None:
    """(chief id, percent) for a valid, unexpired token; None otherwise."""
    try:
        raw = base64.urlsafe_b64decode(token.strip() + "=" * (-len(token.strip()) % 4)).decode()
        chief_hex, whole, cents, expires, signature = raw.split(".")
        percent = f"{whole}.{cents}"
        payload = f"{chief_hex}.{percent}.{expires}"
        expected = hmac.new(_terms_key(), payload.encode(), hashlib.sha256).hexdigest()[:20]
        if not hmac.compare_digest(expected, signature) or int(expires) < time.time():
            return None
        value = Decimal(percent)
        if not Decimal("0") <= value <= Decimal("100"):
            return None
        return UUID(chief_hex), value
    except Exception:
        return None


# --------------------------------------------------------------- schemas
class InviteResponse(BaseModel):
    code: str
    invite_url: str
    percent: Decimal | None = None


class InviteLinkRequest(BaseModel):
    percent: Decimal = Field(ge=0, le=90, decimal_places=2)


class InvitePreview(BaseModel):
    chief_name: str
    percent: Decimal | None


class JoinRequest(BaseModel):
    code: str = Field(min_length=4, max_length=40)


class MyChiefResponse(BaseModel):
    chief_name: str | None
    chief_nickname: str | None
    participation_percent: Decimal | None
    since: str | None
    has_chief: bool


class PercentRequest(BaseModel):
    # Below 100: SmokePay refuses splits that take the whole net amount.
    participation_percent: Decimal = Field(ge=0, le=99, decimal_places=2)


class AffiliateRow(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    nickname: str
    participation_percent: Decimal
    since: str
    accounts_total: int
    accounts_connected: int
    published_posts: int
    leads: int
    pix_generated: int
    purchases: int
    revenue: Decimal
    pix_to_paid_rate: float | None
    lead_to_purchase_rate: float | None
    average_ticket: Decimal | None
    participation_amount: Decimal
    accepted_percent: Decimal | None = None
    pending_acceptance: bool = True
    bot_revenue: Decimal = Decimal("0.00")
    bot_sales: int = 0
    bot_leads: int = 0
    bot_pix: int = 0
    commission_received: Decimal = Decimal("0.00")
    # SharkBot + Falcon Bot together, so a sale in either bot shows up.
    total_revenue: Decimal = Decimal("0.00")
    total_sales: int = 0
    total_ticket: Decimal | None = None
    today_revenue: Decimal = Decimal("0.00")
    withdrawn: Decimal = Decimal("0.00")
    balance: Decimal = Decimal("0.00")


class AffiliatesResponse(BaseModel):
    period: str
    period_label: str
    time_zone: str
    basis: str
    totals_revenue: Decimal
    totals_participation: Decimal
    rows: list[AffiliateRow]


class AffiliateAccountRow(BaseModel):
    account_id: UUID
    username: str
    status: str
    follower_count: int | None
    published_posts: int
    video_views_lifetime: int | None
    videos_with_views: int


class AffiliateDetail(AffiliateRow):
    accounts: list[AffiliateAccountRow]
    purchases_without_amount: int
    leads_per_purchase: float | None
    criteria: dict[str, str]


# --------------------------------------------------------------- invite
@router.get("/invite", response_model=InviteResponse)
async def get_invite(access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> InviteResponse:
    code = await ensure_invite_code(db, user)
    await db.commit()
    return _invite(code)


@router.post("/invite/rotate", response_model=InviteResponse, dependencies=[Depends(require_csrf)])
async def rotate_invite(access: OwnerAccess, user: AuthenticatedUser, db: DbSession) -> InviteResponse:
    # Existing affiliates stay linked; only new sign-ups need the new code.
    code = await ensure_invite_code(db, user, rotate=True)
    await db.commit()
    return _invite(code)


def _invite(code: str, terms: str | None = None, percent: Decimal | None = None) -> InviteResponse:
    base = get_settings().public_base_url.rstrip("/")
    url = f"{base}/register?invite={code}" + (f"&terms={terms}" if terms else "")
    return InviteResponse(code=code, invite_url=url, percent=percent)


@router.post("/invite/link", response_model=InviteResponse, dependencies=[Depends(require_csrf)])
async def invite_link_with_percent(
    payload: InviteLinkRequest, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> InviteResponse:
    """Invite link that already carries the commission: whoever signs up through it
    agrees to that percent on the sign-up screen, so no separate acceptance is asked."""
    code = await ensure_invite_code(db, user)
    await db.commit()
    percent = payload.percent.quantize(Decimal("0.01"))
    return _invite(code, make_invite_terms(user.id, percent), percent)


@router.get("/invite/preview", response_model=InvitePreview)
async def invite_preview(code: str, db: DbSession, terms: str | None = None) -> InvitePreview:
    """Public: what the sign-up screen shows before the person creates the account."""
    chief = await find_chief(db, code)
    parsed = read_invite_terms(terms) if terms else None
    percent = parsed[1] if parsed and parsed[0] == chief.id else None
    return InvitePreview(chief_name=chief.full_name, percent=percent)


@router.post("/join", response_model=MyChiefResponse, dependencies=[Depends(require_csrf)])
async def join_with_code(
    payload: JoinRequest, user: AuthenticatedUser, db: DbSession
) -> MyChiefResponse:
    if not await owns_workspace(db, user.id):
        raise HTTPException(status_code=403, detail="Somente usuários com operação própria podem usar um código.")
    try:
        await link_affiliate(db, payload.code, user)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Você já está vinculado a um chefe.") from None
    return await _my_chief(db, user)


async def _my_chief(db: AsyncSession, user: User) -> MyChiefResponse:
    row = (
        await db.execute(
            select(Affiliation, User)
            .join(User, User.id == Affiliation.chief_user_id)
            .where(Affiliation.affiliate_user_id == user.id)
        )
    ).first()
    if row is None:
        return MyChiefResponse(
            chief_name=None, chief_nickname=None, participation_percent=None, since=None, has_chief=False
        )
    link, chief = row
    return MyChiefResponse(
        chief_name=chief.full_name,
        chief_nickname=chief.nickname,
        participation_percent=link.participation_percent,
        since=link.created_at.isoformat(),
        has_chief=True,
    )


@router.get("/me", response_model=MyChiefResponse)
async def my_chief(user: AuthenticatedUser, db: DbSession) -> MyChiefResponse:
    """What an affiliate may know: who their chief is and the agreed percentage."""
    return await _my_chief(db, user)


# --------------------------------------------------------------- chief view
async def _affiliate_workspace(db: AsyncSession, affiliate_user_id: UUID) -> Workspace | None:
    return await db.scalar(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            WorkspaceMember.user_id == affiliate_user_id,
            WorkspaceMember.role == "OWNER",
            WorkspaceMember.status == "ACTIVE",
            Workspace.owner_id == affiliate_user_id,
        )
        .order_by(Workspace.created_at)
        .limit(1)
    )


async def _row_for(db: AsyncSession, link: Affiliation, user: User, start, end) -> AffiliateRow:
    workspace = await _affiliate_workspace(db, user.id)
    accounts_total = accounts_connected = published = 0
    metrics = None
    if workspace is not None:
        accounts_total = (
            await db.scalar(
                select(func.count(InstagramAccount.id)).where(InstagramAccount.workspace_id == workspace.id)
            )
            or 0
        )
        accounts_connected = (
            await db.scalar(
                select(func.count(InstagramAccount.id)).where(
                    InstagramAccount.workspace_id == workspace.id, InstagramAccount.status == "connected"
                )
            )
            or 0
        )
        published_at = func.coalesce(InstagramPublicationJob.published_at, InstagramPublicationJob.updated_at)
        published = (
            await db.scalar(
                select(func.count(InstagramPublicationJob.id))
                .join(InstagramAccount, InstagramAccount.id == InstagramPublicationJob.account_id)
                .where(
                    InstagramAccount.workspace_id == workspace.id,
                    InstagramPublicationJob.status == "published",
                    *window(published_at, start, end),
                )
            )
            or 0
        )
        metrics = await compute_shark_metrics(db, workspace.id, start, end)
    revenue = metrics.revenue if metrics else Decimal("0.00")
    percent = link.participation_percent
    return AffiliateRow(
        id=link.id,
        user_id=user.id,
        full_name=user.full_name,
        nickname=user.nickname,
        participation_percent=percent,
        since=link.created_at.isoformat(),
        accounts_total=accounts_total,
        accounts_connected=accounts_connected,
        published_posts=published,
        leads=metrics.leads if metrics else 0,
        pix_generated=metrics.pix_generated if metrics else 0,
        purchases=metrics.purchases if metrics else 0,
        revenue=revenue,
        pix_to_paid_rate=metrics.pix_to_paid_rate if metrics else None,
        lead_to_purchase_rate=metrics.lead_to_purchase_rate if metrics else None,
        average_ticket=metrics.average_ticket if metrics else None,
        participation_amount=(revenue * percent / Decimal(100)).quantize(Decimal("0.01")),
        accepted_percent=link.participation_percent,
        pending_acceptance=False,
        **(await _bot_numbers(db, workspace.id if workspace else None, link.chief_user_id, start, end)),
        **(await _money_numbers(db, user, workspace.id if workspace else None, start, end)),
    )


async def _money_numbers(db: AsyncSession, user: User, workspace_id, start, end) -> dict:
    """Combined revenue (period and today, Brazil time), what was withdrawn and what is left."""
    if workspace_id is None:
        return {}
    from app.finance.router import _revenue_between
    from app.wallet.router import balances

    gross, _net, sales, _no_amount, _bot = await _revenue_between(db, workspace_id, start, end)
    now = utc_now()
    today_start = now.astimezone(BRAZIL_TIME_ZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    today, *_ = await _revenue_between(db, workspace_id, today_start.astimezone(timezone.utc), now)
    wallet = await balances(db, user, workspace_id)
    gross = Decimal(gross or 0).quantize(Decimal("0.01"))
    return {
        "total_revenue": gross,
        "total_sales": int(sales),
        "total_ticket": (gross / sales).quantize(Decimal("0.01")) if sales else None,
        "today_revenue": Decimal(today or 0).quantize(Decimal("0.01")),
        "withdrawn": wallet["withdrawn"],
        "balance": wallet["available"],
    }


async def _bot_numbers(db: AsyncSession, workspace_id, chief_user_id, start, end) -> dict:
    """Falcon Bot paid sales of the affiliate and the split the chief received from them."""
    if workspace_id is None:
        return {}
    row = (
        await db.execute(
            select(
                func.count(TgOrder.id),
                func.coalesce(func.sum(TgOrder.amount), 0),
                func.coalesce(
                    func.sum(case((TgOrder.split_chief_user_id == chief_user_id, TgOrder.split_amount), else_=0)), 0
                ),
            ).where(
                TgOrder.workspace_id == workspace_id, TgOrder.status == "paid",
                TgOrder.paid_at >= start, TgOrder.paid_at < end, not_hidden_bot(TgOrder.bot_id),
            )
        )
    ).one()
    leads = await db.scalar(
        select(func.count(TgLead.id)).where(
            TgLead.workspace_id == workspace_id, TgLead.created_at >= start, TgLead.created_at < end,
            not_hidden_bot(TgLead.bot_id),
        )
    )
    pix = await db.scalar(
        select(func.count(TgOrder.id)).where(
            TgOrder.workspace_id == workspace_id, TgOrder.created_at >= start, TgOrder.created_at < end,
            not_hidden_bot(TgOrder.bot_id),
        )
    )
    return {
        "bot_leads": int(leads or 0),
        "bot_pix": int(pix or 0),
        "bot_sales": int(row[0]),
        "bot_revenue": Decimal(row[1] or 0).quantize(Decimal("0.01")),
        "commission_received": Decimal(row[2] or 0).quantize(Decimal("0.01")),
    }


@router.get("", response_model=AffiliatesResponse)
async def list_affiliates(
    access: OwnerAccess,
    user: AuthenticatedUser,
    db: DbSession,
    period: AnalyticsPeriod = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    user_calendar: bool = False,
) -> AffiliatesResponse:
    zone = await user_time_zone(db, access.workspace.id, user.id) if user_calendar else None
    start, end = period_bounds(period, start_date, end_date, utc_now(), zone)
    links = (
        await db.execute(
            select(Affiliation, User)
            .join(User, User.id == Affiliation.affiliate_user_id)
            .where(Affiliation.chief_user_id == user.id, Affiliation.status == "ACTIVE")
            .order_by(User.full_name, Affiliation.id)
        )
    ).all()
    rows = [await _row_for(db, link, affiliate, start, end) for link, affiliate in links]
    return AffiliatesResponse(
        period=period,
        period_label=period_label(start, end, zone),
        time_zone=zone.key if zone else APP_TIME_ZONE_NAME,
        basis=PARTICIPATION_BASIS,
        totals_revenue=sum((row.total_revenue for row in rows), Decimal("0.00")),
        totals_participation=sum((row.participation_amount for row in rows), Decimal("0.00")),
        rows=rows,
    )


async def _own_link(db: AsyncSession, user: User, affiliation_id: UUID) -> tuple[Affiliation, User]:
    row = (
        await db.execute(
            select(Affiliation, User)
            .join(User, User.id == Affiliation.affiliate_user_id)
            .where(Affiliation.id == affiliation_id, Affiliation.chief_user_id == user.id)
        )
    ).first()
    if row is None:  # also hides other chiefs' affiliates
        raise HTTPException(status_code=404, detail="Filiado não encontrado.")
    return row


@router.get("/{affiliation_id}", response_model=AffiliateDetail)
async def affiliate_detail(
    affiliation_id: UUID,
    access: OwnerAccess,
    user: AuthenticatedUser,
    db: DbSession,
    period: AnalyticsPeriod = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
) -> AffiliateDetail:
    start, end = period_bounds(period, start_date, end_date, utc_now())
    link, affiliate = await _own_link(db, user, affiliation_id)
    base = await _row_for(db, link, affiliate, start, end)
    workspace = await _affiliate_workspace(db, affiliate.id)
    accounts: list[AffiliateAccountRow] = []
    metrics = None
    if workspace is not None:
        metrics = await compute_shark_metrics(db, workspace.id, start, end)
        published_at = func.coalesce(InstagramPublicationJob.published_at, InstagramPublicationJob.updated_at)
        posts = dict(
            (
                await db.execute(
                    select(InstagramPublicationJob.account_id, func.count(InstagramPublicationJob.id))
                    .where(
                        InstagramPublicationJob.status == "published",
                        *window(published_at, start, end),
                    )
                    .group_by(InstagramPublicationJob.account_id)
                )
            ).all()
        )
        views = {
            account_id: (total, with_views)
            for account_id, total, with_views in (
                await db.execute(
                    select(
                        InstagramMediaInsight.account_id,
                        func.sum(InstagramMediaInsight.views),
                        func.count(InstagramMediaInsight.id).filter(InstagramMediaInsight.views.is_not(None)),
                    )
                    .where(
                        InstagramMediaInsight.workspace_id == workspace.id,
                        InstagramMediaInsight.media_type == "VIDEO",
                        *window(InstagramMediaInsight.posted_at, start, end),
                    )
                    .group_by(InstagramMediaInsight.account_id)
                )
            ).all()
        }
        for account in (
            await db.scalars(
                select(InstagramAccount)
                .where(InstagramAccount.workspace_id == workspace.id)
                .order_by(InstagramAccount.username)
            )
        ).all():
            total, with_views = views.get(account.id, (None, 0))
            accounts.append(
                AffiliateAccountRow(
                    account_id=account.id,
                    username=account.username,
                    status=account.status,
                    follower_count=account.follower_count,
                    published_posts=posts.get(account.id, 0),
                    video_views_lifetime=int(total) if total is not None else None,
                    videos_with_views=with_views,
                )
            )
    return AffiliateDetail(
        **base.model_dump(),
        accounts=accounts,
        purchases_without_amount=metrics.purchases_without_amount if metrics else 0,
        leads_per_purchase=metrics.leads_per_purchase if metrics else None,
        criteria={**CRITERIA, "participation": PARTICIPATION_BASIS},
    )


@router.patch(
    "/{affiliation_id}", response_model=AffiliateRow, dependencies=[Depends(require_csrf)]
)
async def set_participation(
    affiliation_id: UUID,
    payload: PercentRequest,
    access: OwnerAccess,
    user: AuthenticatedUser,
    db: DbSession,
    period: AnalyticsPeriod = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
) -> AffiliateRow:
    link, affiliate = await _own_link(db, user, affiliation_id)
    if link.participation_percent != payload.participation_percent:
        link.participation_percent = payload.participation_percent
        link.accepted_percent = payload.participation_percent
        link.accepted_at = utc_now()
        await notify_user(
            db, affiliate.id, "partner-commission", "Comissão da sociedade atualizada",
            f"{user.full_name} definiu sua comissão em {float(payload.participation_percent):g}%. "
            "O novo percentual vale para as próximas vendas.", "/",
        )
    await db.commit()
    start, end = period_bounds(period, start_date, end_date, utc_now())
    return await _row_for(db, link, affiliate, start, end)


@router.delete("/{affiliation_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def remove_affiliate(
    affiliation_id: UUID, access: OwnerAccess, user: AuthenticatedUser, db: DbSession
) -> None:
    link, _affiliate = await _own_link(db, user, affiliation_id)
    await db.delete(link)
    await db.commit()
