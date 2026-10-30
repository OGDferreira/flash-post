import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, Numeric, String, func, text
from sqlalchemy.orm import Mapped, deferred, mapped_column
from sqlalchemy.types import Uuid

from app.models import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("home_panel IS NULL OR home_panel IN ('flashpost', 'flashbot')", name="ck_users_home_panel"),
        CheckConstraint(
            "platform_role IN ('USER', 'SUPER_ADMIN')",
            name="ck_users_platform_role",
        ),
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
        Index(
            "uq_users_username_lower",
            func.lower(text("username")),
            unique=True,
            postgresql_where=text("username IS NOT NULL"),
            sqlite_where=text("username IS NOT NULL"),
        ),
        Index("uq_users_nickname_normalized", "nickname_normalized", unique=True),
        Index(
            "uq_users_invite_code",
            "invite_code",
            unique=True,
            postgresql_where=text("invite_code IS NOT NULL"),
            sqlite_where=text("invite_code IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    username: Mapped[str | None] = mapped_column(String(80))
    nickname: Mapped[str] = mapped_column(String(40), nullable=False)
    nickname_normalized: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(2048))
    # Code a chief shares so new users become affiliates (created lazily).
    invite_code: Mapped[str | None] = mapped_column(String(16))
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Fallback avatar stored in the database when object storage is not configured.
    avatar_data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary))
    avatar_content_type: Mapped[str | None] = mapped_column(String(40))
    platform_role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="USER", server_default="USER"
    )
    # Flash fee per sale for this user's operations; NULL = the platform default
    transaction_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # Set by the Super Admin: this user can't withdraw (the Super Admin still can, for them).
    withdrawals_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Only the Super Admin invites partners, unless they give this permission to a user.
    can_invite_partners: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # The Super Admin can take away the platform Instagram app from one user (they can no
    # longer connect accounts through it). Off by default: everyone can use it.
    platform_app_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Push notifications: what the user chose (changed only in Configurações) and whether the
    # "ativar notificações" prompt was already answered (it shows once).
    push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    push_prompt_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    home_panel: Mapped[str | None] = mapped_column(String(16))
    # iPhone widget (Scriptable): SHA-256 of a read-only token for today's Flash numbers
    widget_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    is_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
