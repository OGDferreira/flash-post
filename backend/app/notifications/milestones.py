"""Fun milestone pushes built from real data.

Daily (per user, local day): views, published posts and paid sales.
Per account (forever): followers reached.

Every threshold is sent at most once. When several are crossed between two
checks only the highest is pushed; the lower ones are marked as done. Texts
are templates ({valor}, {conta}, {nome}) that a super admin can override in the
``milestone_messages`` system setting.
"""

from __future__ import annotations

import logging
import random
import time as monotonic_time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.core.security import WorkspaceRole
from app.instagram.oauth import fetch_instagram_profile_metrics
from app.models import (
    AccountFollowerMilestone,
    DailyViewsGoal,
    InstagramAccount,
    InstagramPublicationJob,
    MilestoneNotification,
    PushSubscription,
    SharkTransaction,
    SystemSetting,
    User,
    WorkspaceMember,
)
from app.notifications.goals import (
    _account_views_today,
    format_views,
    goal_scope_accounts,
    local_day_window,
    resolve_time_zone,
)
from app.notifications.webpush import VapidKeys, WebPushError, get_vapid_keys, send_web_push

logger = logging.getLogger(__name__)

MESSAGES_SETTING_KEY = "milestone_messages"
FOLLOWERS_REFRESH_SECONDS = 3600
_last_followers_refresh = 0.0

THRESHOLDS: dict[str, tuple[int, ...]] = {
    "views": (10_000, 50_000, 100_000, 500_000, 1_000_000),
    "posts": (1_000, 5_000, 10_000, 15_000),
    "sales": (10, 50, 100, 500),
    "followers": (1_000, 5_000, 10_000, 50_000, 100_000),
}
KIND_LABELS = {
    "views": "Visualizações no dia",
    "posts": "Posts publicados no dia",
    "sales": "Vendas pagas no dia",
    "followers": "Seguidores de uma conta",
}
PLACEHOLDERS = {
    "{valor}": "número real (ex.: 12.340)",
    "{conta}": "@ da conta (só seguidores)",
    "{nome}": "apelido do usuário",
}


def _m(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"title": title, "body": body} for title, body in pairs]


