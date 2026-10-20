"""Partner (sócio) rules shared by loops, funnels, payments and panels.

* A partner is an affiliate (``Affiliation``) of exactly one chief.
* The commission that money splits use is the one the partner *accepted*;
  a new proposal only applies after a new acceptance (future sales only).
* Templates are copied into the partner's own workspace: the copy has its own
  media files, accounts, queue and metrics, and never touches the original.
* A loop or funnel is shared with every partner (``shared_with`` None) or only
  with the partners listed in ``shared_with``.
* A shared loop reaches the partner as a *linked* copy: it follows the chief's
  loop (same media and schedule) and starts with no accounts, so it only posts
  once the partner adds their own accounts to it.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models import (
    Affiliation,
    AppNotification,
    InstagramLoop,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
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


def shares_with(item: InstagramLoop | TgFlow, user_id: uuid.UUID) -> bool:
    """Whether a chief's loop or funnel is offered to this partner."""
    if not item.shared:
        return False
    return item.shared_with is None or str(user_id) in {str(target) for target in item.shared_with}


def merge_targets(current: list | None, extra: list | None) -> list | None:
    """Targets after adding ``extra`` (None means every partner and always wins)."""
    if current is None or extra is None:
        return None
    return sorted({str(target) for target in [*current, *extra]})


