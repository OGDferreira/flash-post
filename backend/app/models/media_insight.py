import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class InstagramMediaInsight(Base):
    """Latest known lifetime metrics of one publication, synced from Meta.

    A metric is NULL when Meta did not return it (unsupported for the media
    type, missing permission or not yet available) — never stored as 0.
    """

    __tablename__ = "instagram_media_insights"
    __table_args__ = (
        UniqueConstraint("account_id", "ig_media_id", name="uq_instagram_media_insights_account_media"),
        Index("ix_instagram_media_insights_workspace_posted", "workspace_id", "posted_at"),
        Index("ix_instagram_media_insights_account_posted", "account_id", "posted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False
    )
    ig_media_id: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(32))
    media_product_type: Mapped[str | None] = mapped_column(String(32))
    permalink: Mapped[str | None] = mapped_column(String(500))
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048))
    caption: Mapped[str | None] = mapped_column(String(300))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    views: Mapped[int | None] = mapped_column(Integer)
    reach: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    metrics_error: Mapped[str | None] = mapped_column(String(300))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