DEFAULT_MESSAGES: dict[str, dict[int, list[dict[str, str]]]] = {
    "views": {
        10_000: _m(
            ("👀 {valor} visualizações hoje!", "Já dá pra comprar o pastel na feira 🥟😋"),
            ("👀 {valor} views hoje!", "O caldo de cana também tá pago 🥤 Bora pra mais!"),
            ("🔥 {valor} visualizações!", "Primeiro pastel garantido. Agora vem o de queijo 🧀"),
            ("🍿 {valor} views hoje, {nome}!", "Já tem plateia. Faz a pipoca que o show começou 🎬"),
        ),
        50_000: _m(
            ("🚀 {valor} visualizações hoje!", "Tá ficando famoso no bairro, hein? 😎"),
            ("🚀 {valor} views!", "Sua mãe já tá mostrando pras vizinhas 👵📱"),
            ("📈 {valor} visualizações!", "O algoritmo começou a te notar 👀"),
            ("🎯 {valor} views hoje!", "Já dá pra pagar a pizza de sexta 🍕"),
        ),
        100_000: _m(
            ("💯 {valor} visualizações hoje!", "Você já aprendeu a viralizar 🧠🔥"),
            ("💯 {valor} views!", "Pode colocar 'influencer' na bio 😏"),
            ("🔥 {valor} visualizações!", "O algoritmo tá comendo na sua mão 🍽️"),
            ("📣 {valor} views hoje, {nome}!", "Cem mil pessoas viram. Nem o vizinho que reclama do som 🔊"),
        ),
        500_000: _m(
            ("🤯 {valor} visualizações hoje!", "Meio milhão de olhos em você. Arruma o cabelo 💇"),
            ("🌪️ {valor} views!", "Isso não é post, é furacão 🌀"),
            ("🤯 {valor} visualizações!", "Já pode dar palestra sobre viralizar 🎤"),
            ("🛸 {valor} views hoje!", "Até os ETs estão assistindo 👽"),
        ),
        1_000_000: _m(
            ("🤑 {valor} visualizações em um dia?!", "Dubai te espera 🏝️✈️"),
            ("💎 {valor} views hoje!", "Pode ir escolhendo a cor da Lamborghini 🏎️"),
            ("🤑 {valor} visualizações!", "O Instagram tá te devendo um troféu 🏆"),
            ("👑 1 MILHÃO hoje, {nome}!", "{valor} views. Avisa quando for abrir o fã-clube 📸"),
        ),
    },
    "posts": {
        1_000: _m(
            ("⚡ {valor} posts hoje!", "A máquina de postar foi ligada 🤖"),
            ("⚡ {valor} posts publicados!", "Tá aquecendo os motores 🔥"),
            ("🏭 {valor} posts hoje!", "Fábrica de conteúdo a todo vapor 💨"),
        ),
        5_000: _m(
            ("🔥 {valor} posts hoje!", "Desse jeito o Instagram vai cair 💥📉"),
            ("🔥 {valor} posts!", "Os servidores da Meta tão suando 🥵"),
            ("📦 {valor} posts hoje!", "Nem os Correios entregam tanto assim 🚚"),
        ),
        10_000: _m(
            ("🧠 {valor} posts hoje!", "Haja memória 💾😵"),
            ("🧠 {valor} posts!", "Alguém chama o TI da Meta 🧑‍💻🚨"),
            ("🐙 {valor} posts hoje!", "Você tem quantos braços? 🤔"),
        ),
        15_000: _m(
            ("😱 {valor} posts hoje!", "O Zuckerberg tem medo de você 🫣"),
            ("😱 {valor} posts!", "O Zuck já tá ligando pra marcar reunião 📞"),
            ("🦖 {valor} posts hoje!", "Isso não é perfil, é dinossauro do conteúdo 🦕"),
        ),
    },
    "sales": {
        10: _m(
            ("💸 {valor} vendas hoje!", "O caixa começou a cantar 🎶💰"),
            ("💸 {valor} vendas!", "Pix caindo igual chuva 🌧️💵"),
            ("🛒 {valor} vendas hoje!", "Já paga o café da semana ☕"),
        ),
        50: _m(
            ("🤑 {valor} vendas hoje!", "O banco vai te ligar perguntando o que tá acontecendo 📞😅"),
            ("🤑 {valor} vendas!", "Já pode chamar o contador 🧾"),
            ("💰 {valor} vendas hoje!", "A maquininha pediu férias 🏖️"),
        ),
        100: _m(
            ("🚨 {valor} vendas em um dia!", "Vai com calma, quer ficar rico? 😂💰"),
            ("🚨 {valor} vendas hoje!", "Calma, deixa um pouco pros outros 🤭"),
            ("🔥 {valor} vendas hoje!", "O Pix tá até esquentando 🌡️"),
        ),
        500: _m(
            ("👑 {valor} vendas hoje!", "Isso não é venda, é império 🏰💎"),
            ("👑 {valor} vendas!", "Forbes já tá com sua foto na pauta 📸"),
            ("🚀 {valor} vendas hoje!", "Elon Musk quer saber seu segredo 🛰️"),
        ),
    },
    "followers": {
        1_000: _m(
            ("🎉 {conta} bateu {valor} seguidores!", "Mil pessoas acompanhando. Já é uma festa 🥳"),
            ("🎉 {conta} chegou a {valor} seguidores!", "Primeiro milhar a gente nunca esquece 💙"),
        ),
        5_000: _m(
            ("🌟 {conta} bateu {valor} seguidores!", "Já lota um show pequeno 🎤"),
            ("🌟 {conta}: {valor} seguidores!", "A conta tá crescendo bonita 🌱"),
        ),
        10_000: _m(
            ("🔟 {conta} bateu {valor} seguidores!", "10 mil! Agora é perfil de respeito 😎"),
            ("🔥 {conta}: {valor} seguidores!", "Dá pra encher um ginásio 🏟️"),
        ),
        50_000: _m(
            ("🚀 {conta} bateu {valor} seguidores!", "Meio caminho dos 100 mil 🧭"),
            ("🚀 {conta}: {valor} seguidores!", "Isso já é uma cidade inteira te seguindo 🏙️"),
        ),
        100_000: _m(
            ("🏆 {conta} bateu {valor} seguidores!", "Cem mil! Pode pedir o selo de prata ao YouTube 😂"),
            ("🏆 {conta}: {valor} seguidores!", "Celebridade confirmada ⭐"),
        ),
    },
}


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render(template: dict[str, str], value: int, account: str | None, name: str | None) -> tuple[str, str]:
    values = _SafeDict(valor=format_views(value), conta=f"@{account}" if account else "sua conta", nome=name or "")
    title = template["title"].format_map(values).replace(", !", "!").strip()
    body = template["body"].format_map(values).strip()
    return title[:120], body[:240]


