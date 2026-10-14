"""Chief -> affiliate links with the chief's participation percentage."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class Affiliation(Base):
    """An affiliate belongs to at most one chief (``affiliate_user_id`` is unique)."""

    __tablename__ = "affiliations"
    __table_args__ = (
        CheckConstraint("chief_user_id <> affiliate_user_id", name="ck_affiliations_not_self"),
        CheckConstraint(
            "participation_percent >= 0 AND participation_percent <= 100",
            name="ck_affiliations_percent_range",
        ),
        CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_affiliations_status"),
        Index("uq_affiliations_affiliate", "affiliate_user_id", unique=True),
        Index("ix_affiliations_chief", "chief_user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chief_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    affiliate_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    participation_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
