"""Fun engagement pushes built on real connection data.

- Streak: consecutive local days meeting the daily connection goal (or >= 1
  connection when no goal). Warns at 20h when today would break it.
- Personal record: today's connections beat every previous day (prev best >= 3).
- Ranking: "X passed you" (max 1/hour) and "you are #1 today" (1/day).
- Nightly summary at 22h: connections, views and money of the day.

All pushes reuse ``MilestoneNotification`` rows for de-duplication.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import WorkspaceRole
from app.core.time import BRAZIL_TIME_ZONE
from app.models import (
    InstagramAccount,
    MilestoneNotification,
    PushSubscription,
    SharkTransaction,
    User,
    WorkspaceMember,
)
from app.notifications.goals import format_views

logger = logging.getLogger(__name__)
STREAK_WARN_HOUR = 20
SUMMARY_HOUR = 22
RECORD_MIN_PREVIOUS_BEST = 3
HISTORY_DAYS = 365

# workspace_id -> (local_date, {user_id: (position, connections)})
_rank_snapshots: dict[uuid.UUID, tuple[date, dict[uuid.UUID, tuple[int, int]]]] = {}


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def local_today(now: datetime) -> date:
    return now.astimezone(BRAZIL_TIME_ZONE).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=BRAZIL_TIME_ZONE).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=BRAZIL_TIME_ZONE).astimezone(timezone.utc)
    return start, end


@dataclass
class EngagementStats:
    today: int
    goal: int
    streak: int  # including today when today is already met
    streak_before_today: int
    best_previous: int
    best_previous_date: date | None
    is_record_today: bool

    @property
    def met_today(self) -> bool:
        return self.today >= max(self.goal, 1)

    @property
    def missing_today(self) -> int:
        return max(max(self.goal, 1) - self.today, 0)


def compute_stats(counts: dict[date, int], today: date, goal: int) -> EngagementStats:
    target = max(goal, 1)
    streak_before = 0
    day = today - timedelta(days=1)
    while counts.get(day, 0) >= target:
        streak_before += 1
        day -= timedelta(days=1)
    today_count = counts.get(today, 0)
    previous = {d: c for d, c in counts.items() if d < today}
    best_date = max(previous, key=lambda d: (previous[d], d)) if previous else None
    best = previous[best_date] if best_date else 0
    return EngagementStats(
        today=today_count,
        goal=goal,
        streak=streak_before + (1 if today_count >= target else 0),
        streak_before_today=streak_before,
        best_previous=best,
        best_previous_date=best_date,
        is_record_today=best >= RECORD_MIN_PREVIOUS_BEST and today_count > best,
    )


async def daily_connection_counts(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> dict[date, int]:
    since = now - timedelta(days=HISTORY_DAYS)
    stamps = (
        await db.scalars(
            select(InstagramAccount.first_connected_at).where(
                InstagramAccount.workspace_id == workspace_id,
                InstagramAccount.connected_by_user_id == user_id,
                InstagramAccount.first_connected_at >= since,
            )
        )
    ).all()
    counts: dict[date, int] = {}
    for stamp in stamps:
        if stamp is None:
            continue
        day = _aware(stamp).astimezone(BRAZIL_TIME_ZONE).date()
        counts[day] = counts.get(day, 0) + 1
    return counts


async def user_stats(db: AsyncSession, workspace_id, user_id, now: datetime) -> EngagementStats:
    goal = await db.scalar(
        select(WorkspaceMember.daily_connection_goal).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
        )
    )
    counts = await daily_connection_counts(db, workspace_id, user_id, now)
    return compute_stats(counts, local_today(now), int(goal or 0))


async def today_ranking(db: AsyncSession, workspace_id, now: datetime) -> list[tuple[uuid.UUID, str, int]]:
    start, end = day_bounds(local_today(now))
    rows = (
        await db.execute(
            select(
                WorkspaceMember.user_id,
                WorkspaceMember.role,
                User.nickname,
                func.count(InstagramAccount.id),
            )
            .join(User, User.id == WorkspaceMember.user_id)
            .outerjoin(
                InstagramAccount,
                (InstagramAccount.connected_by_user_id == WorkspaceMember.user_id)
                & (InstagramAccount.workspace_id == workspace_id)
                & (InstagramAccount.first_connected_at >= start)
                & (InstagramAccount.first_connected_at < end),
            )
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.status == "ACTIVE",
                WorkspaceMember.role.in_((WorkspaceRole.OWNER.value, WorkspaceRole.COLLABORATOR.value)),
            )
            .group_by(WorkspaceMember.user_id, WorkspaceMember.role, User.nickname)
        )
    ).all()
    named = [
        (user_id, "o chefe" if role == WorkspaceRole.OWNER.value else (nickname or "Alguém"), int(count))
        for user_id, role, nickname, count in rows
    ]
    named.sort(key=lambda item: (-item[2], item[1].lower(), str(item[0])))
    return named


def ranking_events(
    previous: dict[uuid.UUID, tuple[int, int]],
    current: list[tuple[uuid.UUID, str, int]],
) -> dict[uuid.UUID, tuple[str, str | None]]:
    """{user: ("top", None) | ("passed", overtaker_name)} comparing two snapshots."""
    events: dict[uuid.UUID, tuple[str, str | None]] = {}
    if not previous:
        return events
    for index, (user_id, _name, connections) in enumerate(current):
        position = index + 1
        before = previous.get(user_id)
        if before is None:
            continue
        if position == 1 and before[0] != 1 and connections > 0:
            events[user_id] = ("top", None)
            continue
        if position > before[0] and index > 0:
            above_id, above_name, above_connections = current[index - 1]
            above_before = previous.get(above_id)
            if (
                above_connections > connections
                and above_before is not None
                and above_before[1] <= before[1]
            ):
                events[user_id] = ("passed", above_name)
    return events


def _choice(options: list[tuple[str, str]]) -> tuple[str, str]:
    return random.choice(options)


def streak_message(stats: EngagementStats) -> tuple[str, str]:
    faltam = stats.missing_today
    dias = stats.streak_before_today
    word = "conexão" if faltam == 1 else "conexões"
    return _choice(
        [
            (f"😱 Sua sequência de {dias} dias tá em risco!", f"Faltam {faltam} {word} hoje pra não perder o foguinho 🔥"),
            (f"🔥 {dias} dias seguidos… vai parar agora?", f"Só {faltam} {word} e a sequência continua viva 💪"),
            (f"⏰ Corre! Sequência de {dias} dias", f"Faltam {faltam} {word}. O foguinho tá apagando 🕯️"),
        ]
    )


def record_message(stats: EngagementStats) -> tuple[str, str]:
    return _choice(
        [
            (f"🏆 Novo recorde! {stats.today} conexões hoje", f"Seu melhor dia até agora (antes: {stats.best_previous}) 🚀"),
            (f"🥇 Recorde pessoal: {stats.today} conexões!", "Hoje você se superou. Print e manda pro grupo 📸"),
            (f"📈 {stats.today} conexões, recorde batido!", "O você de ontem tá com inveja 😏"),
        ]
    )


def ranking_message(kind: str, name: str | None) -> tuple[str, str]:
    if kind == "top":
        return _choice(
            [
                ("👑 Você é o número 1 de hoje!", "Topo do ranking. Agora segura a coroa 😎"),
                ("🥇 Primeiro lugar no ranking do dia!", "Todo mundo tá correndo atrás de você 🏃💨"),
            ]
        )
    return _choice(
        [
            (f"⚠️ {name} te passou no ranking do dia", "Vai deixar? 😤"),
            (f"😳 {name} acabou de te ultrapassar", "Bora recuperar a posição 🏎️"),
            (f"👀 {name} tá na sua frente agora", "Uma conexão e você volta pro jogo 🎮"),
        ]
    )


def summary_message(
    connections: int, views: int | None, money: Decimal | None, money_label: str = "a receber"
) -> tuple[str, str]:
    parts = [f"{connections} {'conexão' if connections == 1 else 'conexões'}"]
    if views is not None:
        parts.append(f"{format_views(views)} views")
    if money is not None and money > 0:
        parts.append(f"R$ {money:.2f}".replace(".", ",") + f" {money_label}")
    closer = random.choice(
        ["Dormiu rico 😴💰", "Amanhã tem mais 🚀", "Descansa que você mereceu 🛌", "Boa noite, máquina 🤖🌙"]
        if connections or (views or 0) > 0
        else ["Amanhã é um novo dia 🌅", "Recarrega a bateria e volta com tudo 🔋"]
    )
    title = random.choice(["🌙 Resumo do seu dia", "📊 Fechamento do dia", "🌙 Seu dia em uma frase"])
    return title, f"Hoje: {', '.join(parts)}. {closer}"


async def _claim(db: AsyncSession, workspace_id, user_id, day: date, kind: str, threshold: int, value: int) -> MilestoneNotification | None:
    exists = await db.scalar(
        select(MilestoneNotification.id).where(
            MilestoneNotification.workspace_id == workspace_id,
            MilestoneNotification.user_id == user_id,
            MilestoneNotification.local_date == day,
            MilestoneNotification.kind == kind,
            MilestoneNotification.threshold == threshold,
        )
    )
    if exists is not None:
        return None
    marker = MilestoneNotification(
        workspace_id=workspace_id, user_id=user_id, local_date=day, kind=kind, threshold=threshold, value=value
    )
    try:
        async with db.begin_nested():
            db.add(marker)
            await db.flush()
    except IntegrityError:
        return None
    await db.commit()
    return marker


async def run_engagement_tick(
    db: AsyncSession,
    now: datetime,
    *,
    client,
    keys_getter,
    push_to,
    views_today,
) -> int:
    """Called from the milestones tick for every user that has push enabled."""
    from app.notifications.milestones import _Scope  # local import avoids a cycle

    today = local_today(now)
    hour = now.astimezone(BRAZIL_TIME_ZONE).hour
    start, end = day_bounds(today)
    pairs = (
        await db.execute(
            select(PushSubscription.workspace_id, PushSubscription.user_id, WorkspaceMember.role)
            .join(
                WorkspaceMember,
                (WorkspaceMember.workspace_id == PushSubscription.workspace_id)
                & (WorkspaceMember.user_id == PushSubscription.user_id),
            )
            .where(WorkspaceMember.status == "ACTIVE")
            .distinct()
        )
    ).all()
    subscribed = {(w, u): r for w, u, r in pairs}
    total = 0

    async def send(workspace_id, user_id, title, body, url, marker, topic) -> int:
        subs = (
            await db.scalars(
                select(PushSubscription).where(
                    PushSubscription.workspace_id == workspace_id, PushSubscription.user_id == user_id
                )
            )
        ).all()
        keys = await keys_getter()
        if keys is None or not subs:
            return 0
        delivered, transient = await push_to(
            db, subs, {"title": title, "body": body, "url": url, "tag": f"fun-{marker.kind}"}, keys, client, topic
        )
        if delivered == 0 and transient:
            await db.delete(marker)
        else:
            marker.delivered = delivered
        await db.commit()
        return delivered

    # Ranking events per workspace (only workspaces with someone subscribed).
    for workspace_id in {w for w, _u in subscribed}:
        try:
            current = await today_ranking(db, workspace_id, now)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.warning("Ranking snapshot failed (%s).", type(exc).__name__)
            continue
        snapshot = _rank_snapshots.get(workspace_id)
        previous = snapshot[1] if snapshot and snapshot[0] == today else {}
        _rank_snapshots[workspace_id] = (
            today,
            {user_id: (index + 1, count) for index, (user_id, _n, count) in enumerate(current)},
        )
        for user_id, (kind, name) in ranking_events(previous, current).items():
            if (workspace_id, user_id) not in subscribed:
                continue
            marker = await _claim(
                db, workspace_id, user_id, today, f"rank_{kind}", 1 if kind == "top" else hour, 0
            )
            if marker is None:
                continue
            title, body = ranking_message(kind, name)
            total += await send(workspace_id, user_id, title, body, "/feature/ranking", marker, f"rank{kind}")

    for (workspace_id, user_id), role in subscribed.items():
        try:
            stats = await user_stats(db, workspace_id, user_id, now)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.warning("Engagement stats failed (%s).", type(exc).__name__)
            continue
        if stats.is_record_today:
            marker = await _claim(db, workspace_id, user_id, today, "record", 0, stats.today)
            if marker is not None:
                title, body = record_message(stats)
                total += await send(workspace_id, user_id, title, body, "/dashboard", marker, "record")
        if hour >= STREAK_WARN_HOUR and stats.streak_before_today >= 2 and not stats.met_today:
            marker = await _claim(db, workspace_id, user_id, today, "streak_warn", 0, stats.streak_before_today)
            if marker is not None:
                title, body = streak_message(stats)
                total += await send(workspace_id, user_id, title, body, "/dashboard", marker, "streak")
        if hour >= SUMMARY_HOUR:
            marker = await _claim(db, workspace_id, user_id, today, "summary", 0, stats.today)
            if marker is None:
                continue
            try:
                views = await views_today(db, _Scope(workspace_id, user_id), now, start)
            except Exception:  # noqa: BLE001
                views = None
            money: Decimal | None = None
            if role == WorkspaceRole.OWNER.value:
                amount = await db.scalar(
                    select(func.coalesce(func.sum(SharkTransaction.amount), 0)).where(
                        SharkTransaction.workspace_id == workspace_id,
                        SharkTransaction.status == "paid",
                        SharkTransaction.paid_at >= start,
                        SharkTransaction.paid_at < end,
                    )
                )
                money = Decimal(str(amount or 0))
            else:
                member = await db.scalar(
                    select(WorkspaceMember).where(
                        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
                    )
                )
                rate = Decimal(str(member.rate_per_connection if member else 0))
                amount = await db.scalar(
                    select(
                        func.coalesce(
                            func.sum(func.coalesce(InstagramAccount.collaborator_rate_at_connection, rate)), 0
                        )
                    ).where(
                        InstagramAccount.workspace_id == workspace_id,
                        InstagramAccount.connected_by_user_id == user_id,
                        InstagramAccount.first_connected_at >= start,
                        InstagramAccount.first_connected_at < end,
                    )
                )
                money = Decimal(str(amount or 0))
            title, body = summary_message(
                stats.today, views, money, "em vendas" if role == WorkspaceRole.OWNER.value else "a receber"
            )
            total += await send(workspace_id, user_id, title, body, "/dashboard", marker, "summary")
    return total