def merge_messages(overrides: Any) -> dict[str, dict[int, list[dict[str, str]]]]:
    """Defaults with admin overrides applied (only valid kinds/thresholds/templates)."""
    merged = {kind: {t: list(v) for t, v in table.items()} for kind, table in DEFAULT_MESSAGES.items()}
    if not isinstance(overrides, dict):
        return merged
    for kind, table in overrides.items():
        if kind not in merged or not isinstance(table, dict):
            continue
        for raw_threshold, variants in table.items():
            try:
                threshold = int(raw_threshold)
            except (TypeError, ValueError):
                continue
            if threshold not in merged[kind] or not isinstance(variants, list):
                continue
            clean = [
                {"title": str(v["title"])[:120], "body": str(v["body"])[:240]}
                for v in variants
                if isinstance(v, dict) and str(v.get("title", "")).strip() and str(v.get("body", "")).strip()
            ]
            if clean:
                merged[kind][threshold] = clean
    return merged


async def load_messages(db: AsyncSession) -> dict[str, dict[int, list[dict[str, str]]]]:
    stored = await db.get(SystemSetting, MESSAGES_SETTING_KEY)
    return merge_messages(stored.value if stored else None)


def pick(messages, kind: str, threshold: int, rng: random.Random | None = None) -> dict[str, str]:
    return (rng or random).choice(messages[kind][threshold])


def new_thresholds(kind: str, value: int, already: set[int]) -> list[int]:
    return [t for t in THRESHOLDS[kind] if value >= t and t not in already]


@dataclass(frozen=True)
class _Scope:
    workspace_id: uuid.UUID
    user_id: uuid.UUID


async def views_today(db, scope, now, start, cache) -> int | None:
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


async def posts_today(db, scope, role, start, end) -> int:
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


async def sales_today(db, scope, start, end) -> int:
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


async def push_to(db, subscriptions, payload, keys, client, topic) -> tuple[int, int]:
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


async def _subscriptions(db, workspace_id, user_ids) -> list[PushSubscription]:
    return list(
        (
            await db.scalars(
                select(PushSubscription).where(
                    PushSubscription.workspace_id == workspace_id,
                    PushSubscription.user_id.in_(list(user_ids)),
                )
            )
        ).all()
    )


async def _nickname(db, user_id) -> str | None:
    row = (await db.execute(select(User.nickname, User.full_name).where(User.id == user_id))).first()
    return (row[0] or row[1]) if row else None


async def _notify_daily(db, scope, day: date, kind: str, value: int, client, keys, messages) -> int:
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
    top = max(pending)
    title, body = render(pick(messages, kind, top), value, None, await _nickname(db, scope.user_id))
    payload = {"title": title, "body": body, "url": "/dashboard", "tag": f"ms-{kind}-{top}-{day.isoformat()}"}
    subscriptions = await _subscriptions(db, scope.workspace_id, [scope.user_id])
    delivered, transient = await push_to(db, subscriptions, payload, keys, client, f"ms{kind[:1]}{top}")
    if delivered == 0 and transient:
        await db.execute(
            delete(MilestoneNotification).where(MilestoneNotification.id.in_([m.id for m in markers]))
        )
    else:
        for marker in markers:
            marker.delivered = delivered
    await db.commit()
    return delivered


async def _refresh_followers(db: AsyncSession, now: datetime) -> None:
    """Background read of followers_count for every connected account (hourly)."""
    accounts = (
        await db.scalars(
            select(InstagramAccount).where(
                InstagramAccount.status == "connected",
                InstagramAccount.token_expires_at > now,
                InstagramAccount.encrypted_access_token.is_not(None),
            )
        )
    ).all()
    for account in accounts:
        try:
            token = decrypt_value(account.encrypted_access_token or "")
            followers, _follows, media = await fetch_instagram_profile_metrics(token)
        except Exception:  # noqa: BLE001 - one account failing must not stop the rest
            continue
        if followers is not None:
            account.follower_count = followers
        if media is not None:
            account.media_count = media
    await db.commit()


