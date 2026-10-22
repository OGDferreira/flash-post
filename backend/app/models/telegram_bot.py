"""Telegram sales bots run by Falcon Post itself (the in-house SharkBot alternative).

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
    CheckConstraint,
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
    # Who it is shared with: None = every partner, else a list of partner user ids.
    shared_with: Mapped[list | None] = mapped_column(JSON)
    template_flow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flows.id", ondelete="SET NULL")
    )
    customized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # PIX gateway for this funnel's sales; None follows the operation's default.
    payment_gateway: Mapped[str | None] = mapped_column(String(16))
    # Loop that goes out together with the shared funnel (optional).
    shared_loop_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_loops.id", ondelete="SET NULL")
    )
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
    # A folder of funnels instead of one funnel: each new lead gets one of them at random.
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flow_folders.id", ondelete="SET NULL")
    )
    tg_bot_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_token: Mapped[str] = mapped_column(String(4096), nullable=False)
    # Telegram echoes it in X-Telegram-Bot-Api-Secret-Token on every update.
    webhook_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    # Group/channel this bot delivers to when it runs a funnel shared by the chief
    # (the chief's own group would not accept invites from the partner's bot).
    delivery_group_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    # Channel/group where the bot is admin; files are uploaded there once and reused by file_id.
    cache_chat_id: Mapped[int | None] = mapped_column(BigInteger)
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
    # copied from a chief's shared funnel: delivered normally, never shown to the partner
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
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
    snakepay_api_key_encrypted: Mapped[str | None] = mapped_column(String(1024))
    snakepay_webhook_secret_encrypted: Mapped[str | None] = mapped_column(String(1024))
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
    # Fixed when the charge is created, never changed: shared_funnel | own_funnel | main
    origin: Mapped[str | None] = mapped_column(String(16))
    # The share rules (tg_flow_shares) the commission came from, for the audit of each sale.
    share_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    # Gateways tried before the one that charged (failover), e.g. ["snakepay"].
    gateway_attempts: Mapped[list | None] = mapped_column(JSON)
    platform_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    transaction_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # Falcon Bot fee charged on this sale
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


class TgCampaign(Base):
    """A remarketing broadcast of one funnel: sent to that funnel's leads through their own bots.

    ``definition`` (audience, message variants, offer) is validated by
    ``app.bots.campaigns.CampaignDefinition``. Sending walks the audience in lead id
    order; ``cursor_lead_id`` is the last lead handled so a restart never repeats one.
    """

    __tablename__ = "tg_campaigns"
    __table_args__ = (
        Index("ix_tg_campaigns_workspace_flow", "workspace_id", "flow_id"),
        Index("ix_tg_campaigns_status_scheduled", "status", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    flow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # draft -> scheduled -> sending -> finished | paused
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cursor_lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Leads of the audience that had already blocked the bot when the send started.
    already_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TgFlowShare(Base):
    """The rules of one funnel shared with one partner (the seller), set by the funnel's owner.

    Only the owner creates or changes them; the seller reads them. ``owner_percent`` is the
    owner's commission and ``seller_percent`` what the seller keeps, both over the sale's
    net after the gateway fee, summing to 100. The SnakePay ShopIDs are tied to this share
    only: the seller never needs credentials of their own to sell this funnel.
    """

    __tablename__ = "tg_flow_shares"
    __table_args__ = (
        UniqueConstraint("flow_id", "partner_user_id", name="uq_tg_flow_shares_flow_partner"),
        Index("ix_tg_flow_shares_owner", "owner_user_id", "status"),
        Index("ix_tg_flow_shares_partner", "partner_user_id", "status"),
        CheckConstraint("owner_percent >= 0 AND owner_percent < 100", name="ck_tg_flow_shares_owner_percent"),
        CheckConstraint("seller_percent > 0 AND seller_percent <= 100", name="ck_tg_flow_shares_seller_percent"),
        CheckConstraint("owner_percent + seller_percent = 100", name="ck_tg_flow_shares_total"),
        CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_tg_flow_shares_status"),
        CheckConstraint("gateway IN ('smokepay', 'snakepay')", name="ck_tg_flow_shares_gateway"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    partner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    gateway: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    seller_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    seller_shop_id: Mapped[str | None] = mapped_column(String(64))
    owner_shop_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TgGatewaySetting(Base):
    """One gateway of an operation: on/off, its place in the order (1 = principal, then the
    backups) and, optionally, the operation's own funnels it is limited to (None = all)."""

    __tablename__ = "tg_gateway_settings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "gateway", name="uq_tg_gateway_settings_workspace_gateway"),
        CheckConstraint("gateway IN ('smokepay', 'snakepay')", name="ck_tg_gateway_settings_gateway"),
        CheckConstraint("priority >= 1", name="ck_tg_gateway_settings_priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    gateway: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    flow_ids: Mapped[list | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AuditEvent(Base):
    """Who changed which financial rule and when. ``details`` never holds a secret: ShopIDs
    are masked and credentials are only recorded as "changed"."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_events_entity", "entity", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    entity: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TgFlowFolder(Base):
    """A folder of funnels to test against each other: a bot connected to it sends each new
    lead one of its funnels at random (the lead keeps that funnel)."""

    __tablename__ = "tg_flow_folders"
    __table_args__ = (Index("ix_tg_flow_folders_workspace", "workspace_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TgFlowFolderItem(Base):
    """A funnel in a folder: one of the operation's own, or one shared with it."""

    __tablename__ = "tg_flow_folder_items"
    __table_args__ = (UniqueConstraint("folder_id", "flow_id", name="uq_tg_flow_folder_items"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    folder_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flow_folders.id", ondelete="CASCADE"), nullable=False
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tg_flows.id", ondelete="CASCADE"), nullable=False
    )
