import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import AuthenticatedUser, DbSession, OwnerAccess, WorkspaceMemberAccess, require_csrf
from app.core.nickname import nickname_key
from app.core.security import WorkspaceRole, hash_password
from app.models import (
    CollaboratorPayment,
    InstagramAccount,
    User,
    WorkspaceMember,
)
from app.schemas.collaborators import (
    CollaboratorCreateRequest,
    CollaboratorDashboardResponse,
    CollaboratorPaymentActionResponse,
    CollaboratorPaymentResponse,
    CollaboratorRankingItem,
    CollaboratorRankingResponse,
    CollaboratorReportItem,
    CollaboratorUpdateRequest,
    CollaboratorsResponse,
)

router = APIRouter(prefix="/api/collaborators", tags=["Collaborators"])
logger = logging.getLogger(__name__)
_BRAZIL_TIME_ZONE = ZoneInfo("America/Sao_Paulo")
_CENT = Decimal("0.01")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _month_bounds(value: datetime) -> tuple[datetime, datetime, date]:
    local_now = value.astimezone(_BRAZIL_TIME_ZONE)
    month_start_date = local_now.date().replace(day=1)
    next_month = (
        date(month_start_date.year + 1, 1, 1)
        if month_start_date.month == 12
        else date(month_start_date.year, month_start_date.month + 1, 1)
    )
    start = datetime.combine(
        month_start_date, time.min, tzinfo=_BRAZIL_TIME_ZONE
    ).astimezone(timezone.utc)
    end = datetime.combine(next_month, time.min, tzinfo=_BRAZIL_TIME_ZONE).astimezone(
        timezone.utc
    )
    return start, end, month_start_date


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    next_day = day + timedelta(days=1)
    start = datetime.combine(day, time.min, tzinfo=_BRAZIL_TIME_ZONE).astimezone(
        timezone.utc
    )
    end = datetime.combine(next_day, time.min, tzinfo=_BRAZIL_TIME_ZONE).astimezone(
        timezone.utc
    )
    return start, end