async def _notify_followers(db: AsyncSession, client, keys_getter, messages) -> int:
    accounts = (
        await db.scalars(
            select(InstagramAccount).where(
                InstagramAccount.status == "connected", InstagramAccount.follower_count.is_not(None)
            )
        )
    ).all()
    total = 0
    for account in accounts:
        followers = int(account.follower_count or 0)
        seen = set(
            (
                await db.scalars(
                    select(AccountFollowerMilestone.threshold).where(
                        AccountFollowerMilestone.account_id == account.id
                    )
                )
            ).all()
        )
        if 0 not in seen:
            # First time we see this account: record what it already has, silently.
            db.add(AccountFollowerMilestone(account_id=account.id, threshold=0, followers=followers, delivered=-1))
            for threshold in new_thresholds("followers", followers, seen):
                db.add(
                    AccountFollowerMilestone(
                        account_id=account.id, threshold=threshold, followers=followers, delivered=-1
                    )
                )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
            continue
        pending = new_thresholds("followers", followers, seen)
        if not pending:
            continue
        markers = [
            AccountFollowerMilestone(account_id=account.id, threshold=t, followers=followers) for t in pending
        ]
        try:
            async with db.begin_nested():
                db.add_all(markers)
                await db.flush()
        except IntegrityError:
            continue
        await db.commit()
        owners = (
            await db.scalars(
                select(WorkspaceMember.user_id).where(
                    WorkspaceMember.workspace_id == account.workspace_id,
                    WorkspaceMember.role == WorkspaceRole.OWNER.value,
                    WorkspaceMember.status == "ACTIVE",
                )
            )
        ).all()
        recipients = set(owners)
        if account.connected_by_user_id:
            recipients.add(account.connected_by_user_id)
        subscriptions = await _subscriptions(db, account.workspace_id, recipients)
        if not subscriptions:
            continue
        keys = await keys_getter()
        if keys is None:
            return total
        top = max(pending)
        title, body = render(pick(messages, "followers", top), followers, account.username, None)
        payload = {"title": title, "body": body, "url": "/feature/accounts", "tag": f"ms-fol-{account.id}-{top}"}
        delivered, transient = await push_to(db, subscriptions, payload, keys, client, f"msf{top}")
        if delivered == 0 and transient:
            await db.execute(
                delete(AccountFollowerMilestone).where(
                    AccountFollowerMilestone.id.in_([m.id for m in markers])
                )
            )
        else:
            for marker in markers:
                marker.delivered = delivered
        await db.commit()
        total += delivered
    return total


async def run_milestones_tick(
    db: AsyncSession,
    now: datetime | None = None,
    views_cache: dict | None = None,
    refresh_followers: bool | None = None,
) -> int:
    """Check daily milestones for users with push and follower milestones per account."""
    global _last_followers_refresh
    now = now or datetime.now(timezone.utc)
    cache = views_cache if views_cache is not None else {}
    messages = await load_messages(db)
    keys_box: dict[str, VapidKeys | None] = {}

    async def keys_getter() -> VapidKeys | None:
        if "k" not in keys_box:
            try:
                keys_box["k"] = await get_vapid_keys(db)
            except (WebPushError, RuntimeError, ValueError) as exc:
                logger.error("Web Push keys unavailable (%s).", type(exc).__name__)
                keys_box["k"] = None
        return keys_box["k"]

    total = 0
    if refresh_followers is None:
        refresh_followers = monotonic_time.monotonic() - _last_followers_refresh >= FOLLOWERS_REFRESH_SECONDS
    if refresh_followers:
        _last_followers_refresh = monotonic_time.monotonic()
        try:
            await _refresh_followers(db, now)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.warning("Followers refresh failed (%s).", type(exc).__name__)

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
                    "views": await views_today(db, scope, now, start, cache),
                    "posts": await posts_today(db, scope, role, start, end),
                    "sales": (
                        await sales_today(db, scope, start, end)
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
                keys = await keys_getter()
                if keys is None:
                    return total
                total += await _notify_daily(db, scope, day, kind, value, client, keys, messages)
        try:
            from app.notifications.engagement import run_engagement_tick

            total += await run_engagement_tick(
                db,
                now,
                client=client,
                keys_getter=keys_getter,
                push_to=push_to,
                views_today=lambda d, scope, n, start: views_today(d, scope, n, start, cache),
            )
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.warning("Engagement pushes failed (%s).", type(exc).__name__)
        try:
            total += await _notify_followers(db, client, keys_getter, messages)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.warning("Follower milestones failed (%s).", type(exc).__name__)
    return total
