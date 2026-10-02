from typing import Annotated
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import DbSession, SuperAdminUser
from app.models import SystemSetting, User, Workspace, WorkspaceMember
from app.schemas.admin import (
    AdminSummary,
    AdminUser,
    AdminUsersPage,
    AdminWorkspace,
    AdminWorkspacesPage,
)

router = APIRouter(prefix="/api/admin", tags=["platform administration"])
_SENSITIVE_SETTING_KEY = re.compile(
    r"(secret|password|token|credential|private|service.?role|database.?url|encryption.?key)",
    re.IGNORECASE,
)


@router.get("/summary", response_model=AdminSummary)
async def summary(_admin: SuperAdminUser, db: DbSession) -> AdminSummary:
    users_total = await db.scalar(select(func.count()).select_from(User)) or 0
    workspaces_total = await db.scalar(select(func.count()).select_from(Workspace)) or 0
    owners = await db.scalar(
        select(func.count(func.distinct(WorkspaceMember.user_id))).where(
            WorkspaceMember.role == "OWNER",
            WorkspaceMember.status == "ACTIVE",
        )
    ) or 0
    collaborators = await db.scalar(
        select(func.count(func.distinct(WorkspaceMember.user_id))).where(
            WorkspaceMember.role == "COLLABORATOR",
            WorkspaceMember.status == "ACTIVE",
        )
    ) or 0
    active_users = await db.scalar(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    ) or 0
    return AdminSummary(
        users_total=users_total,
        workspaces_total=workspaces_total,
        owners=owners,
        collaborators=collaborators,
        active_users=active_users,
    )


@router.get("/users", response_model=AdminUsersPage)
async def list_users(
    _admin: SuperAdminUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUsersPage:
    membership_role = (
        select(WorkspaceMember.role)
        .where(
            WorkspaceMember.user_id == User.id,
            WorkspaceMember.status == "ACTIVE",
        )
        .order_by(WorkspaceMember.created_at, WorkspaceMember.workspace_id)
        .limit(1)
        .scalar_subquery()
    )
    workspace_name = (
        select(Workspace.name)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            WorkspaceMember.user_id == User.id,
            WorkspaceMember.status == "ACTIVE",
        )
        .order_by(WorkspaceMember.created_at, WorkspaceMember.workspace_id)
        .limit(1)
        .scalar_subquery()
    )
    role = case(
        (User.platform_role == "SUPER_ADMIN", "SUPER_ADMIN"),
        else_=func.coalesce(membership_role, "USER"),
    )

    count_query = select(func.count()).select_from(User)
    user_query = select(User, role.label("resolved_role"), workspace_name.label("workspace_name"))
    if q and q.strip():
        search = f"%{q.strip()}%"
        predicate = User.full_name.ilike(search) | User.email.ilike(search)
        count_query = count_query.where(predicate)
        user_query = user_query.where(predicate)

    total = await db.scalar(count_query) or 0
    rows = (
        await db.execute(
            user_query.order_by(User.created_at.desc(), User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        AdminUser(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=resolved_role,
            status="ACTIVE" if user.is_active else "INACTIVE",
            workspace_name=workspace,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )
        for user, resolved_role, workspace in rows
    ]
    return AdminUsersPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/workspaces", response_model=AdminWorkspacesPage)
async def list_workspaces(
    _admin: SuperAdminUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminWorkspacesPage:
    member_count = (
        select(func.count(WorkspaceMember.id))
        .where(
            WorkspaceMember.workspace_id == Workspace.id,
            WorkspaceMember.status == "ACTIVE",
        )
        .scalar_subquery()
    )
    count_query = select(func.count()).select_from(Workspace).join(User, User.id == Workspace.owner_id)
    workspace_query = (
        select(Workspace, User, member_count.label("members_count"))
        .join(User, User.id == Workspace.owner_id)
    )
    if q and q.strip():
        search = f"%{q.strip()}%"
        predicate = Workspace.name.ilike(search) | Workspace.slug.ilike(search) | User.email.ilike(search)
        count_query = count_query.where(predicate)
        workspace_query = workspace_query.where(predicate)

    total = await db.scalar(count_query) or 0
    rows = (
        await db.execute(
            workspace_query.order_by(Workspace.created_at.desc(), Workspace.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        AdminWorkspace(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            owner_name=owner.full_name,
            owner_email=owner.email,
            status=workspace.status,
            members_count=members_count,
            created_at=workspace.created_at,
        )
        for workspace, owner, members_count in rows
    ]
    return AdminWorkspacesPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/system/settings")
async def list_system_settings(_admin: SuperAdminUser, db: DbSession) -> list[dict]:
    rows = (await db.execute(select(SystemSetting).order_by(SystemSetting.key))).scalars().all()
    return [
        {
            "key": setting.key,
            "value": "[redacted]" if _SENSITIVE_SETTING_KEY.search(setting.key) else setting.value,
            "is_public": setting.is_public,
            "updated_at": setting.updated_at,
        }
        for setting in rows
    ]
