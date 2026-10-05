from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class AdminSummary(BaseModel):
    users_total: int
    workspaces_total: int
    owners: int
    collaborators: int
    active_users: int


class AdminUser(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    role: str
    status: str
    is_approved: bool
    workspace_name: str | None
    created_at: datetime
    last_login_at: datetime | None


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