async def partner_ids(db: AsyncSession, chief_id: uuid.UUID) -> set[str]:
    return {
        str(value)
        for value in await db.scalars(
            select(Affiliation.affiliate_user_id).where(Affiliation.chief_user_id == chief_id, Affiliation.status == "ACTIVE")
        )
    }


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
    # fixed fee on every sale that is not the Super Admin's own (Settings.flashbot_transaction_fee)
    transaction_fee: Decimal = Decimal("0.00")
    allowed: bool = True

    def preview(self, net: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
        """(chief commission, partner net) from the net after the gateway fee."""
        if net is None or self.percent is None:
            return None, None
        commission = money(net * self.percent / Decimal(100))
        return commission, money(net - commission - self.transaction_fee)

    def drop_transaction_fee(self) -> None:
        """Take the transaction fee back out of the splits (when the gateway refuses them)."""
        fee, self.transaction_fee = self.transaction_fee, Decimal("0.00")
        for rule in list(self.splits):
            if rule.get("parent") and "amount" in rule:
                left = money(Decimal(str(rule["amount"])) - fee)
                if left > 0:
                    rule["amount"] = float(left)
                else:
                    self.splits.remove(rule)
                return

    def platform_fee(self, net: Decimal | None) -> Decimal | None:
        """Everything the platform keeps from this sale: its fee plus the transaction fee."""
        if self.fee_amount is not None:
            return self.fee_amount + self.transaction_fee
        if self.fee_percent is not None and net is not None:
            return money(net * self.fee_percent / Decimal(100)) + self.transaction_fee
        return self.transaction_fee or None


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
    if not shares_with(flow, workspace.owner_id):
        return None
    return link


async def _chief_copy_link(db: AsyncSession, flow: TgFlow, owner_id: uuid.UUID) -> Affiliation | None:
    """A partner's own copy of their chief's funnel (copies made before funnels were
    protected): its sales still pay the chief's commission, like the original."""
    if flow.template_flow_id is None:
        return None
    template = await db.get(TgFlow, flow.template_flow_id)
    link = await partner_link(db, owner_id)
    if template is None or not accepted(link):
        return None
    chief_workspace = await owner_workspace(db, link.chief_user_id)
    return link if chief_workspace is not None and template.workspace_id == chief_workspace.id else None


async def billing_route(db: AsyncSession, workspace_id: uuid.UUID, flow_id: uuid.UUID | None = None) -> BillingRoute:
    route = await _base_route(db, workspace_id, flow_id)
    if route.allowed and route.shop_ref is not None:  # every operation but the Super Admin's
        _add_transaction_fee(route)
    return route


def _add_transaction_fee(route: BillingRoute) -> None:
    """The fixed fee per sale goes to the platform's main account, on top of any commission or
    platform fee; it joins a fixed platform-fee rule when there is one."""
    from app.core.config import get_settings

    fee = money(get_settings().flashbot_transaction_fee)
    if fee <= 0:
        return
    route.transaction_fee = fee
    for rule in route.splits:
        if rule.get("parent") and "amount" in rule:
            rule["amount"] = float(money(Decimal(str(rule["amount"])) + fee))
            return
    route.splits.append({"parent": True, "amount": float(fee)})


async def _base_route(db: AsyncSession, workspace_id: uuid.UUID, flow_id: uuid.UUID | None) -> BillingRoute:
    workspace = await db.get(Workspace, workspace_id)
    owner = await db.get(User, workspace.owner_id) if workspace else None
    flow = await db.get(TgFlow, flow_id) if flow_id else None
    foreign = flow is not None and flow.workspace_id != workspace_id
    if owner is None or owner.platform_role == "SUPER_ADMIN":
        return BillingRoute(allowed=not foreign)
    route = BillingRoute(shop_ref=shop_ref(workspace_id), origin="own_funnel")
    link = None
    if foreign:
        link = await shared_funnel_access(db, flow, workspace_id)
        if link is None:
            route.allowed = False  # unshared, or partnership ended/not accepted
            return route
    elif flow is not None:
        link = await _chief_copy_link(db, flow, owner.id)
    if link is not None:
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


# Money notices: shown with the dark FlashBot logo on the phone.
SALE_KINDS = ("sale", "commission")


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
                await push_to(db, subscriptions, {"title": title, "body": body, "url": url or "/", "tag": kind, **({"brand": "flashbot-dark"} if kind in SALE_KINDS else {})}, keys, session, kind[:32])
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


async def _flush_media_then_links(db: AsyncSession, links: list[InstagramLoopMedia]) -> None:
    """Insert the copied media before the playlist rows that point at them: the models have
    no relationship, so one flush may insert the links first and break the foreign key."""
    await db.flush()
    db.add_all(links)
    await db.flush()


def _copied_path(workspace_id: uuid.UUID, media_id: uuid.UUID, source_path: str) -> str:
    return f"{workspace_id}/{media_id}/{source_path.rsplit('/', 1)[-1]}"


async def _copy_covers(
    db: AsyncSession,
    source_workspace_id: uuid.UUID,
    workspace_id: uuid.UUID,
    cover_ids: set[uuid.UUID],
    pairs: list[tuple[str, str]],
) -> dict[uuid.UUID, uuid.UUID]:
    """Reels covers of the chief's loop in the partner's workspace: source cover id -> copy id.
    Covers already copied are reused; new ones are copied (locked) and their objects queued in ``pairs``."""
    cover_ids.discard(None)
    if not cover_ids:
        return {}
    if source_workspace_id == workspace_id:
        return {cover: cover for cover in cover_ids}
    mapping = {
        media.template_media_id: media.id
        for media in await db.scalars(
            select(InstagramMedia).where(
                InstagramMedia.workspace_id == workspace_id,
                InstagramMedia.is_cover.is_(True),
                InstagramMedia.template_media_id.in_(cover_ids),
            )
        )
    }
    for cover in await db.scalars(
        select(InstagramMedia).where(
            InstagramMedia.workspace_id == source_workspace_id,
            InstagramMedia.id.in_(cover_ids - set(mapping)),
        )
    ):
        new_id = uuid.uuid4()
        path = _copied_path(workspace_id, new_id, cover.storage_path)
        pairs.append((cover.storage_path, path))
        db.add(
            InstagramMedia(
                id=new_id, workspace_id=workspace_id, storage_path=path, filename=cover.filename,
                mime_type=cover.mime_type, media_type=cover.media_type, size_bytes=cover.size_bytes,
                is_cover=True, locked=True, template_media_id=cover.id,
            )
        )
        mapping[cover.id] = new_id
    return mapping


def _copy_post_settings(source: InstagramLoop, copy: InstagramLoop, covers: dict[uuid.UUID, uuid.UUID]) -> None:
    copy.caption_mode = source.caption_mode
    copy.caption = source.caption
    copy.cover_mode = source.cover_mode
    copy.cover_media_id = covers.get(source.cover_media_id) if source.cover_media_id else None


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
    pairs, links = [], []
    covers = await _copy_covers(
        db, source.workspace_id, workspace_id,
        {source.cover_media_id, *(media.cover_media_id for media in medias)}, pairs,
    )
    _copy_post_settings(source, clone, covers)
    for media in medias:
        new_id = uuid.uuid4()
        path = _copied_path(workspace_id, new_id, media.storage_path)
        pairs.append((media.storage_path, path))
        db.add(
            InstagramMedia(
                id=new_id, workspace_id=workspace_id, storage_path=path, filename=media.filename,
                mime_type=media.mime_type, media_type=media.media_type, size_bytes=media.size_bytes,
                caption=media.caption, locked=media.locked or source.workspace_id != workspace_id,
                cover_media_id=covers.get(media.cover_media_id) if media.cover_media_id else None,
            )
        )
        links.append(InstagramLoopMedia(loop_id=clone.id, media_id=new_id))
    await _flush_media_then_links(db, links)
    await _copy_objects(pairs)
    return clone


# ------------------------------------------------------------------ linked loops

_PENDING_JOBS = ("waiting_for_media", "queued")


async def _drop_pending_jobs(db: AsyncSession, loop_id: uuid.UUID, media_ids: list[uuid.UUID] | None = None) -> None:
    query = delete(InstagramPublicationJob).where(
        InstagramPublicationJob.loop_id == loop_id, InstagramPublicationJob.status.in_(_PENDING_JOBS)
    )
    if media_ids is not None:
        query = query.where(InstagramPublicationJob.media_id.in_(media_ids))
    await db.execute(query)


async def pause_linked_loop(db: AsyncSession, loop: InstagramLoop) -> None:
    """The chief stopped sharing (or the partnership ended): the copy stops posting."""
    if loop.status != "paused":
        loop.status = "paused"
        loop.next_run_at = None
        await _drop_pending_jobs(db, loop.id)


async def sync_linked_loop(db: AsyncSession, source: InstagramLoop, copy: InstagramLoop) -> None:
    """Make the partner's linked copy match the chief's loop: settings and media.
    New media are copied (locked) into the partner's workspace; removed ones leave the playlist."""
    copy.name = source.name[:120]
    interval_changed = (copy.interval_min_minutes, copy.interval_max_minutes) != (
        source.interval_min_minutes,
        source.interval_max_minutes,
    )
    copy.interval_min_minutes = source.interval_min_minutes
    copy.interval_max_minutes = source.interval_max_minutes
    copy.daily_limit_per_account = source.daily_limit_per_account
    copy.post_type = source.post_type
    copy.repeat_media = source.repeat_media
    if interval_changed:
        from app.loops.scheduler import reschedule_loop_accounts

        await reschedule_loop_accounts(db, copy, utc_now())
    wanted = {
        media.id: media
        for media in await db.scalars(
            select(InstagramMedia)
            .join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
            .where(InstagramLoopMedia.loop_id == source.id, InstagramMedia.workspace_id == source.workspace_id)
        )
    }
    have = list(
        await db.scalars(
            select(InstagramMedia)
            .join(InstagramLoopMedia, InstagramLoopMedia.media_id == InstagramMedia.id)
            .where(InstagramLoopMedia.loop_id == copy.id, InstagramMedia.workspace_id == copy.workspace_id)
        )
    )
    present = {media.template_media_id for media in have}
    gone = [media.id for media in have if media.template_media_id not in wanted]
    pairs, links = [], []
    covers = await _copy_covers(
        db, source.workspace_id, copy.workspace_id,
        {source.cover_media_id, *(media.cover_media_id for media in wanted.values())}, pairs,
    )
    _copy_post_settings(source, copy, covers)
    for media in have:  # captions and covers the chief edited later follow too
        source_media = wanted.get(media.template_media_id)
        if source_media is not None:
            if media.caption != source_media.caption:
                media.caption = source_media.caption
            cover = covers.get(source_media.cover_media_id) if source_media.cover_media_id else None
            if media.cover_media_id != cover:
                media.cover_media_id = cover
    if gone:
        await _drop_pending_jobs(db, copy.id, gone)
        await db.execute(
            delete(InstagramLoopMedia).where(InstagramLoopMedia.loop_id == copy.id, InstagramLoopMedia.media_id.in_(gone))
        )
    for media in wanted.values():
        if media.id in present:
            continue
        new_id = uuid.uuid4()
        path = _copied_path(copy.workspace_id, new_id, media.storage_path)
        pairs.append((media.storage_path, path))
        db.add(
            InstagramMedia(
                id=new_id, workspace_id=copy.workspace_id, storage_path=path, filename=media.filename,
                mime_type=media.mime_type, media_type=media.media_type, size_bytes=media.size_bytes,
                caption=media.caption, locked=True, template_media_id=media.id,
                cover_media_id=covers.get(media.cover_media_id) if media.cover_media_id else None,
                created_at=media.created_at,  # same playlist order as the chief's loop
            )
        )
        links.append(InstagramLoopMedia(loop_id=copy.id, media_id=new_id))
    await _flush_media_then_links(db, links)
    await _copy_objects(pairs)


async def ensure_linked_loop(db: AsyncSession, source: InstagramLoop, workspace_id: uuid.UUID) -> InstagramLoop:
    """The partner's linked copy of a shared loop, created on first need with zero accounts.
    It is active from the start: with no accounts it posts nothing until the partner adds one."""
    copy = await db.scalar(
        select(InstagramLoop).where(
            InstagramLoop.workspace_id == workspace_id,
            InstagramLoop.template_loop_id == source.id,
            InstagramLoop.linked.is_(True),
        )
    )
    if copy is None:
        copy = InstagramLoop(
            workspace_id=workspace_id, name=source.name[:120],
            interval_min_minutes=source.interval_min_minutes, interval_max_minutes=source.interval_max_minutes,
            daily_limit_per_account=source.daily_limit_per_account, post_type=source.post_type,
            repeat_media=source.repeat_media, auto_folder_ids=[], status="active", next_run_at=None,
            template_loop_id=source.id, linked=True,
        )
        db.add(copy)
        await db.flush()
    await sync_linked_loop(db, source, copy)
    return copy


async def sync_partner_loops(db: AsyncSession, link: Affiliation) -> list[InstagramLoop]:
    """Every loop the chief shares with this partner exists as a linked copy and is up to date;
    copies of loops no longer shared with them are paused. The caller commits."""
    partner_ws = await owner_workspace(db, link.affiliate_user_id)
    if partner_ws is None:
        return []
    chief_ws = await owner_workspace(db, link.chief_user_id) if accepted(link) else None
    sources = (
        [
            loop
            for loop in await db.scalars(
                select(InstagramLoop).where(InstagramLoop.workspace_id == chief_ws.id, InstagramLoop.shared.is_(True))
            )
            if shares_with(loop, link.affiliate_user_id)
        ]
        if chief_ws is not None
        else []
    )
    copies = [await ensure_linked_loop(db, source, partner_ws.id) for source in sources]
    kept = {copy.id for copy in copies}
    for orphan in await db.scalars(
        select(InstagramLoop).where(InstagramLoop.workspace_id == partner_ws.id, InstagramLoop.linked.is_(True))
    ):
        if orphan.id not in kept:
            await pause_linked_loop(db, orphan)
    return copies


async def linked_loop_available(db: AsyncSession, loop: InstagramLoop) -> bool:
    """A linked copy whose chief still shares the original with this partner."""
    if not loop.linked or loop.template_loop_id is None:
        return False
    source = await db.get(InstagramLoop, loop.template_loop_id)
    workspace = await db.get(Workspace, loop.workspace_id)
    if source is None or workspace is None:
        return False
    link = await partner_link(db, workspace.owner_id)
    chief_ws = await owner_workspace(db, link.chief_user_id) if accepted(link) else None
    return chief_ws is not None and source.workspace_id == chief_ws.id and shares_with(source, workspace.owner_id)


async def sync_all_shared_loops(db: AsyncSession) -> int:
    """Periodic job: provision and refresh every partner's linked loops; pause the ones that
    lost access (partnership ended). One partner failing never blocks the others."""
    synced = 0
    for link in list(await db.scalars(select(Affiliation).where(Affiliation.status == "ACTIVE"))):
        try:
            synced += len(await sync_partner_loops(db, link))
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Shared loop sync failed for a partner")
    for loop in list(await db.scalars(select(InstagramLoop).where(InstagramLoop.linked.is_(True), InstagramLoop.status == "active"))):
        if not await linked_loop_available(db, loop):
            await pause_linked_loop(db, loop)
    await db.commit()
    return synced


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
