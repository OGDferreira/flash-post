"""Partner (sócio) rules shared by loops, funnels, payments and panels.

* A partner is an affiliate (``Affiliation``) of exactly one chief.
* The commission that money splits use is the one the partner *accepted*;
  a new proposal only applies after a new acceptance (future sales only).
* Templates are copied into the partner's own workspace: the copy has its own
  media files, accounts, queue and metrics, and never touches the original.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Affiliation,
    AppNotification,
    InstagramLoop,
    InstagramLoopMedia,
    InstagramMedia,
    PushSubscription,
    TgFlow,
    TgMedia,
    User,
    Workspace,
    WorkspaceMember,
)

logger = logging.getLogger(__name__)

SHOP_PREFIX = "fp-"
CENT = Decimal("0.01")
MAX_COMMISSION = Decimal("99.00")  # SmokePay rejects split percentages summing to 100


def shop_ref(workspace_id: uuid.UUID) -> str:
    """SmokePay subaccount reference of a workspace (created on first charge)."""
    return f"{SHOP_PREFIX}{workspace_id.hex}"


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


async def owner_workspace(db: AsyncSession, user_id: uuid.UUID) -> Workspace | None:
    return await db.scalar(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.role == "OWNER",
            WorkspaceMember.status == "ACTIVE",
            Workspace.owner_id == user_id,
        )
        .order_by(Workspace.created_at)
        .limit(1)
    )


async def partner_link(db: AsyncSession, user_id: uuid.UUID) -> Affiliation | None:
    return await db.scalar(
        select(Affiliation).where(Affiliation.affiliate_user_id == user_id, Affiliation.status == "ACTIVE")
    )


def accepted(link: Affiliation | None) -> bool:
    return link is not None and link.accepted_at is not None and link.accepted_percent is not None


def pending_acceptance(link: Affiliation) -> bool:
    return not accepted(link) or link.accepted_percent != link.participation_percent


async def is_chief(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return bool(
        await db.scalar(
            select(Affiliation.id).where(Affiliation.chief_user_id == user_id, Affiliation.status == "ACTIVE").limit(1)
        )
    )


async def role_of(db: AsyncSession, user: User) -> str:
    if user.platform_role == "SUPER_ADMIN":
        return "super_admin"
    if await partner_link(db, user.id):
        return "partner"
    if await is_chief(db, user.id):
        return "chief"
    return "independent"


# ------------------------------------------------------------------ payments


PLATFORM_FEE_KEY = "platform_fee"


@dataclass
class BillingRoute:
    """Where a PIX charge goes: ``shop_ref`` None = the platform's main account.

    ``origin`` is fixed on the order when the charge is created:
    * ``main`` — the platform owner's own sale (main wallet, no split);
    * ``shared_funnel`` — a partner selling with the chief's shared funnel:
      the accepted commission goes to the chief (SmokePay split);
    * ``own_funnel`` — a funnel of the seller's own: no chief commission; a
      partner pays only the platform fee set by the Super Admin.
    """

    shop_ref: str | None = None
    splits: list[dict] = field(default_factory=list)
    chief_user_id: uuid.UUID | None = None
    percent: Decimal | None = None
    origin: str = "main"
    fee_percent: Decimal | None = None
    fee_amount: Decimal | None = None
    allowed: bool = True

    def preview(self, net: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
        """(chief commission, partner net) from the net after the gateway fee."""
        if net is None or self.percent is None:
            return None, None
        commission = money(net * self.percent / Decimal(100))
        return commission, money(net - commission)

    def platform_fee(self, net: Decimal | None) -> Decimal | None:
        if self.fee_amount is not None:
            return self.fee_amount
        if self.fee_percent is not None and net is not None:
            return money(net * self.fee_percent / Decimal(100))
        return None


async def platform_fee_setting(db: AsyncSession) -> dict:
    from app.models import SystemSetting

    row = await db.get(SystemSetting, PLATFORM_FEE_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    kind = value.get("type") if value.get("type") in ("percent", "fixed") else "percent"
    try:
        amount = Decimal(str(value.get("value") or "0")).quantize(CENT)
    except Exception:
        amount = Decimal("0.00")
    return {"type": kind, "value": max(Decimal("0.00"), amount)}


async def shared_funnel_access(db: AsyncSession, flow: TgFlow, workspace_id: uuid.UUID) -> Affiliation | None:
    """The accepted partnership that lets ``workspace_id`` run this foreign funnel, or None."""
    if flow.workspace_id == workspace_id or not flow.shared:
        return None
    workspace = await db.get(Workspace, workspace_id)
    flow_workspace = await db.get(Workspace, flow.workspace_id)
    if workspace is None or flow_workspace is None:
        return None
    link = await partner_link(db, workspace.owner_id)
    if not accepted(link) or link.chief_user_id != flow_workspace.owner_id:
        return None
    return link


async def billing_route(db: AsyncSession, workspace_id: uuid.UUID, flow_id: uuid.UUID | None = None) -> BillingRoute:
    workspace = await db.get(Workspace, workspace_id)
    owner = await db.get(User, workspace.owner_id) if workspace else None
    flow = await db.get(TgFlow, flow_id) if flow_id else None
    foreign = flow is not None and flow.workspace_id != workspace_id
    if owner is None or owner.platform_role == "SUPER_ADMIN":
        return BillingRoute(allowed=not foreign)
    route = BillingRoute(shop_ref=shop_ref(workspace_id), origin="own_funnel")
    if foreign:
        link = await shared_funnel_access(db, flow, workspace_id)
        if link is None:
            route.allowed = False  # unshared, or partnership ended/not accepted
            return route
        route.origin = "shared_funnel"
        if not link.accepted_percent:
            return route
        chief = await db.get(User, link.chief_user_id)
        if chief is None:
            return route
        if chief.platform_role == "SUPER_ADMIN":
            rule: dict = {"parent": True}
        else:
            chief_workspace = await owner_workspace(db, chief.id)
            if chief_workspace is None:
                return route
            rule = {"shop_id": shop_ref(chief_workspace.id)}
        percent = min(link.accepted_percent, MAX_COMMISSION)
        rule["percent"] = float(percent)
        route.splits = [rule]
        route.chief_user_id = chief.id
        route.percent = percent
        return route
    # Own funnel: a partner pays only the platform fee (never the chief's commission).
    if await partner_link(db, owner.id):
        fee = await platform_fee_setting(db)
        if fee["value"] > 0:
            if fee["type"] == "fixed":
                route.fee_amount = fee["value"]
                route.splits = [{"parent": True, "amount": float(fee["value"])}]
            else:
                route.fee_percent = min(fee["value"], MAX_COMMISSION)
                route.splits = [{"parent": True, "percent": float(route.fee_percent)}]
    return route


# ------------------------------------------------------------------ notices


async def notify_user(
    db: AsyncSession, user_id: uuid.UUID, kind: str, title: str, body: str, url: str | None = None
) -> None:
    """In-app notice plus a best-effort web push. The caller commits."""
    db.add(AppNotification(user_id=user_id, kind=kind, title=title[:120], body=body[:500], url=url))
    try:
        from app.bots import http
        from app.notifications.milestones import push_to
        from app.notifications.webpush import get_vapid_keys

        subscriptions = list(await db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)))
        if subscriptions:
            keys = await get_vapid_keys(db)
            async with http.client(15.0) as session:
                await push_to(db, subscriptions, {"title": title, "body": body, "url": url or "/", "tag": kind}, keys, session, kind[:32])
    except Exception:
        logger.exception("Partner push notification failed")


# ------------------------------------------------------------------ templates


async def _copy_objects(pairs: list[tuple[str, str]]) -> None:
    if not pairs:
        return
    from app.instagram.storage import SupabaseStorage

    storage = SupabaseStorage.from_settings()
    gate = asyncio.Semaphore(5)

    async def one(src: str, dst: str) -> None:
        async with gate:
            await storage.copy(src, dst)

    await asyncio.gather(*(one(src, dst) for src, dst in pairs))


def _copied_path(workspace_id: uuid.UUID, media_id: uuid.UUID, source_path: str) -> str:
    return f"{workspace_id}/{media_id}/{source_path.rsplit('/', 1)[-1]}"


async def clone_loop(db: AsyncSession, source: InstagramLoop, workspace_id: uuid.UUID) -> InstagramLoop:
    """Copy a chief's loop into a partner workspace: same settings and media, zero accounts."""
    clone = InstagramLoop(
        workspace_id=workspace_id,
        name=source.name[:120],
        interval_min_minutes=source.interval_min_minutes,
        interval_max_minutes=source.interval_max_minutes,
        daily_limit_per_account=source.daily_limit_per_account,
        post_type=source.post_type,
        repeat_media=source.repeat_media,
        auto_folder_ids=[],
        status="paused",
        next_run_at=None,
        template_loop_id=source.id,
    )
    db.add(clone)
    await db.flush()
    medias = list(
        await db.scalars(
            select(InstagramMedia)
            .join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
            .where(InstagramLoopMedia.loop_id == source.id, InstagramMedia.workspace_id == source.workspace_id)
        )
    )
    pairs = []
    for media in medias:
        new_id = uuid.uuid4()
        path = _copied_path(workspace_id, new_id, media.storage_path)
        pairs.append((media.storage_path, path))
        db.add(
            InstagramMedia(
                id=new_id, workspace_id=workspace_id, storage_path=path, filename=media.filename,
                mime_type=media.mime_type, media_type=media.media_type, size_bytes=media.size_bytes,
                caption=media.caption, locked=media.locked or source.workspace_id != workspace_id,
            )
        )
        db.add(InstagramLoopMedia(loop_id=clone.id, media_id=new_id))
    await db.flush()
    await _copy_objects(pairs)
    return clone


