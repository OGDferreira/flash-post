"""Which PIX gateway charges a sale, and how gateway splits are applied.

SmokePay stays the default. SnakePay is used for an operation when:
* the Super Admin connected it (``SNAKEPAY_API_KEY`` + ``SNAKEPAY_WEBHOOK_SECRET``) and
  turned it on for users (system setting ``snakepay_enabled``);
* the operation chose it (``workspaces.payment_gateway``);
* everyone who must receive a share has a SnakePay recipient id.

With the platform key, SnakePay splits the net (after 3% + R$ 0,25) to the seller
and chief. When a seller configured their own credentials, their charge is created
in their account and only external shares are split out. Same billing rules apply.
Athenas Pay uses the platform key and each operation's own subaccount; it is also
the final automatic backup when the Super Admin releases it.
"""

import re
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import atenaspay, snakepay
from app.models import SystemSetting, TgFlow, TgFlowShare, TgGatewaySetting, User, Workspace
from app.partners.service import BillingRoute, active_share, owner_workspace, shared_source

SNAKEPAY_ENABLED_KEY = "snakepay_enabled"
ATENASPAY_ENABLED_KEY = "atenaspay_enabled"
GATEWAYS = ("smokepay", "snakepay", "atenaspay")
# The ShopID shown in SnakePay → Conta → Split ("snakepay_" + 32 hex); the docs' UUID form is accepted too.
RECIPIENT_RE = re.compile(
    r"^(snakepay_[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)
HUNDRED = Decimal("100")


def valid_recipient(value: str) -> bool:
    return bool(RECIPIENT_RE.match(value.strip()))


async def snakepay_enabled(db: AsyncSession) -> bool:
    row = await db.get(SystemSetting, SNAKEPAY_ENABLED_KEY)
    return bool(row and isinstance(row.value, dict) and row.value.get("enabled"))


async def snakepay_available(db: AsyncSession) -> bool:
    return snakepay.configured() and await snakepay_enabled(db)


async def atenaspay_enabled(db: AsyncSession) -> bool:
    row = await db.get(SystemSetting, ATENASPAY_ENABLED_KEY)
    return bool(row and isinstance(row.value, dict) and row.value.get("enabled"))


async def atenaspay_available(db: AsyncSession) -> bool:
    return atenaspay.configured() and await atenaspay_enabled(db)


@dataclass
class SnakePlan:
    """The split sent with a SnakePay charge and the expected shares."""

    split: list[dict] = field(default_factory=list)
    seller_recipient: str | None = None
    seller_percent: Decimal | None = None  # None: the seller is the platform (keeps everything)
    chief_recipient: str | None = None
    chief_percent: Decimal = Decimal("0")
    api_key: str | None = None
    webhook_secret: str | None = None


def same_recipient(a: str, b: str) -> bool:
    """``snakepay_<32 hex>`` and the dashed UUID are the same account."""
    def bare(value: str) -> str:
        value = value.strip().lower()
        return value.removeprefix("snakepay_").replace("-", "")

    return bool(a and b) and bare(a) == bare(b)


async def platform_recipients(db: AsyncSession) -> list[str]:
    """ShopIDs saved by Super Admin operations: the account that owns the API key. SnakePay
    refuses a split to the charging account itself, and its money already lands there."""
    rows = await db.scalars(
        select(Workspace.snakepay_recipient_id)
        .join(User, User.id == Workspace.owner_id)
        .where(User.platform_role == "SUPER_ADMIN", Workspace.snakepay_recipient_id.is_not(None))
    )
    return [row for row in rows if row]


def gateway_for(workspace: Workspace, flow: TgFlow | None) -> str:
    """The funnel's own choice, else the operation's default."""
    if flow is not None and flow.payment_gateway in GATEWAYS:
        return flow.payment_gateway
    return workspace.payment_gateway if workspace.payment_gateway in GATEWAYS else "smokepay"


async def gateway_choice(db: AsyncSession, workspace: Workspace, flow: TgFlow | None) -> str:
    """Who picks the gateway for this sale. A funnel shared by the chief (run directly, or a
    copy made from it) follows the gateway of the share's rules, else the chief's choice for
    that funnel, else the chief's default; the operation's own funnels follow the operation
    (its principal gateway for that funnel)."""
    source = await shared_source(db, flow, workspace.id)
    if source is None:
        return (await gateway_order(db, workspace, flow))[0]
    rule = await active_share(db, flow, workspace.id)
    if rule is not None:
        return rule.gateway
    owner = await db.get(Workspace, source.workspace_id)
    return gateway_for(owner, source) if owner is not None else gateway_for(workspace, None)


async def gateway_settings(db: AsyncSession, workspace_id) -> list[TgGatewaySetting]:
    return list(
        await db.scalars(
            select(TgGatewaySetting)
            .where(TgGatewaySetting.workspace_id == workspace_id)
            .order_by(TgGatewaySetting.priority, TgGatewaySetting.gateway)
        )
    )


def serves(setting: TgGatewaySetting, flow: TgFlow | None) -> bool:
    """Whether a gateway may charge this funnel (None = every funnel of the operation)."""
    if setting.flow_ids is None:
        return True
    return flow is not None and str(flow.id) in {str(value) for value in setting.flow_ids}


async def automatic_order(db: AsyncSession) -> list[str]:
    """Order of an operation that never arranged its gateways."""
    order = ["snakepay", "smokepay"] if await snakepay_available(db) else ["smokepay"]
    if await atenaspay_available(db):
        order.append("atenaspay")
    return order


async def gateway_order(db: AsyncSession, workspace: Workspace, flow: TgFlow | None) -> list[str]:
    """The gateways to try for one sale, in order: the principal first, then the backups.

    * A funnel shared by another operation follows that owner's rules, with SmokePay and
      Atenas Pay as safety nets when the selected gateway cannot pay every share.
    * The operation's own funnel: its own gateway choice comes first, then the operation's
      enabled gateways by priority, limited to the ones associated with this funnel.
    * Any operation can arrange its own gateways. One that never did uses the automatic order
      (Super Admin: its choice, with SmokePay and Atenas Pay as backups).
    """
    if await shared_source(db, flow, workspace.id) is not None:
        first = await gateway_choice(db, workspace, flow)
        backups = [name for name in ("smokepay", "atenaspay") if name != first]
        return [first, *backups]
    settings = await gateway_settings(db, workspace.id)
    owner = await db.get(User, workspace.owner_id)
    if not settings and owner is not None and owner.platform_role != "SUPER_ADMIN":
        # Until the operation orders its gateways, SnakePay is the principal when the platform has
        # it on, with SmokePay behind it (SnakePay that can't charge falls through).
        return await automatic_order(db)
    if not settings:
        first = gateway_for(workspace, flow)
        return [first, *[name for name in ("smokepay", "atenaspay") if name != first]]
    order = [row.gateway for row in settings if row.enabled and serves(row, flow)]
    enabled = {row.gateway for row in settings if row.enabled}
    if flow is not None and flow.payment_gateway in enabled:  # the funnel's own choice beats the global order
        if flow.payment_gateway in order:
            order.remove(flow.payment_gateway)
        order.insert(0, flow.payment_gateway)
    return order or ["smokepay"]


async def snakepay_plan(
    db: AsyncSession, workspace: Workspace, route: BillingRoute, amount: Decimal, flow: TgFlow | None = None,
    *, chosen: bool = False,
) -> SnakePlan | None:
    """The SnakePay plan for this sale, or None to charge with another gateway instead.
    ``chosen``: the gateway order already put SnakePay here (see ``gateway_order``)."""
    if not chosen and await gateway_choice(db, workspace, flow) != "snakepay":
        return None
    if not await snakepay_available(db):
        return None
    owner = await db.get(User, workspace.owner_id)
    if owner is None:
        return None
    if owner.platform_role == "SUPER_ADMIN":
        return SnakePlan()  # the platform's own sale: no split
    if route.owner_all:
        return await _owner_all_plan(db, route, amount)
    rule = await active_share(db, flow, workspace.id) if route.share_id else None
    own_account = bool(workspace.snakepay_api_key_encrypted and workspace.snakepay_webhook_secret_encrypted)
    owner_shop = ""
    if rule is not None:
        # A shared funnel with the owner's rules. When the seller saved their own SnakePay key,
        # the sale is charged in the seller's account and the owner's commission goes out by
        # split to the owner's ShopID. Without it, the platform key charges and splits the
        # seller's part to the ShopID saved on the share (the seller needs no credentials).
        if rule.gateway != "snakepay":
            return None
        if not own_account:
            return await _split_plan(db, route, amount, (rule.seller_shop_id or "").strip(), rule)
        owner_shop = (rule.owner_shop_id or "").strip()
    if own_account:
        from app.core.crypto import decrypt_value

        try:
            api_key = decrypt_value(workspace.snakepay_api_key_encrypted)
            webhook_secret = decrypt_value(workspace.snakepay_webhook_secret_encrypted)
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError("Saved SnakePay credentials could not be decrypted.") from exc
        net = snakepay.expected_net(amount)
        if net <= 0:
            return None
        chief_percent = route.percent or Decimal("0")
        fee_percent = route.fee_percent or Decimal("0")
        fixed = (route.fee_amount or Decimal("0")) + route.transaction_fee
        if fixed:
            fee_percent += (fixed * HUNDRED / net).quantize(Decimal("0.01"), ROUND_UP)

        platform = [value for value in await platform_recipients(db) if valid_recipient(value)]
        platform_accounts = {
            value.strip().lower().removeprefix("snakepay_").replace("-", "")
            for value in platform
        }
        platform_recipient = platform[0] if len(platform_accounts) == 1 else None
        split_percents: dict[str, Decimal] = {}
        chief_recipient = None
        if chief_percent > 0:
            chief = await db.get(User, route.chief_user_id) if route.chief_user_id else None
            if chief is None:
                return None
            if chief.platform_role == "SUPER_ADMIN":
                chief_recipient = platform_recipient
            else:
                chief_workspace = await owner_workspace(db, chief.id)
                chief_recipient = owner_shop or ((chief_workspace.snakepay_recipient_id or "").strip() if chief_workspace else None)
            if not chief_recipient or not valid_recipient(chief_recipient):
                return None
            split_percents[chief_recipient] = split_percents.get(chief_recipient, Decimal("0")) + chief_percent
        if fee_percent > 0:
            if not platform_recipient:
                return None
            split_percents[platform_recipient] = split_percents.get(platform_recipient, Decimal("0")) + fee_percent

        total_split = sum(split_percents.values(), Decimal("0"))
        seller_percent = HUNDRED - total_split
        if seller_percent <= 0 or total_split > HUNDRED:
            return None
        return SnakePlan(
            split=[{"recipient_id": recipient, "percentage": float(percent)} for recipient, percent in split_percents.items()],
            seller_percent=seller_percent,
            chief_recipient=chief_recipient,
            chief_percent=chief_percent,
            api_key=api_key,
            webhook_secret=webhook_secret,
        )

    return await _split_plan(db, route, amount, (workspace.snakepay_recipient_id or "").strip())


async def _owner_all_plan(db: AsyncSession, route: BillingRoute, amount: Decimal) -> SnakePlan | None:
    """The funnel's owner takes the whole sale: the Super Admin's goes to the platform account
    (no split); another owner's is charged with their own SnakePay key (only the Flash fee goes
    out by split) or, without one, with the platform key splitting the net to their ShopID."""
    chief = await db.get(User, route.chief_user_id) if route.chief_user_id else None
    if chief is None:
        return None
    if chief.platform_role == "SUPER_ADMIN":
        return SnakePlan()
    chief_workspace = await owner_workspace(db, chief.id)
    if chief_workspace is None:
        return None
    net = snakepay.expected_net(amount)
    if net <= 0:
        return None
    fee_percent = Decimal("0")
    if route.transaction_fee:
        fee_percent = (route.transaction_fee * HUNDRED / net).quantize(Decimal("0.01"), ROUND_UP)
    owner_percent = HUNDRED - fee_percent
    if owner_percent <= 0:
        return None
    platform = [value for value in await platform_recipients(db) if valid_recipient(value)]
    if chief_workspace.snakepay_api_key_encrypted and chief_workspace.snakepay_webhook_secret_encrypted:
        from app.core.crypto import decrypt_value

        try:
            api_key = decrypt_value(chief_workspace.snakepay_api_key_encrypted)
            webhook_secret = decrypt_value(chief_workspace.snakepay_webhook_secret_encrypted)
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError("Saved SnakePay credentials could not be decrypted.") from exc
        split = []
        if fee_percent > 0:
            accounts = {value.strip().lower().removeprefix("snakepay_").replace("-", "") for value in platform}
            if len(accounts) != 1:
                return None
            split = [{"recipient_id": platform[0], "percentage": float(fee_percent)}]
        return SnakePlan(split=split, chief_percent=owner_percent, api_key=api_key, webhook_secret=webhook_secret)
    rule = await db.get(TgFlowShare, route.share_id) if route.share_id else None
    recipient = ((rule.owner_shop_id if rule else None) or chief_workspace.snakepay_recipient_id or "").strip()
    if not valid_recipient(recipient) or any(same_recipient(recipient, own) for own in platform):
        return None
    return SnakePlan(
        split=[{"recipient_id": recipient, "percentage": float(owner_percent)}],
        chief_recipient=recipient, chief_percent=owner_percent,
    )


async def _split_plan(
    db: AsyncSession, route: BillingRoute, amount: Decimal, recipient: str, rule: TgFlowShare | None = None
) -> SnakePlan | None:
    """Platform key: the net is split to the seller's ShopID, the chief's commission to the
    chief's ShopID (the share's, when the owner set one) and the fees stay with the platform."""
    if not valid_recipient(recipient):
        return None
    platform = await platform_recipients(db)
    if any(same_recipient(recipient, own) for own in platform):
        return None  # a seller cannot use the platform's own ShopID: keep SmokePay
    net = snakepay.expected_net(amount)
    if net <= 0:
        return None
    chief_percent = route.percent or Decimal("0")
    fee_percent = route.fee_percent or Decimal("0")
    fixed = (route.fee_amount or Decimal("0")) + route.transaction_fee
    if fixed:
        # Fixed fees (platform fee, transaction fee) become a percentage of this sale's net,
        # rounded up so the platform never gets less than them.
        fee_percent += (fixed * HUNDRED / net).quantize(Decimal("0.01"), ROUND_UP)
    seller_percent = HUNDRED - chief_percent - fee_percent
    if seller_percent <= 0:
        return None
    plan = SnakePlan(seller_recipient=recipient, seller_percent=seller_percent, chief_percent=chief_percent)
    plan.split.append({"recipient_id": recipient, "percentage": float(seller_percent)})
    if chief_percent > 0 and route.chief_user_id is not None:
        chief = await db.get(User, route.chief_user_id)
        if chief is None:
            return None
        chief_workspace = None if chief.platform_role == "SUPER_ADMIN" else await owner_workspace(db, chief.id)
        chief_recipient = (chief_workspace.snakepay_recipient_id or "").strip() if chief_workspace else ""
        if rule is not None and chief_workspace is not None:
            chief_recipient = (rule.owner_shop_id or "").strip()
        if chief_workspace is not None and any(same_recipient(chief_recipient, own) for own in platform):
            chief_workspace = None  # the chief's ShopID is the platform account: the commission stays there
        if chief_workspace is not None:  # a Super Admin's commission stays in the platform account
            if not valid_recipient(chief_recipient) or same_recipient(chief_recipient, recipient):
                return None  # the chief could not receive the commission: keep SmokePay
            plan.chief_recipient = chief_recipient
            plan.split.append({"recipient_id": chief_recipient, "percentage": float(chief_percent)})
    return plan


def apply_snake_charge(order, route: BillingRoute, plan: SnakePlan, charge: snakepay.SnakeCharge) -> None:
    """Record gateway, fee and the shares of a SnakePay charge on the order."""
    net = charge.net_amount if charge.net_amount is not None else snakepay.expected_net(order.amount)
    order.gateway = "snakepay"
    order.gateway_transaction_id = charge.charge_id[:64]
    order.shop_ref = None  # SnakePay has no subaccounts
    order.net_amount = net
    order.gateway_fee = (order.amount - net).quantize(Decimal("0.01"))
    order.pix_copy_paste = charge.copy_paste
    amounts = {k.lower(): v for k, v in (charge.split_amounts or {}).items()}
    if route.owner_all:  # the whole sale is the funnel owner's; the seller gets nothing
        order.partner_net = Decimal("0.00")
        if plan.chief_recipient:  # platform key: the owner's share went out by split
            owner = amounts.get(plan.chief_recipient.lower())
            if owner is None:
                owner = snakepay.share(net, plan.chief_percent)
        else:  # charged in the owner's own account: only the splits (the Flash fee) went out
            out = Decimal("0.00")
            for rule in plan.split:
                part = amounts.get(rule["recipient_id"].lower())
                out += part if part is not None else snakepay.share(net, Decimal(str(rule["percentage"])))
            owner = net - out
        order.split_amount = owner
        order.platform_fee = (net - owner).quantize(Decimal("0.01")) or None
        return
    if plan.api_key is not None:
        split_total = Decimal("0.00")
        for rule in plan.split:
            recipient = rule["recipient_id"].lower()
            percentage = Decimal(str(rule["percentage"]))
            split_total += amounts.get(recipient, snakepay.share(net, percentage))
        seller = net - split_total
        order.partner_net = seller
        if route.percent is not None:
            commission = amounts.get(plan.chief_recipient.lower()) if plan.chief_recipient else None
            order.split_amount = commission if commission is not None else snakepay.share(net, plan.chief_percent)
        order.platform_fee = (net - seller - (order.split_amount or Decimal("0.00"))).quantize(Decimal("0.01"))
        return
    if plan.seller_percent is None:
        return  # platform sale: everything stays, nothing to record
    seller = amounts.get(plan.seller_recipient.lower()) if plan.seller_recipient else None
    if seller is None:
        seller = snakepay.share(net, plan.seller_percent)
    order.partner_net = seller
    if route.percent is not None:
        commission = amounts.get(plan.chief_recipient.lower()) if plan.chief_recipient else None
        order.split_amount = commission if commission is not None else snakepay.share(net, plan.chief_percent)
        if route.transaction_fee:  # what is left after the seller and the chief stays with the platform
            order.platform_fee = (net - seller - order.split_amount).quantize(Decimal("0.01"))
    elif route.fee_percent is not None or route.fee_amount is not None or route.transaction_fee:
        order.platform_fee = (net - seller).quantize(Decimal("0.01"))


def snake_order_ref(order_id: uuid.UUID) -> str:
    from app.bots.engine import ORDER_PREFIX

    return f"{ORDER_PREFIX}{order_id}"
