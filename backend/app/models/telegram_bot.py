"""Telegram sales bots run by FlashPost itself (the in-house SharkBot alternative).

A workspace connects bots (token from @BotFather) and builds flows in the panel.
Every piece of copy, media, price and delivery lives in ``TgFlow.definition``;
the engine only reads it. Leads, orders and subscriptions are per bot.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


def _workspace_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )


class TgFlow(Base):
    __tablename__ = "tg_flows"
    __table_args__ = (Index("ix_tg_flows_workspace", "workspace_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    template_flow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flows.id", ondelete="SET NULL")
    )
    customized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TgBot(Base):
    __tablename__ = "tg_bots"
    __table_args__ = (
        UniqueConstraint("tg_bot_id", name="uq_tg_bots_tg_bot_id"),
        Index("ix_tg_bots_workspace", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    flow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flows.id", ondelete="SET NULL")
    )
    tg_bot_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_token: Mapped[str] = mapped_column(String(4096), nullable=False)
    # Telegram echoes it in X-Telegram-Bot-Api-Secret-Token on every update.
    webhook_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="online", server_default="online"
    )
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TgGroup(Base):
    """A group/channel where a bot is a member; filled from my_chat_member updates."""

    __tablename__ = "tg_groups"
    __table_args__ = (
        UniqueConstraint("bot_id", "chat_id", name="uq_tg_groups_bot_chat"),
        Index("ix_tg_groups_workspace", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    bot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # True only while the bot is admin with permission to create invite links.
    can_invite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TgMedia(Base):
    """A file uploaded in the panel; ``file_ids`` caches Telegram's id per bot."""

    __tablename__ = "tg_media"
    __table_args__ = (Index("ix_tg_media_workspace", "workspace_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # photo|video|audio
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_ids: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TgLead(Base):
    __tablename__ = "tg_leads"
    __table_args__ = (
        UniqueConstraint("bot_id", "tg_user_id", name="uq_tg_leads_bot_user"),
        Index("ix_tg_leads_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    bot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False
    )
    flow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flows.id", ondelete="SET NULL")
    )
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))
    # Payload of /start (tracking code per Instagram account or campaign).
    source: Mapped[str | None] = mapped_column(String(64))
    age_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_bot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="new", server_default="new")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TgOrder(Base):
    __tablename__ = "tg_orders"
    __table_args__ = (
        Index("ix_tg_orders_workspace_created", "workspace_id", "created_at"),
        Index("ix_tg_orders_status_expires", "status", "expires_at"),
        Index("ix_tg_orders_split_chief", "split_chief_user_id", "paid_at"),
        UniqueConstraint("gateway", "gateway_transaction_id", name="uq_tg_orders_gateway_tx"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    bot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_leads.id", ondelete="CASCADE"), nullable=False
    )
    flow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flows.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="plan", server_default="plan")
    offer_id: Mapped[str] = mapped_column(String(64), nullable=False)  # plan id in the flow
    offer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Snapshot of the plan (price, duration, delivery) at purchase time.
    offer_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gateway: Mapped[str] = mapped_column(String(32), nullable=False, default="smokepay", server_default="smokepay")
    gateway_transaction_id: Mapped[str | None] = mapped_column(String(64))
    gateway_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Partner split, fixed when the PIX is created (server-side percentage).
    shop_ref: Mapped[str | None] = mapped_column(String(64))
    split_chief_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    split_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    split_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    partner_net: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pix_copy_paste: Mapped[str | None] = mapped_column(Text)
    # pending -> paid | expired | review (amount mismatch) | failed (gateway error)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    payer_name: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TgSubscription(Base):
    __tablename__ = "tg_subscriptions"
    __table_args__ = (
        Index("ix_tg_subscriptions_status_ends", "status", "ends_at"),
        Index("ix_tg_subscriptions_workspace", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    bot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_leads.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_orders.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # None = lifetime
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    invite_link: Mapped[str | None] = mapped_column(String(255))


class TgJob(Base):
    """A scheduled bot action (delayed message, expiry, removal). Idempotent by key."""

    __tablename__ = "tg_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tg_jobs_idempotency"),
        Index("ix_tg_jobs_due", "status", "run_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    bot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_leads.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TgUpdateSeen(Base):
    """Telegram may redeliver an update; each (bot, update_id) is processed once."""

    __tablename__ = "tg_updates_seen"
    __table_args__ = (UniqueConstraint("bot_id", "update_id", name="uq_tg_updates_seen"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_bots.id", ondelete="CASCADE"), nullable=False
    )
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
