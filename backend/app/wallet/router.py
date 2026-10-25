"""Wallet: revenue, balance to withdraw, withdrawals and revenue goals.

Money from Flash sales sits in SmokePay: the platform owner's main account
(Super Admin) or each operation's subaccount. The balance shown here is what
the sales left for this user after fees and the partner split. Withdrawals go
straight to SmokePay: a subaccount pays out with POST /api/shops/{ref}/withdraw
(idempotent on our row id), the main wallet with POST /api/withdrawals. The
balance shown is SmokePay's own when reachable. Amounts are checked on the
server, never trusted from the browser.
"""

import logging
import re
import uuid
from datetime import timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.auth.dependencies import AuthenticatedUser, DbSession, SuperAdminUser, require_csrf
from app.core.time import BRAZIL_TIME_ZONE, utc_now
from app.bots import smokepay
from app.core.config import get_settings
from app.models import FinancialWithdrawal, TgOrder, User, Workspace
from app.models import Affiliation
from app.partners.service import owner_workspace, partner_link, shop_ref
from app.wallet import snake_withdrawals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wallet", tags=["Wallet"])
admin_router = APIRouter(prefix="/api/admin/partner-wallets", tags=["platform administration"])

CENT = Decimal("0.01")
MIN_WITHDRAWAL = Decimal("10.00")
GOALS = [Decimal(v) for v in ("10000", "50000", "100000", "500000", "1000000", "5000000", "10000000")]
GOAL_PRIZES = {
    10000: "Pulseira", 50000: "Caneca", 100000: "Placa", 500000: "Placa", 1000000: "Quadro, cordão e pingente de ouro",
    5000000: "Placa Ouro Elite", 10000000: "Placa Diamante",
}


def _brl(value: Decimal) -> str:
    return f"R$ {value:.2f}".replace(".", ",")


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class WithdrawalRequest(BaseModel):
    # None only with ``withdraw_all`` on SnakePay ("MAX": everything available).
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    gateway: Literal["smokepay", "snakepay"] = "smokepay"
    withdraw_all: bool = False
    pix_key_type: Literal["cpf", "cnpj", "email", "phone", "random"] | None = None
    pix_key: str | None = Field(default=None, max_length=140)
    note: str | None = Field(default=None, max_length=240)

    @field_validator("pix_key", "note")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None


def _check_digits(digits: str, weights_from: int) -> int:
    total = sum(int(d) * w for d, w in zip(digits, range(weights_from, 1, -1)))
    return (total * 10 % 11) % 10


def _cnpj_digit(digits: str) -> int:
    weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(digits):]
    rest = sum(int(d) * w for d, w in zip(digits, weights)) % 11
    return 0 if rest < 2 else 11 - rest


def normalize_pix_key(kind: str, key: str) -> str:
    """The key SmokePay should receive, or 422 with what is wrong (a bad key makes the
    Pix fail at the bank and the amount comes back, wasting the 5-minute cooldown)."""
    digits = "".join(c for c in key if c.isdigit())
    if kind == "cpf":
        if len(digits) != 11 or len(set(digits)) == 1 or [_check_digits(digits[:9], 10), _check_digits(digits[:10], 11)] != [int(digits[9]), int(digits[10])]:
            raise HTTPException(status_code=422, detail="CPF inválido: confira os números da chave Pix.")
        return digits
    if kind == "cnpj":
        if len(digits) != 14 or len(set(digits)) == 1 or [_cnpj_digit(digits[:12]), _cnpj_digit(digits[:13])] != [int(digits[12]), int(digits[13])]:
            raise HTTPException(status_code=422, detail="CNPJ inválido: confira os números da chave Pix.")
        return digits
    if kind == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", key):
            raise HTTPException(status_code=422, detail="E-mail inválido para chave Pix.")
        return key.lower()
    if kind == "phone":
        if digits.startswith("55") and len(digits) in (12, 13):
            digits = digits[2:]
        if len(digits) not in (10, 11):
            raise HTTPException(status_code=422, detail="Telefone inválido: use DDD + número, ex.: 11 91234-5678.")
        return f"+55{digits}"
    try:
        return str(uuid.UUID(key))
    except ValueError:
        raise HTTPException(status_code=422, detail="Chave aleatória inválida: cole a chave completa (32 letras e números com traços).") from None


