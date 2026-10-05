import hmac
import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import PlatformRole, WorkspaceRole
from app.models import User, Workspace, WorkspaceMember

DbSession = Annotated[AsyncSession, Depends(get_db)]


def csrf_token_for(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


async def require_csrf(
    request: Request,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    session_token = request.session.get("csrf_token")
    if (
        not isinstance(session_token, str)
        or not isinstance(csrf_header, str)
        or not hmac.compare_digest(session_token, csrf_header)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid.",
        )


async def require_authenticated_user(
    request: Request,
    db: DbSession,
) -> User:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    try:
        parsed_user_id = uuid.UUID(user_id)
    except ValueError:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    user = await db.scalar(select(User).where(User.id == parsed_user_id))
    if user is None or not user.is_active or not user.is_approved:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


AuthenticatedUser = Annotated[User, Depends(require_authenticated_user)]


async def require_super_admin(user: AuthenticatedUser) -> User:
    if user.platform_role != PlatformRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
    return user


SuperAdminUser = Annotated[User, Depends(require_super_admin)]


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace: Workspace
    membership: WorkspaceMember


async def require_workspace_member(
    request: Request,
    user: AuthenticatedUser,
    db: DbSession,
    workspace_id_header: Annotated[uuid.UUID | None, Header(alias="X-Workspace-ID")] = None,
) -> WorkspaceAccess:
    session_workspace_id = request.session.get("workspace_id")
    workspace_id: uuid.UUID | None = workspace_id_header
    if workspace_id is None and isinstance(session_workspace_id, str):
        try:
            workspace_id = uuid.UUID(session_workspace_id)
        except ValueError:
            request.session.pop("workspace_id", None)

    query = (
        select(Workspace, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.status == "ACTIVE",
            Workspace.status == "ACTIVE",
        )
        .order_by(WorkspaceMember.created_at, Workspace.id)
    )
    if workspace_id is not None:
        query = query.where(Workspace.id == workspace_id)

    result = (await db.execute(query)).first()
    if result is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active workspace membership required.")
    workspace, membership = result
    return WorkspaceAccess(workspace=workspace, membership=membership)


WorkspaceMemberAccess = Annotated[WorkspaceAccess, Depends(require_workspace_member)]


async def require_owner(access: WorkspaceMemberAccess) -> WorkspaceAccess:
    if access.membership.role != WorkspaceRole.OWNER.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner role required.")
    return access


OwnerAccess = Annotated[WorkspaceAccess, Depends(require_owner)]


async def require_loop_manager(access: WorkspaceMemberAccess) -> WorkspaceAccess:
    if access.membership.role not in {
        WorkspaceRole.OWNER.value,
        WorkspaceRole.COLLABORATOR.value,
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Loop access required.")
    return access


LoopManagerAccess = Annotated[WorkspaceAccess, Depends(require_loop_manager)]