def _remap(value, ids: dict[str, str]):
    if isinstance(value, dict):
        out = {k: _remap(v, ids) for k, v in value.items()}
        if out.get("type") == "group" and "group_chat_id" in out:
            out["group_chat_id"] = 0  # the partner picks their own group
        return out
    if isinstance(value, list):
        return [_remap(v, ids) for v in value]
    if isinstance(value, str) and value in ids:
        return ids[value]
    return value


def _uuid_strings(value, found: set[str]) -> set[str]:
    if isinstance(value, dict):
        for v in value.values():
            _uuid_strings(v, found)
    elif isinstance(value, list):
        for v in value:
            _uuid_strings(v, found)
    elif isinstance(value, str) and len(value) == 36:
        try:
            uuid.UUID(value)
            found.add(value)
        except ValueError:
            pass
    return found


async def clone_flow(db: AsyncSession, source: TgFlow, workspace_id: uuid.UUID) -> TgFlow:
    """Copy a shared funnel into a partner workspace with its own media copies.
    Group deliveries are reset: the partner's bot delivers to the partner's group."""
    candidates = [uuid.UUID(v) for v in _uuid_strings(source.definition, set())]
    medias = (
        list(
            await db.scalars(
                select(TgMedia).where(TgMedia.id.in_(candidates), TgMedia.workspace_id == source.workspace_id)
            )
        )
        if candidates
        else []
    )
    ids, pairs = {}, []
    for media in medias:
        new_id = uuid.uuid4()
        path = _copied_path(workspace_id, new_id, media.storage_path)
        ids[str(media.id)] = str(new_id)
        pairs.append((media.storage_path, path))
        db.add(
            TgMedia(
                id=new_id, workspace_id=workspace_id, kind=media.kind, file_name=media.file_name,
                content_type=media.content_type, size_bytes=media.size_bytes, storage_path=path, file_ids={},
                locked=media.locked,
            )
        )
    clone = TgFlow(
        workspace_id=workspace_id,
        name=source.name[:120],
        definition=_remap(source.definition, ids),
        template_flow_id=source.id,
    )
    db.add(clone)
    await db.flush()
    await _copy_objects(pairs)
    return clone


async def template_root(db: AsyncSession, flow: TgFlow) -> uuid.UUID:
    """The original funnel a chain of copies came from (for rankings)."""
    current, seen = flow, {flow.id}
    while current.template_flow_id and current.template_flow_id not in seen:
        parent = await db.get(TgFlow, current.template_flow_id)
        if parent is None:
            break
        seen.add(parent.id)
        current = parent
    return current.id