async def _workspace_for(db, user: User) -> Workspace:
    workspace = await owner_workspace(db, user.id)
    if workspace is None:
        raise HTTPException(status_code=403, detail="A carteira é da operação do dono da conta.")
    return workspace


async def balances(db, user: User, workspace_id: uuid.UUID) -> dict:
    """What the sales left for this user (after fee and split) and what is free to withdraw."""
    # SnakePay sales are paid out by SnakePay itself (split to each account): only
    # SmokePay money sits in the Flash wallet.
    smoke = TgOrder.gateway != "snakepay"
    own = await db.scalar(
        select(func.coalesce(func.sum(func.coalesce(TgOrder.partner_net, TgOrder.net_amount, TgOrder.amount)), 0)).where(
            TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", smoke
        )
    )
    commissions = await db.scalar(
        select(func.coalesce(func.sum(TgOrder.split_amount), 0)).where(
            TgOrder.split_chief_user_id == user.id, TgOrder.status == "paid", smoke
        )
    )
    commission_paid = await db.scalar(
        select(func.coalesce(func.sum(TgOrder.split_amount), 0)).where(
            TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", TgOrder.split_chief_user_id.is_not(None), smoke,
            TgOrder.seller_hidden.is_(False),
        )
    )
    sums: dict[tuple[str, str], object] = {
        (gateway, status): total
        for gateway, status, total in (
            await db.execute(
                select(FinancialWithdrawal.gateway, FinancialWithdrawal.status, func.coalesce(func.sum(FinancialWithdrawal.amount), 0))
                .where(FinancialWithdrawal.workspace_id == workspace_id)
                .group_by(FinancialWithdrawal.gateway, FinancialWithdrawal.status)
            )
        ).all()
    }

    def total(statuses: tuple[str, ...], gateway: str | None = None) -> Decimal:
        return sum((_money(v) for (g, st), v in sums.items() if st in statuses and gateway in (None, g)), Decimal("0.00"))

    earned = _money(own) + _money(commissions)
    smoke_out = total(("PAID", "PROCESSING", "REQUESTED"), "smokepay")
    return {
        "earned": earned,
        "commissions_received": _money(commissions),
        "commission_paid": _money(commission_paid),
        "withdrawn": total(("PAID",)),  # every gateway
        "pending": total(("PROCESSING", "REQUESTED")),
        "available": max(Decimal("0.00"), earned - smoke_out),  # SmokePay estimate
    }


async def snakepay_breakdown(db, user: User, workspace_id: uuid.UUID) -> dict[str, Decimal]:
    """What SnakePay already sent to this user's own account: the shares of their sales, the
    commissions they earned and, for the Super Admin (the account that charges), the platform
    and per-sale fees that stay in it. Flash revenue never counts the last two."""
    paid_snake = (TgOrder.status == "paid", TgOrder.gateway == "snakepay")
    own = await db.scalar(
        select(func.coalesce(func.sum(func.coalesce(TgOrder.partner_net, TgOrder.net_amount)), 0)).where(
            TgOrder.workspace_id == workspace_id, *paid_snake
        )
    )
    commissions = await db.scalar(
        select(func.coalesce(func.sum(TgOrder.split_amount), 0)).where(TgOrder.split_chief_user_id == user.id, *paid_snake)
    )
    fees = Decimal("0.00")
    if user.platform_role == "SUPER_ADMIN":
        fees = _money(await db.scalar(
            select(func.coalesce(func.sum(TgOrder.platform_fee), 0)).where(TgOrder.workspace_id != workspace_id, *paid_snake)
        ))
    return {"sales": _money(own), "commissions": _money(commissions), "fees": fees}


