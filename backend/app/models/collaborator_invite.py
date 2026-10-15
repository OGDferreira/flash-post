"""Owner-generated invite links that let a collaborator self-register."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class CollaboratorInvite(Base):
    """Only the SHA-256 of the token is stored; the link is shown once.

    The rate and goals are copied to the member when someone registers, so the
    owner only defines them here. The most recent invite doubles as the
    "last used settings" the owner sees as defaults for the next one.
    """

    __tablename__ = "collaborator_invites"
    __table_args__ = (
        Index("uq_collaborator_invites_token_hash", "token_hash", unique=True),
        Index("ix_collaborator_invites_workspace", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rate_per_connection: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    daily_connection_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    monthly_connection_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    monthly_bonus: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
