"""Which PIX gateway charges a sale, and how a SnakePay sale is divided.

SmokePay stays the default. SnakePay is used for an operation when:
* the Super Admin connected it (``SNAKEPAY_API_KEY`` + ``SNAKEPAY_WEBHOOK_SECRET``) and
  turned it on for users (system setting ``snakepay_enabled``);
* the operation chose it (``workspaces.payment_gateway``);
* everyone who must receive a share has a SnakePay recipient id.

Money: the charge is made with the platform owner's key, so the sale lands in the
platform's SnakePay account and SnakePay splits the net (after 3% + R$ 0,25) at once:
the seller's share to the seller's account, the accepted commission to the chief's
account. What is not split (platform fee, or a commission owed to the Super Admin)
stays in the platform account. Same rules as the SmokePay route (``billing_route``).
"""

import re
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import snakepay
from app.models import SystemSetting, User, Workspace
from app.partners.service import BillingRoute, owner_workspace

SNAKEPAY_ENABLED_KEY = "snakepay_enabled"
GATEWAYS = ("smokepay", "snakepay")
RECIPIENT_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
HUNDRED = Decimal("100")


def valid_recipient(value: str) -> bool:
    return bool(RECIPIENT_RE.match(value.strip()))


async def snakepay_enabled(db: AsyncSession) -> bool:
    row = await db.get(SystemSetting, SNAKEPAY_ENABLED_KEY)
    return bool(row and isinstance(row.value, dict) and row.value.get("enabled"))


async def snakepay_available(db: AsyncSession) -> bool:
    return snakepay.configured() and await snakepay_enabled(db)


@dataclass
class SnakePlan:
    """The split sent with a SnakePay charge and the expected shares."""

    split: list[dict] = field(default_factory=list)
    seller_recipient: str | None = None
    seller_percent: Decimal | None = None  # None: the seller is the platform (keeps everything)
    chief_recipient: str | None = None
    chief_percent: Decimal = Decimal("0")


async def snakepay_plan(db: AsyncSession, workspace: Workspace, route: BillingRoute, amount: Decimal) -> SnakePlan | None:
    """The SnakePay plan for this sale, or None to charge with SmokePay instead."""
    if workspace.payment_gateway != "snakepay" or not await snakepay_available(db):
        return None
    owner = await db.get(User, workspace.owner_id)
    if owner is None:
        return None
    if owner.platform_role == "SUPER_ADMIN":
        return SnakePlan()  # the platform's own sale: no split
    recipient = (workspace.snakepay_recipient_id or "").strip()
    if not valid_recipient(recipient):
        return None
    net = snakepay.expected_net(amount)
    if net <= 0:
        return None
    chief_percent = route.percent or Decimal("0")
    fee_percent = route.fee_percent or Decimal("0")
    if route.fee_amount:
        # A fixed platform fee becomes a percentage of this sale's net, rounded up so
        # the platform never gets less than the fee.
        fee_percent = (route.fee_amount * HUNDRED / net).quantize(Decimal("0.01"), ROUND_UP)
    seller_percent = HUNDRED - chief_percent - fee_percent
    if seller_percent <= 0:
        return None
    plan = SnakePlan(seller_recipient=recipient, seller_percent=seller_percent, chief_percent=chief_percent)
    plan.split.append({"recipient_id": recipient, "percentage": float(seller_percent)})
    if chief_percent > 0 and route.chief_user_id is not None:
        chief = await db.get(User, route.chief_user_id)
        if chief is None:
            return None
        if chief.platform_role != "SUPER_ADMIN":  # a Super Admin's commission stays in the platform account
            chief_workspace = await owner_workspace(db, chief.id)
            chief_recipient = (chief_workspace.snakepay_recipient_id or "").strip() if chief_workspace else ""
            if not valid_recipient(chief_recipient) or chief_recipient.lower() == recipient.lower():
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
    if plan.seller_percent is None:
        return  # platform sale: everything stays, nothing to record
    seller = amounts.get(plan.seller_recipient.lower()) if plan.seller_recipient else None
    if seller is None:
        seller = snakepay.share(net, plan.seller_percent)
    order.partner_net = seller
    if route.percent is not None:
        commission = amounts.get(plan.chief_recipient.lower()) if plan.chief_recipient else None
        order.split_amount = commission if commission is not None else snakepay.share(net, plan.chief_percent)
    elif route.fee_percent is not None or route.fee_amount is not None:
        order.platform_fee = (net - seller).quantize(Decimal("0.01"))


def snake_order_ref(order_id: uuid.UUID) -> str:
    from app.bots.engine import ORDER_PREFIX

    return f"{ORDER_PREFIX}{order_id}"