async def _falcon_fees(db) -> dict:
    """Super Admin: what the per-sale Flash fee (R$ 0,40 by default) brought in, month and today."""
    now = utc_now()
    local = now.astimezone(BRAZIL_TIME_ZONE)
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    async def between(start) -> tuple[Decimal, int]:
        total, count = (await db.execute(
            select(func.coalesce(func.sum(TgOrder.transaction_fee), 0), func.count(TgOrder.id)).where(
                TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.transaction_fee > 0
            )
        )).one()
        return _money(total), int(count)

    month, month_count = await between(month_start)
    today, today_count = await between(day_start)
    return {
        "falcon_fees_month": float(month), "falcon_fees_month_count": month_count,
        "falcon_fees_today": float(today), "falcon_fees_today_count": today_count,
    }


async def month_revenue(db, workspace_id: uuid.UUID) -> Decimal:
    """Gross revenue (SharkBot + Flash) since the 1st of the current month, Brazil time."""
    return (await month_revenue_by_bot(db, workspace_id))[0]


def _month_start():
    now = utc_now()
    return now.astimezone(BRAZIL_TIME_ZONE).replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc), now


async def month_commissions(db, workspace_id: uuid.UUID) -> Decimal:
    """Commissions the workspace's owner received this month from partners' sales (any gateway)."""
    from app.bots.hidden import not_hidden_bot

    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        return Decimal("0.00")
    start, now = _month_start()
    return _money(await db.scalar(
        select(func.coalesce(func.sum(TgOrder.split_amount), 0)).where(
            TgOrder.split_chief_user_id == workspace.owner_id, TgOrder.status == "paid",
            TgOrder.paid_at >= start, TgOrder.paid_at < now, not_hidden_bot(TgOrder.bot_id, seller=False),
        )
    ))


async def month_revenue_by_bot(db, workspace_id: uuid.UUID) -> tuple[Decimal, Decimal, Decimal]:
    """(total, SharkBot, Flash) since the 1st of the current month, Brazil time. Flash =
    the operation's own sales plus the commissions received from partners' sales."""
    from app.finance.router import _revenue_between

    start, now = _month_start()
    gross, _net, _sales, _no_amount, flash = await _revenue_between(db, workspace_id, start, now)
    commissions = await month_commissions(db, workspace_id)
    shark = _money(gross) - _money(flash)
    return _money(gross) + commissions, shark, _money(flash) + commissions


def goal_progress(revenue: Decimal) -> dict:
    target = next((goal for goal in GOALS if revenue < goal), GOALS[-1])
    reached = [int(goal) for goal in GOALS if revenue >= goal]
    return {
        "target": target,
        "percent": round(float(min(revenue / target, Decimal(1)) * 100), 1),
        "prize": GOAL_PRIZES[int(target)],
        "reached": reached,
        "goals": [{"amount": int(g), "prize": GOAL_PRIZES[int(g)], "reached": revenue >= g} for g in GOALS],
    }


# ------------------------------------------------------------------ award photos

AWARD_IMAGES_KEY = "award_images"
# Flash award art shipped with the site (frontend/public/premiacoes); a Super Admin upload replaces it.
DEFAULT_AWARD_IMAGES = {
    10000: "/premiacoes/flashbot-10k.webp", 50000: "/premiacoes/flashbot-50k.webp",
    100000: "/premiacoes/flashbot-100k.webp", 500000: "/premiacoes/flashbot-500k.webp",
    1000000: "/premiacoes/flashbot-1m.webp", 5000000: "/premiacoes/flashbot-5m.webp",
    10000000: "/premiacoes/flashbot-10m.webp",
}
_signed_cache: dict[str, tuple[float, str]] = {}


