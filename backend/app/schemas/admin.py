from datetime import datetime
from decimal import Decimal
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class AdminSummary(BaseModel):
    users_total: int
    workspaces_total: int
    owners: int
    collaborators: int
    active_users: int
    # Falcon Bot today (Brazil time): paid sales of every operation and the per-sale fee they paid
    flashbot_sales_today: int = 0
    flashbot_revenue_today: Decimal = Decimal("0.00")
    transaction_fees_today: Decimal = Decimal("0.00")
    transaction_fee_default: Decimal = Decimal("0.00")
    # Pix of the operations that pay the fee (not the Super Admin's own): generated / paid today
    fee_pix_generated_today: int = 0
    fee_pix_paid_today: int = 0


class AdminUser(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    role: str
    platform_role: str = "USER"
    status: str  # PENDING_APPROVAL | ACTIVE | BLOCKED
    is_approved: bool
    is_active: bool = True
    workspace_name: str | None
    created_at: datetime
    last_login_at: datetime | None
    hierarchy: str = "independent"  # chief | partner | independent
    transaction_fee: Decimal | None = None  # own Falcon Bot fee per sale; None = the default
    transaction_fee_effective: Decimal = Decimal("0.00")
    chief_name: str | None = None
    invited_by_name: str | None = None


class AdminUserAccessRequest(BaseModel):
    blocked: bool


class AdminUserRoleRequest(BaseModel):
    platform_role: Literal["USER", "SUPER_ADMIN"]


class AdminUsersPage(BaseModel):
    items: list[AdminUser]
    total: int
    page: int
    page_size: int


class AdminWorkspaceCollaborator(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr


class AdminWorkspace(BaseModel):
    id: UUID
    name: str
    slug: str
    owner_id: UUID | None = None
    owner_name: str
    owner_email: EmailStr
    status: str
    members_count: int
    connected_accounts: int
    errored_accounts: int
    active_posts: int
    collaborators: list[AdminWorkspaceCollaborator]
    created_at: datetime


class AdminWorkspacesPage(BaseModel):
    items: list[AdminWorkspace]
    total: int
    page: int
    page_size: int


class AdminTransactionFeeRequest(BaseModel):
    # None goes back to the platform default
    transaction_fee: Decimal | None = Field(default=None, ge=0, le=50, decimal_places=2)
