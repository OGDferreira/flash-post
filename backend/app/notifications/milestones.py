"""Fun milestone pushes: views, posts and sales reached in one local day.

Each (workspace, user, day, kind, threshold) is sent at most once. When a user
jumps several thresholds between two checks, only the highest one is pushed
(the lower ones are marked as done so they never arrive late).
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import WorkspaceRole
from app.models import (
    DailyViewsGoal,
    InstagramAccount,
    InstagramPublicationJob,
    MilestoneNotification,
    PushSubscription,
    SharkTransaction,
    WorkspaceMember,
)
from app.notifications.goals import (
    _account_views_today,
    goal_scope_accounts,
    local_day_window,
    resolve_time_zone,
)
from app.notifications.webpush import VapidKeys, WebPushError, get_vapid_keys, send_web_push

logger = logging.getLogger(__name__)

VIEW_THRESHOLDS = (10_000, 50_000, 100_000, 500_000, 1_000_000)
POST_THRESHOLDS = (1_000, 5_000, 10_000, 15_000)
SALE_THRESHOLDS = (10, 50, 100, 500)

# {threshold: [(title, body), ...]} — one variant is picked at random.
MESSAGES: dict[str, dict[int, list[tuple[str, str]]]] = {
    "views": {
        10_000: [
            ("👀 10 mil visualizações hoje!", "Já dá pra comprar o pastel na feira 🥟😋"),
            ("👀 10 mil views hoje!", "O caldo de cana também tá pago 🥤 Bora pra mais!"),
            ("🔥 10 mil visualizações!", "Primeiro pastel garantido. Agora vem o de queijo 🧀"),
        ],
        50_000: [
            ("🚀 50 mil visualizações hoje!", "Tá ficando famoso no bairro, hein? 😎"),
            ("🚀 50 mil views!", "Sua mãe já tá mostrando pras vizinhas 👵📱"),
            ("📈 50 mil visualizações!", "O algoritmo começou a te notar 👀"),
        ],
        100_000: [
            ("💯 100 mil visualizações hoje!", "Você já aprendeu a viralizar 🧠🔥"),
            ("💯 100 mil views!", "Pode colocar 'influencer' na bio 😏"),
            ("🔥 100 mil visualizações!", "O algoritmo tá comendo na sua mão 🍽️"),
        ],
        500_000: [
            ("🤯 500 mil visualizações hoje!", "Meio milhão de olhos em você. Arruma o cabelo 💇"),
            ("🌪️ 500 mil views!", "Isso não é post, é furacão 🌀"),
            ("🤯 500 mil visualizações!", "Já pode dar palestra sobre viralizar 🎤"),
        ],
        1_000_000: [
            ("🤑 1 milhão de visualizações em um dia?!", "Dubai te espera 🏝️✈️"),
            ("💎 1 MILHÃO de views hoje!", "Pode ir escolhendo a cor da Lamborghini 🏎️"),
            ("🤑 1 milhão de visualizações!", "O Instagram tá te devendo um troféu 🏆"),
        ],
    },
    "posts": {
        1_000: [
            ("⚡ 1 mil posts hoje!", "A máquina de postar foi ligada 🤖"),
            ("⚡ Mil posts hoje!", "Tá aquecendo os motores 🔥"),
        ],
        5_000: [
            ("🔥 5 mil posts hoje!", "Desse jeito o Instagram vai cair 💥📉"),
            ("🔥 5 mil posts!", "Os servidores da Meta tão suando 🥵"),
        ],
        10_000: [
            ("🧠 10 mil posts hoje!", "Haja memória 💾😵"),
            ("🧠 10 mil posts!", "Alguém chama o TI da Meta 🧑‍💻🚨"),
        ],
        15_000: [
            ("😱 15 mil posts hoje!", "O Zuckerberg tem medo de você 🫣"),
            ("😱 15 mil posts!", "O Zuck já tá ligando pra marcar reunião 📞"),
        ],
    },
    "sales": {
        10: [
            ("💸 10 vendas hoje!", "O caixa começou a cantar 🎶💰"),
            ("💸 10 vendas!", "Pix caindo igual chuva 🌧️💵"),
        ],
        50: [
            ("🤑 50 vendas hoje!", "O banco vai te ligar perguntando o que tá acontecendo 📞😅"),
            ("🤑 50 vendas!", "Já pode chamar o contador 🧾"),
        ],
        100: [
            ("🚨 100 vendas em um dia!", "Vai com calma, quer ficar rico? 😂💰"),
            ("🚨 100 vendas hoje!", "Calma, deixa um pouco pros outros 🤭"),
        ],
        500: [
            ("👑 500 vendas hoje!", "Isso não é venda, é império 🏰💎"),
            ("👑 500 vendas!", "Forbes já tá com sua foto na pauta 📸"),
        ],
    },
}

THRESHOLDS = {"views": VIEW_THRESHOLDS, "posts": POST_THRESHOLDS, "sales": SALE_THRESHOLDS}


@dataclass(frozen=True)
class _Scope:
    workspace_id: uuid.UUID
    user_id: uuid.UUID


def milestone_message(kind: str, threshold: int, rng: random.Random | None = None) -> tuple[str, str]:
    return (rng or random).choice(MESSAGES[kind][threshold])


def new_thresholds(kind: str, value: int, already: set[int]) -> list[int]:
    return [t for t in THRESHOLDS[kind] if value >= t and t not in already]


async def _views_today(db, scope, now, start, cache) -> int | None:
    accounts = await goal_scope_accounts(db, scope, now)  # duck-typed like a goal
    if not accounts or now <= start:
        return None
    values = []
    for account in accounts:
        key = (account.id, start)
        if key not in cache:
            cache[key] = await _account_views_today(account, start, now)
        views, _error = cache[key]
        if views is not None:
            values.append(views)
    return sum(values) if values else None


async def _posts_today(db, scope, role, start, end) -> int:
    query = (
        select(func.count(InstagramPublicationJob.id))
        .join(InstagramAccount, InstagramAccount.id == InstagramPublicationJob.account_id)
        .where(
            InstagramPublicationJob.workspace_id == scope.workspace_id,
            InstagramPublicationJob.status == "published",
            InstagramPublicationJob.published_at >= start,
            InstagramPublicationJob.published_at < end,
        )
    )
    if role != WorkspaceRole.OWNER.value:
        query = query.where(InstagramAccount.connected_by_user_id == scope.user_id)
    return int(await db.scalar(query) or 0)


async def _sales_today(db, scope, start, end) -> int:
    return int(
        await db.scalar(
            select(func.count(SharkTransaction.id)).where(
                SharkTransaction.workspace_id == scope.workspace_id,
                SharkTransaction.status == "paid",
                SharkTransaction.paid_at >= start,
                SharkTransaction.paid_at < end,
            )
        )
        or 0
    )


async def _push(db, subscriptions, payload, keys, client, topic) -> tuple[int, int]:
    delivered = transient = 0
    for subscription in subscriptions:
        result = await send_web_push(
            client,
            endpoint=subscription.endpoint,
            p256dh=subscription.p256dh,
            auth=subscription.auth,
            payload=payload,
            keys=keys,
            topic=topic,
        )
        if result.ok:
            delivered += 1
            subscription.failure_count = 0
            subscription.last_success_at = datetime.now(timezone.utc)
        elif result.gone:
            await db.delete(subscription)
        else:
            transient += 1
            subscription.failure_count += 1
    return delivered, transient


async def _notify(db, scope, day: date, kind: str, value: int, client, keys) -> int:
    already = set(
        (
            await db.scalars(
                select(MilestoneNotification.threshold).where(
                    MilestoneNotification.workspace_id == scope.workspace_id,
                    MilestoneNotification.user_id == scope.user_id,
                    MilestoneNotification.local_date == day,
                    MilestoneNotification.kind == kind,
                )
            )
        ).all()
    )
    pending = new_thresholds(kind, value, already)
    if not pending:
        return 0
    markers = [
        MilestoneNotification(
            workspace_id=scope.workspace_id,
            user_id=scope.user_id,
            local_date=day,
            kind=kind,
            threshold=threshold,
            value=value,
        )
        for threshold in pending
    ]
    try:
        async with db.begin_nested():
            db.add_all(markers)
            await db.flush()
    except IntegrityError:  # another worker got here first
        return 0
    await db.commit()
    subscriptions = (
        await db.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == scope.user_id,
                PushSubscription.workspace_id == scope.workspace_id,
            )
        )
    ).all()
    top = max(pending)
    title, body = milestone_message(kind, top)
    payload = {
        "title": title,
        "body": body,
        "url": "/dashboard",
        "tag": f"milestone-{kind}-{top}-{day.isoformat()}",
    }
    delivered, transient = await _push(
        db, subscriptions, payload, keys, client, f"ms{kind[:1]}{top}"[:32]
    )
    if delivered == 0 and transient:
        await db.execute(
            delete(MilestoneNotification).where(
                MilestoneNotification.id.in_([marker.id for marker in markers])
            )
        )
    else:
        for marker in markers:
            marker.delivered = delivered
    await db.commit()
    return delivered


async def run_milestones_tick(
    db: AsyncSession,
    now: datetime | None = None,
    views_cache: dict | None = None,
) -> int:
    """Check every user that has a push subscription. Returns pushes delivered."""
    now = now or datetime.now(timezone.utc)
    cache = views_cache if views_cache is not None else {}
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
    if not pairs:
        return 0
    keys: VapidKeys | None = None
    total = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        for workspace_id, user_id, role in pairs:
            scope = _Scope(workspace_id, user_id)
            zone_name = await db.scalar(
                select(DailyViewsGoal.timezone).where(
                    DailyViewsGoal.workspace_id == workspace_id, DailyViewsGoal.user_id == user_id
                )
            )
            day, start, end = local_day_window(now, resolve_time_zone(zone_name))
            try:
                values = {
                    "views": await _views_today(db, scope, now, start, cache),
                    "posts": await _posts_today(db, scope, role, start, end),
                    "sales": (
                        await _sales_today(db, scope, start, end)
                        if role == WorkspaceRole.OWNER.value
                        else None
                    ),
                }
            except Exception as exc:  # one bad user must not stop the others
                await db.rollback()
                logger.warning("Milestone check failed (%s).", type(exc).__name__)
                continue
            for kind, value in values.items():
                if value is None or not new_thresholds(kind, value, set()):
                    continue
                if keys is None:
                    try:
                        keys = await get_vapid_keys(db)
                    except (WebPushError, RuntimeError, ValueError) as exc:
                        logger.error("Web Push keys unavailable (%s).", type(exc).__name__)
                        return total
                total += await _notify(db, scope, day, kind, value, client, keys)
    return total