async def _connections_between(
    db: DbSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> int:
    return int(
        await db.scalar(
            select(func.count(InstagramAccount.id)).where(
                InstagramAccount.workspace_id == workspace_id,
                InstagramAccount.connected_by_user_id == user_id,
                InstagramAccount.first_connected_at >= start,
                InstagramAccount.first_connected_at < end,
            )
        )
        or 0
    )


async def _recent_daily_counts(
    db: DbSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime,
) -> list[int]:
    today = now.astimezone(_BRAZIL_TIME_ZONE).date()
    counts = []
    for offset in range(6, -1, -1):
        start, end = _day_bounds(today - timedelta(days=offset))
        counts.append(
            await _connections_between(db, workspace_id, user_id, start, end)
        )
    return counts


async def _member_report(
    db: DbSession,
    workspace_id: uuid.UUID,
    member: WorkspaceMember,
    user: User,
    now: datetime,
) -> CollaboratorReportItem:
    today = now.astimezone(_BRAZIL_TIME_ZONE).date()
    today_start, today_end = _day_bounds(today)
    month_start, month_end, month_date = _month_bounds(now)
    connections_today = await _connections_between(
        db, workspace_id, user.id, today_start, today_end
    )
    connections_month = await _connections_between(
        db, workspace_id, user.id, month_start, month_end
    )
    paid_month = Decimal(
        str(
            await db.scalar(
                select(func.coalesce(func.sum(CollaboratorPayment.amount), 0)).where(
                    CollaboratorPayment.workspace_id == workspace_id,
                    CollaboratorPayment.workspace_member_id == member.id,
                    CollaboratorPayment.period_start == month_date,
                )
            )
            or 0
        )
    ).quantize(_CENT)
    rate = Decimal(str(member.rate_per_connection)).quantize(_CENT)
    monthly_bonus = Decimal(str(member.monthly_bonus)).quantize(_CENT)
    earnings_month = (rate * connections_month).quantize(_CENT)
    bonus_earned = (
        monthly_bonus
        if member.monthly_connection_goal > 0
        and connections_month >= member.monthly_connection_goal
        else Decimal("0.00")
    )
    earnings_month += bonus_earned
    due_month = max(earnings_month - paid_month, Decimal("0.00")).quantize(_CENT)
    earnings_today = (rate * connections_today).quantize(_CENT)
    projected_month = (
        rate * member.monthly_connection_goal + monthly_bonus
        if member.monthly_connection_goal > 0
        else Decimal("0.00")
    ).quantize(_CENT)
    return CollaboratorReportItem(
        member_id=member.id,
        user_id=user.id,
        full_name=user.full_name,
        nickname=user.nickname,
        email=user.email,
        rate_per_connection=rate,
        daily_connection_goal=member.daily_connection_goal,
        monthly_connection_goal=member.monthly_connection_goal,
        monthly_bonus=monthly_bonus,
        connections_today=connections_today,
        connections_month=connections_month,
        earnings_today=earnings_today,
        earnings_month=earnings_month,
        paid_month=paid_month,
        due_month=due_month,
        projected_month=projected_month,
        recent_days=await _recent_daily_counts(db, workspace_id, user.id, now),
    )


def _dashboard_response(report: CollaboratorReportItem) -> CollaboratorDashboardResponse:
    daily_progress = (
        min(round(report.connections_today / report.daily_connection_goal * 100), 100)
        if report.daily_connection_goal
        else 0
    )
    monthly_progress = (
        min(round(report.connections_month / report.monthly_connection_goal * 100), 100)
        if report.monthly_connection_goal
        else 0
    )
    return CollaboratorDashboardResponse(
        full_name=report.full_name,
        nickname=report.nickname,
        avatar_url=None,
        rate_per_connection=report.rate_per_connection,
        daily_connection_goal=report.daily_connection_goal,
        monthly_connection_goal=report.monthly_connection_goal,
        monthly_bonus=report.monthly_bonus,
        connections_today=report.connections_today,
        connections_month=report.connections_month,
        earnings_today=report.earnings_today,
        earnings_month=report.earnings_month,
        paid_month=report.paid_month,
        due_month=report.due_month,
        projected_month=report.projected_month,
        daily_progress=daily_progress,
        monthly_progress=monthly_progress,
        recent_days=report.recent_days,
    )


@router.get("/dashboard", response_model=CollaboratorDashboardResponse)
async def collaborator_dashboard(
    user: AuthenticatedUser,
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> CollaboratorDashboardResponse:
    if access.membership.role != WorkspaceRole.COLLABORATOR.value:
        raise HTTPException(status_code=403, detail="Collaborator dashboard only.")
    report = await _member_report(db, access.workspace.id, access.membership, user, _utc_now())
    response = _dashboard_response(report)
    response.avatar_url = user.avatar_url
    return response


@router.get("", response_model=CollaboratorsResponse)
async def list_collaborators(
    access: OwnerAccess,
    db: DbSession,
) -> CollaboratorsResponse:
    now = _utc_now()
    result = await db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(
            WorkspaceMember.workspace_id == access.workspace.id,
            WorkspaceMember.role == WorkspaceRole.COLLABORATOR.value,
            WorkspaceMember.status == "ACTIVE",
        )
        .order_by(User.full_name, User.id)
    )
    collaborators = [
        await _member_report(db, access.workspace.id, member, user, now)
        for member, user in result
    ]
    today_start, today_end = _day_bounds(now.astimezone(_BRAZIL_TIME_ZONE).date())
    owner_connections_today = await _connections_between(
        db,
        access.workspace.id,
        access.workspace.owner_id,
        today_start,
        today_end,
    )
    return CollaboratorsResponse(
        collaborators=collaborators,
        owner_connections_today=owner_connections_today,
        team_connections_today=sum(item.connections_today for item in collaborators),
    )


@router.post(
    "",
    response_model=CollaboratorsResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_collaborator(
    payload: CollaboratorCreateRequest,
    access: OwnerAccess,
    db: DbSession,
) -> CollaboratorsResponse:
    email = str(payload.email).casefold()
    existing_user = await db.scalar(select(User.id).where(func.lower(User.email) == email))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Este e-mail já possui acesso.")
    nickname_exists = await db.scalar(
        select(User.id).where(
            User.nickname_normalized == nickname_key(payload.nickname)
        )
    )
    if nickname_exists is not None:
        raise HTTPException(status_code=409, detail="Este apelido já está em uso.")

    user = User(
        email=email,
        nickname=payload.nickname,
        nickname_normalized=nickname_key(payload.nickname),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=access.workspace.id,
            user_id=user.id,
            role=WorkspaceRole.COLLABORATOR.value,
            status="ACTIVE",
            rate_per_connection=payload.rate_per_connection,
            daily_connection_goal=payload.daily_connection_goal,
            monthly_connection_goal=payload.monthly_connection_goal,
            monthly_bonus=payload.monthly_bonus,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="O e-mail ou apelido informado já está em uso.",
        ) from None
    return await list_collaborators(access, db)


@router.get("/ranking", response_model=CollaboratorRankingResponse)
async def collaborator_ranking(
    access: OwnerAccess,
    db: DbSession,
    month: str | None = None,
) -> CollaboratorRankingResponse:
    current_month_start = _month_bounds(_utc_now())[2]
    try:
        month_date = (
            date.fromisoformat(f"{month}-01") if month else current_month_start
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Informe o mês no formato YYYY-MM.",
        ) from None
    if month_date.day != 1:
        raise HTTPException(status_code=422, detail="Informe o mês no formato YYYY-MM.")
    next_month_date = (
        date(month_date.year + 1, 1, 1)
        if month_date.month == 12
        else date(month_date.year, month_date.month + 1, 1)
    )
    month_start = datetime.combine(
        month_date, time.min, tzinfo=_BRAZIL_TIME_ZONE
    ).astimezone(timezone.utc)
    month_end = datetime.combine(
        next_month_date, time.min, tzinfo=_BRAZIL_TIME_ZONE
    ).astimezone(timezone.utc)
    result = await db.execute(
        select(
            User.id,
            User.full_name,
            User.nickname,
            func.count(InstagramAccount.id).label("connections"),
        )
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .outerjoin(
            InstagramAccount,
            (InstagramAccount.connected_by_user_id == User.id)
            & (InstagramAccount.workspace_id == access.workspace.id)
            & (InstagramAccount.first_connected_at >= month_start)
            & (InstagramAccount.first_connected_at < month_end),
        )
        .where(
            WorkspaceMember.workspace_id == access.workspace.id,
            WorkspaceMember.role == WorkspaceRole.COLLABORATOR.value,
        )
        .group_by(User.id, User.full_name, User.nickname)
        .order_by(func.count(InstagramAccount.id).desc(), User.nickname, User.id)
    )
    ranking = [
        CollaboratorRankingItem(
            user_id=user_id,
            full_name=full_name,
            nickname=nickname,
            connections=connections,
            position=position,
        )
        for position, (user_id, full_name, nickname, connections) in enumerate(
            result, start=1
        )
    ]
    return CollaboratorRankingResponse(
        month=month_date.strftime("%Y-%m"),
        total_connections=sum(item.connections for item in ranking),
        collaborators=ranking,
    )


@router.patch(
    "/{member_id}",
    response_model=CollaboratorReportItem,
    dependencies=[Depends(require_csrf)],
)
async def update_collaborator(
    member_id: uuid.UUID,
    payload: CollaboratorUpdateRequest,
    access: OwnerAccess,
    db: DbSession,
) -> CollaboratorReportItem:
    member = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == access.workspace.id,
            WorkspaceMember.role == WorkspaceRole.COLLABORATOR.value,
        )
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    member.rate_per_connection = payload.rate_per_connection
    member.daily_connection_goal = payload.daily_connection_goal
    member.monthly_connection_goal = payload.monthly_connection_goal
    member.monthly_bonus = payload.monthly_bonus
    await db.commit()
    user = await db.get(User, member.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário do colaborador não encontrado.")
    return await _member_report(db, access.workspace.id, member, user, _utc_now())


@router.post(
    "/{member_id}/payout",
    response_model=CollaboratorPaymentActionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def register_monthly_payout(
    member_id: uuid.UUID,
    user: AuthenticatedUser,
    access: OwnerAccess,
    db: DbSession,
) -> CollaboratorPaymentActionResponse:
    member = await db.scalar(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == access.workspace.id,
            WorkspaceMember.role == WorkspaceRole.COLLABORATOR.value,
        )
        .with_for_update()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    collaborator_user = await db.get(User, member.user_id)
    if collaborator_user is None:
        raise HTTPException(status_code=404, detail="Usuário do colaborador não encontrado.")

    now = _utc_now()
    report = await _member_report(
        db, access.workspace.id, member, collaborator_user, now
    )
    if report.due_month <= 0:
        raise HTTPException(status_code=409, detail="Não há saldo pendente para pagar.")
    _, _, month_date = _month_bounds(now)
    payment = CollaboratorPayment(
        workspace_id=access.workspace.id,
        workspace_member_id=member.id,
        paid_by_user_id=user.id,
        amount=report.due_month,
        period_start=month_date,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return CollaboratorPaymentActionResponse(
        message="Pagamento registrado.",
        payment=CollaboratorPaymentResponse(
            id=payment.id,
            amount=payment.amount,
            period_start=payment.period_start,
            paid_at=payment.paid_at,
        ),
    )
