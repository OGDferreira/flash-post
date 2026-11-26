"""Bot partnerships: an owner shares a whole bot (and the funnel it runs) with an
independent user, who gets their own account, edits the bot and funnel, and takes a
share of each sale's net.

Unlike a *sócio* (``Affiliation``), the partner keeps their own workspace. The bot keeps
running in the owner's workspace and the money lands in the owner's gateway account; the
split here is a transparent ledger (``BotPartnerSale``) both sides read, and the owner
settles payouts off-platform, logging them as ``BotPartnerPayout`` so each side sees when
the other received or withdrew.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class BotPartner(Base):
    """One partnership: the owner's ``bot_id`` shared with ``partner_user_id``.

    ``partner_percent`` is the partner's cut of each sale's net (after the gateway fee and
    the bot fee), the owner keeps the rest, and the owner may change it at any time (it
    only affects future sales). ``bot_fee`` is the Flash fee deducted per sale before the
    split: it defaults to the owner's normal fee and only the Super Admin may zero it.
    """

    __tablename__ = "bot_partners"
    __table_args__ = (
        UniqueConstraint("bot_id", "partner_user_id", name="uq_bot_partners_bot_partner"),
        Index("ix_bot_partners_owner", "owner_user_id", "status"),
        Index("ix_bot_partners_partner", "partner_user_id", "status"),
        CheckConstraint("owner_user_id <> partner_user_id", name="ck_bot_partners_not_self"),
        CheckConstraint(
            "partner_percent >= 0 AND partner_percent <= 100", name="ck_bot_partners_percent_range"
        ),
        CheckConstraint("bot_fee >= 0", name="ck_bot_partners_bot_fee"),
        CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'PAUSED', 'DECLINED', 'REVOKED')",
            name="ck_bot_partners_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    partner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    partner_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    # Fixed Flash fee (BRL) deducted per sale before the split. Snapshot at share time so a
    # later platform-wide change does not silently move a partner's numbers.
    bot_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", server_default="PENDING"
    )
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BotPartnerSale(Base):
    """The split recorded for one paid order on a shared bot, written once when the order is
    paid. ``net`` is what is left after the gateway fee and the bot fee; it is divided into
    ``partner_amount`` and ``owner_amount`` by ``partner_percent`` at that moment."""

    __tablename__ = "bot_partner_sales"
    __table_args__ = (
        UniqueConstraint("order_id", "partnership_id", name="uq_bot_partner_sales_order_part"),
        Index("ix_bot_partner_sales_partnership_paid", "partnership_id", "paid_at"),
        Index("ix_bot_partner_sales_partner_paid", "partner_user_id", "paid_at"),
        Index("ix_bot_partner_sales_owner_paid", "owner_user_id", "paid_at"),
        Index("ix_bot_partner_sales_status", "partnership_id", "payout_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partnership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bot_partners.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_orders.id", ondelete="CASCADE"), nullable=False
    )
    bot_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    partner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gateway_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    bot_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    partner_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    partner_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    owner_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Commission settlement status the owner controls: 'pending' | 'paid' | 'denied'.
    payout_status: Mapped[str] = mapped_column(
        String(8), nullable=False, default="pending", server_default="pending"
    )
    status_note: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Audit reference to the user who last changed the status (no DB-level FK).
    status_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BotPartnerPayout(Base):
    """A withdrawal/payout logged against a partnership so both sides see when each party
    received or took money. ``party`` is who the money went to: 'partner' (the owner paid
    the partner their share) or 'owner' (the owner took their own share)."""

    __tablename__ = "bot_partner_payouts"
    __table_args__ = (
        Index("ix_bot_partner_payouts_partnership_at", "partnership_id", "paid_at"),
        CheckConstraint("party IN ('owner', 'partner')", name="ck_bot_partner_payouts_party"),
        CheckConstraint("amount > 0", name="ck_bot_partner_payouts_amount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partnership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bot_partners.id", ondelete="CASCADE"), nullable=False
    )
    party: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