async def award_image_paths(db) -> dict[int, str]:
    from app.models import SystemSetting

    row = await db.get(SystemSetting, AWARD_IMAGES_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    return {int(k): v for k, v in value.items() if str(k).isdigit() and isinstance(v, str) and v}


async def award_image_urls(db) -> dict[int, str]:
    """Award photo per goal: the Super Admin's upload, else the default Flash art."""
    return {**DEFAULT_AWARD_IMAGES, **await custom_award_image_urls(db)}


async def custom_award_image_urls(db) -> dict[int, str]:
    """Signed URLs for the uploaded award photos, cached in process (they last 4h)."""
    import time

    from app.instagram.storage import SupabaseStorage

    urls: dict[int, str] = {}
    for amount, path in (await award_image_paths(db)).items():
        cached = _signed_cache.get(path)
        if cached and cached[0] > time.time():
            urls[amount] = cached[1]
            continue
        try:
            url = await SupabaseStorage.from_settings().create_signed_url(path)
        except Exception:
            continue
        _signed_cache[path] = (time.time() + 3 * 3600, url)
        urls[amount] = url
    return urls


def _goals_out(revenue: Decimal, images: dict[int, str]) -> dict:
    goal = goal_progress(revenue)
    current = int(goal["target"]) if revenue < GOALS[-1] else int(GOALS[-1])
    return {
        **goal,
        "target": float(goal["target"]),
        "goals": [{**g, "image_url": images.get(g["amount"]), "current": g["amount"] == current} for g in goal["goals"]],
    }


@router.get("/goals")
async def goals(user: AuthenticatedUser, db: DbSession) -> dict:
    """Revenue goals and award photos for the dashboard."""
    workspace = await owner_workspace(db, user.id)
    if workspace is None:
        return {"available": False}
    _total, _shark, revenue = await month_revenue_by_bot(db, workspace.id)  # goals count Flash sales only
    return {"available": True, "month_revenue": float(revenue), **_goals_out(revenue, await award_image_urls(db))}


def _withdrawal_out(item: FinancialWithdrawal, owner: str | None = None) -> dict:
    return {
        "gateway": item.gateway,
        "id": str(item.id), "amount": float(item.amount), "status": item.status, "note": item.note,
        "pix_key_type": item.pix_key_type, "pix_key": item.pix_key, "owner": owner,
        "fee": float(item.fee) if item.fee is not None else None,
        "e2e_id": item.gateway_e2e_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "processed_at": item.processed_at.isoformat() if item.processed_at else None,
    }


@router.get("/summary")
async def summary(user: AuthenticatedUser, db: DbSession) -> dict:
    """Small payload for the floating revenue badge."""
    workspace = await owner_workspace(db, user.id)
    if workspace is None:
        return {"available": False}
    # The pill shows Flash's revenue only (SharkBot sales stay out of it).
    _total, _shark, revenue = await month_revenue_by_bot(db, workspace.id)
    return {"available": True, "month_revenue": float(revenue), **{k: float(v) if isinstance(v, Decimal) else v for k, v in goal_progress(revenue).items() if k in ("target", "percent", "prize")}}


def _shop_for(user: User, workspace: Workspace) -> str | None:
    """None = the platform owner's main SmokePay wallet."""
    return None if user.platform_role == "SUPER_ADMIN" else shop_ref(workspace.id)


async def _gateway_balance(shop: str | None) -> Decimal | None:
    try:
        if shop is None:
            return await smokepay.main_balance()
        value = await smokepay.shop_balance(shop)
        return value if value is not None else Decimal("0.00")
    except smokepay.SmokepayError:
        return None


async def _reconcile(db, workspace_id: uuid.UUID, shop: str | None) -> None:
    """Settle PROCESSING withdrawals with SmokePay's final status, and keep the Pix receipt
    (E2E id) of every recent payout."""
    waiting = list(
        await db.scalars(
            select(FinancialWithdrawal).where(
                FinancialWithdrawal.workspace_id == workspace_id,
                FinancialWithdrawal.gateway == "smokepay",
                FinancialWithdrawal.gateway_withdrawal_id.is_not(None),
                (FinancialWithdrawal.status == "PROCESSING")
                | (
                    FinancialWithdrawal.gateway_e2e_id.is_(None)
                    & (FinancialWithdrawal.status == "PAID")
                    & (FinancialWithdrawal.created_at > utc_now() - timedelta(days=30))
                ),
            )
        )
    )
    if not waiting:
        return
    try:
        remote = {p.withdrawal_id: p for p in await smokepay.withdrawals(shop)}
    except smokepay.SmokepayError:
        return
    for item in waiting:
        payout = remote.get(item.gateway_withdrawal_id or "")
        if payout is None:
            continue
        if payout.fee is not None:
            item.fee = payout.fee
        if payout.e2e_id:
            item.gateway_e2e_id = payout.e2e_id[:64]
        if item.status != "PROCESSING":
            continue
        if payout.status == "completed":
            item.status, item.processed_at = "PAID", utc_now()
        elif payout.status == "failed":
            item.status, item.processed_at = "FAILED", utc_now()
            item.note = (f"SmokePay: {payout.failure_reason}" if payout.failure_reason else "Falhou na SmokePay")[:240]
    await db.commit()


async def _is_partner(db, user: User) -> bool:
    """Partners see what they billed, the net free to withdraw and what was paid out;
    the withdrawals themselves (and their history) belong to the Super Admin."""
    return user.platform_role != "SUPER_ADMIN" and await partner_link(db, user.id) is not None


async def _wallet_numbers(db, user: User, workspace: Workspace, shop: str | None) -> dict:
    """``user`` = the workspace's owner (whose wallet this is)."""
    await _reconcile(db, workspace.id, shop)
    try:
        await snake_withdrawals.reconcile(db, workspace)
    except Exception:  # a status check must never break the wallet
        await db.rollback()
        logger.exception("SnakePay withdrawal check failed")
    balance = await balances(db, user, workspace.id)
    gateway = await _gateway_balance(shop)
    out = {k: float(v) for k, v in balance.items()}
    if gateway is not None:  # SmokePay's own number wins over our estimate
        out["available"] = float(gateway)
    fee = get_settings().smokepay_withdraw_fee
    out["withdraw_fee"] = float(fee)
    # what can actually leave: SmokePay debits the fee from the balance too
    out["withdrawable"] = float(max(Decimal("0.00"), Decimal(str(out["available"])) - fee))
    out["balance_source"] = "smokepay" if gateway is not None else "estimate"
    # One card per gateway in the "Sacar" pop-up.
    snake_received = sum((await snakepay_breakdown(db, user, workspace.id)).values(), Decimal("0.00"))
    snake_balance = await snake_withdrawals.estimated_balance(db, workspace.id, snake_received)
    snake_ready = await snake_withdrawals.credentials(db, workspace) is not None
    out["gateways"] = [
        {"gateway": "smokepay", "available": out["available"], "withdrawable": out["withdrawable"], "fee": float(fee),
         "ready": True, "estimated": gateway is None, "min": float(MIN_WITHDRAWAL)},
    ]
    if snake_received > 0 or snake_ready:
        out["gateways"].append({
            "gateway": "snakepay", "available": float(snake_balance), "withdrawable": float(snake_balance), "fee": None,
            "ready": snake_ready, "estimated": True, "min": float(snake_withdrawals.cashout.MIN_AMOUNT),
        })
    out["withdrawals_blocked"] = await withdrawals_blocked_for(db, user)
    return out


async def _history(db, workspace_id: uuid.UUID, limit: int = 50) -> list[dict]:
    rows = await db.scalars(
        select(FinancialWithdrawal)
        .where(FinancialWithdrawal.workspace_id == workspace_id)
        .order_by(FinancialWithdrawal.created_at.desc())
        .limit(limit)
    )
    return [_withdrawal_out(item) for item in rows]


@router.get("")
async def wallet(user: AuthenticatedUser, db: DbSession) -> dict:
    workspace = await _workspace_for(db, user)
    shop = _shop_for(user, workspace)
    revenue, shark_revenue, flash_revenue = await month_revenue_by_bot(db, workspace.id)
    numbers = await _wallet_numbers(db, user, workspace, shop)
    is_partner = await _is_partner(db, user)
    snake = await snakepay_breakdown(db, user, workspace.id)
    if is_partner:
        numbers.pop("commission_paid", None)
    return {
        "is_main_account": shop is None,
        "is_partner": is_partner,
        "shop_ref": shop,
        "month_revenue": float(revenue),
        "month_shark_revenue": float(shark_revenue),
        "snakepay_received": float(sum(snake.values(), Decimal("0.00"))),
        "snakepay_sales": float(snake["sales"]),
        "snakepay_commissions": float(snake["commissions"]),
        "snakepay_fees": float(snake["fees"]),
        "month_flash_revenue": float(flash_revenue),
        "month_commissions": float(await month_commissions(db, workspace.id)),
        **(await _falcon_fees(db) if user.platform_role == "SUPER_ADMIN" else {}),
        "goal": _goals_out(flash_revenue, await award_image_urls(db)),  # goals count Flash sales only
        **numbers,
        "min_withdrawal": float(MIN_WITHDRAWAL),
        "withdrawals": await _history(db, workspace.id),
    }


def _gateway_message(exc: smokepay.SmokepayError) -> tuple[int, str]:
    if exc.status == 429:
        minutes = max(1, round((exc.cooldown_seconds or 300) / 60))
        return 429, f"A SmokePay só permite um saque a cada 5 minutos. Tente de novo em {minutes} min."
    if exc.status == 403:
        if exc.requires_kyc:
            return 422, "A conta SmokePay precisa concluir a verificação de identidade (KYC) para sacar."
        return 422, "A SmokePay recusou o saque: confira se a chave de API tem permissão de saque."
    if exc.status == 404:
        return 422, "Sua subconta ainda não recebeu nenhuma venda, então não há saldo para sacar."
    if exc.status == 400 and "insuficiente" in (exc.detail or "").lower():
        return 422, "Saldo insuficiente: a SmokePay desconta a taxa de saque do saldo. Use o botão MAX, que já desconta a taxa."
    if exc.status == 400:
        return 422, f"A SmokePay recusou o saque: {exc.detail or 'dados inválidos'}."
    if exc.detail:  # say exactly what SmokePay answered (e.g. "Falha no gateway PIX")
        return 502, f"A SmokePay recusou o saque: {exc.detail}. Confira a chave Pix e tente de novo em 5 minutos."
    return 502, "A SmokePay não conseguiu processar o saque agora. Tente de novo em alguns minutos."


WITHDRAWALS_BLOCKED_KEY = "withdrawals_blocked"


async def all_withdrawals_blocked(db) -> bool:
    from app.models import SystemSetting

    setting = await db.get(SystemSetting, WITHDRAWALS_BLOCKED_KEY)
    return bool(setting and isinstance(setting.value, dict) and setting.value.get("blocked"))


async def withdrawals_blocked_for(db, user: User) -> bool:
    """The Super Admin blocks one user's withdrawals or everyone's; never their own."""
    if user.platform_role == "SUPER_ADMIN":
        return False
    return bool(user.withdrawals_blocked) or await all_withdrawals_blocked(db)


@router.post("/withdrawals", status_code=201, dependencies=[Depends(require_csrf)])
async def request_withdrawal(payload: WithdrawalRequest, user: AuthenticatedUser, db: DbSession) -> dict:
    # Partners withdraw their own subaccount too (owner's decision, 2026-10-19); the
    # Super Admin still sees every payout in "Saques dos sócios".
    if await withdrawals_blocked_for(db, user):
        raise HTTPException(status_code=403, detail="Os saques estão bloqueados pelo administrador.")
    workspace = await _workspace_for(db, user)
    return await _dispatch(db, user, user, workspace, payload)


async def _dispatch(db, actor: User, owner: User, workspace: Workspace, payload: WithdrawalRequest) -> dict:
    """``actor`` asked for it; ``owner`` owns the money (the same, or a partner for the Super Admin)."""
    if payload.gateway == "snakepay":
        if not payload.pix_key or not payload.pix_key_type:
            raise HTTPException(status_code=422, detail="Informe a chave Pix que vai receber.")
        pix_key = normalize_pix_key(payload.pix_key_type, payload.pix_key)
        if not payload.withdraw_all and payload.amount is None:
            raise HTTPException(status_code=422, detail="Informe o valor do saque.")
        received = sum((await snakepay_breakdown(db, owner, workspace.id)).values(), Decimal("0.00"))
        estimate = await snake_withdrawals.estimated_balance(db, workspace.id, received)
        item = await snake_withdrawals.withdraw(
            db, actor, workspace, amount=None if payload.withdraw_all else payload.amount.quantize(CENT),
            pix_key=pix_key, key_type=payload.pix_key_type, estimate=estimate,
        )
        await db.refresh(item)
        return _withdrawal_out(item)
    if payload.amount is None:
        raise HTTPException(status_code=422, detail="Informe o valor do saque.")
    return await _withdraw(db, actor, workspace, _shop_for(owner, workspace), payload)


async def _withdraw(db, user: User, workspace: Workspace, shop: str | None, payload: WithdrawalRequest) -> dict:
    """Pays out ``workspace``'s SmokePay balance; ``user`` is who asked for it."""
    amount = payload.amount.quantize(CENT)
    if shop is not None and amount < MIN_WITHDRAWAL:
        raise HTTPException(status_code=422, detail=f"O saque mínimo é R$ {MIN_WITHDRAWAL:.2f}".replace(".", ",") + ".")
    if not payload.pix_key or not payload.pix_key_type:
        raise HTTPException(status_code=422, detail="Informe a chave Pix que vai receber.")
    pix_key = normalize_pix_key(payload.pix_key_type, payload.pix_key)
    if await db.scalar(
        select(FinancialWithdrawal.id).where(
            FinancialWithdrawal.workspace_id == workspace.id, FinancialWithdrawal.status == "PROCESSING",
            FinancialWithdrawal.gateway == "smokepay", FinancialWithdrawal.gateway_withdrawal_id.is_(None),
            FinancialWithdrawal.created_at > utc_now() - timedelta(minutes=10),
        )
    ):
        raise HTTPException(status_code=409, detail="Há um saque em andamento. Aguarde a confirmação.")
    try:
        available = await (smokepay.main_balance() if shop is None else smokepay.shop_balance(shop))
    except smokepay.SmokepayNotConfigured:
        raise HTTPException(status_code=503, detail="Saque automático não configurado no servidor.") from None
    except smokepay.SmokepayError as exc:
        status, message = _gateway_message(exc)
        raise HTTPException(status_code=status, detail=message) from None
    fee = get_settings().smokepay_withdraw_fee
    if amount + fee > (available or Decimal("0.00")):
        most = max(Decimal("0.00"), (available or Decimal("0.00")) - fee)
        raise HTTPException(
            status_code=422,
            detail=f"A SmokePay desconta {_brl(fee)} de taxa do saldo: dá para sacar até {_brl(most)}.",
        )

    # Saved first: its id is the idempotency key SmokePay uses for subaccounts.
    item = FinancialWithdrawal(
        workspace_id=workspace.id, created_by_user_id=user.id, amount=amount, note=payload.note,
        status="PROCESSING", pix_key_type=payload.pix_key_type, pix_key=pix_key,
    )
    db.add(item)
    await db.commit()
    try:
        payout = await smokepay.withdraw(
            amount=amount, pix_key=pix_key, pix_key_type=payload.pix_key_type,
            correlation_id=str(item.id), shop_ref=shop, sub_shop_id=str(workspace.owner_id),
        )
    except smokepay.SmokepayError as exc:
        if exc.status == 0:  # no answer: the money may have left; keep it pending, never resend
            item.note = "Sem resposta da SmokePay; confira o extrato antes de tentar de novo."
            await db.commit()
            raise HTTPException(status_code=502, detail=item.note) from None
        status, message = _gateway_message(exc)
        logger.warning("SmokePay withdrawal refused: HTTP %s %s", exc.status, exc.detail or "")
        item.status, item.processed_at, item.note = "FAILED", utc_now(), message[:240]
        await db.commit()
        raise HTTPException(status_code=status, detail=message) from None
    item.gateway_withdrawal_id = payout.withdrawal_id or None
    item.fee = payout.fee
    item.amount = payout.amount if payout.amount > 0 else amount  # SmokePay may cap it to the limit/balance
    if payout.status == "completed":
        item.status, item.processed_at = "PAID", utc_now()
    elif payout.status == "failed":
        item.status, item.processed_at = "FAILED", utc_now()
    item.processed_by_user_id = user.id
    await db.commit()
    await db.refresh(item)
    return _withdrawal_out(item)


# ------------------------------------------------------------------ Super Admin: partners' wallets


async def _partner_workspace(db, user_id: uuid.UUID) -> tuple[User, Workspace]:
    link = await partner_link(db, user_id)
    partner = await db.get(User, user_id)
    workspace = await owner_workspace(db, user_id) if link else None
    if link is None or partner is None or workspace is None:
        raise HTTPException(status_code=404, detail="Sócio não encontrado.")
    return partner, workspace


@admin_router.get("")
async def partner_wallets(_admin: SuperAdminUser, db: DbSession) -> dict:
    """Every partner's billing, net balance free to withdraw, payouts and history."""
    links = list(await db.scalars(select(Affiliation).where(Affiliation.status == "ACTIVE")))
    users = {
        u.id: u
        for u in await db.scalars(
            select(User).where(User.id.in_({l.affiliate_user_id for l in links} | {l.chief_user_id for l in links}))
        )
    } if links else {}
    items = []
    for link in links:
        partner = users.get(link.affiliate_user_id)
        workspace = await owner_workspace(db, link.affiliate_user_id)
        if partner is None or workspace is None:
            continue
        numbers = await _wallet_numbers(db, partner, workspace, shop_ref(workspace.id))
        chief = users.get(link.chief_user_id)
        items.append({
            "withdrawals_blocked": bool(partner.withdrawals_blocked),
            "user_id": str(partner.id),
            "name": partner.full_name,
            "email": partner.email,
            "chief": chief.full_name if chief else None,
            "shop_ref": shop_ref(workspace.id),
            "month_revenue": float(await month_revenue(db, workspace.id)),
            **numbers,
            "withdrawals": await _history(db, workspace.id, limit=20),
        })
    items.sort(key=lambda item: item["available"], reverse=True)
    return {"items": items, "min_withdrawal": float(MIN_WITHDRAWAL), "withdrawals_blocked": await all_withdrawals_blocked(db)}


@admin_router.get("/{user_id}/gateway-withdrawals")
async def partner_gateway_withdrawals(user_id: uuid.UUID, _admin: SuperAdminUser, db: DbSession) -> dict:
    """What SmokePay itself recorded for this partner's subaccount: status, destination key,
    Pix receipt (E2E) and failure reason of each payout. For support when a Pix "did not arrive"."""
    _partner, workspace = await _partner_workspace(db, user_id)
    try:
        payouts = await smokepay.withdrawals(shop_ref(workspace.id))
    except smokepay.SmokepayError as exc:
        status, message = _gateway_message(exc)
        raise HTTPException(status_code=status, detail=message) from None
    return {
        "items": [
            {
                "id": p.withdrawal_id, "amount": float(p.amount), "fee": float(p.fee) if p.fee is not None else None,
                "status": p.status, "pix_key_type": p.pix_key_type, "pix_key": p.pix_key, "e2e_id": p.e2e_id,
                "failure_reason": p.failure_reason, "processed_at": p.processed_at,
            }
            for p in payouts
        ]
    }


@admin_router.post("/{user_id}/withdrawals", status_code=201, dependencies=[Depends(require_csrf)])
async def partner_withdrawal(
    user_id: uuid.UUID, payload: WithdrawalRequest, admin: SuperAdminUser, db: DbSession
) -> dict:
    partner, workspace = await _partner_workspace(db, user_id)
    return await _dispatch(db, admin, partner, workspace, payload)  # the Super Admin is never blocked
