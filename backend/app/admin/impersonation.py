"""Super Admin "Entrar": open a user's full account and come back to your own.

While inside, the session's user_id is the target's, so every endpoint behaves exactly as
for that user; impersonator_id remembers who to return to. Entries and exits are not recorded
(the platform owner's decision, 2026-10-23).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.auth.dependencies import DbSession, SuperAdminUser, require_csrf
from app.core.security import PlatformRole
from app.models import User, WorkspaceMember
from app.schemas.auth import MessageResponse

router = APIRouter(prefix="/api", tags=["platform administration"])

IMPERSONATOR_KEY = "impersonator_id"
_IMPERSONATOR_WORKSPACE_KEY = "impersonator_workspace_id"


def is_impersonating(request: Request) -> bool:
    """The Super Admin is inside someone's account: leave no trace the owner could notice
    (notices stay unread, the admin's device never subscribes to the owner's pushes)."""
    return isinstance(request.session.get(IMPERSONATOR_KEY), str)


@router.post(
    "/admin/users/{user_id}/impersonate",
    response_model=MessageResponse,
    dependencies=[Depends(require_csrf)],
)
async def impersonate_user(user_id: uuid.UUID, request: Request, admin: SuperAdminUser, db: DbSession) -> MessageResponse:
    if request.session.get(IMPERSONATOR_KEY):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Volte para a sua conta antes de entrar em outra.")
    target = await db.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    if target.id == admin.id or target.platform_role == PlatformRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível entrar na conta de um Super Admin.")
    if not target.is_active or not target.is_approved:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A conta está bloqueada ou aguardando aprovação.")
    membership = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == target.id, WorkspaceMember.status == "ACTIVE")
        .order_by(WorkspaceMember.created_at, WorkspaceMember.workspace_id)
        .limit(1)
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A conta não tem um workspace ativo.")

    request.session[IMPERSONATOR_KEY] = str(admin.id)
    workspace_id = request.session.get("workspace_id")
    if isinstance(workspace_id, str):
        request.session[_IMPERSONATOR_WORKSPACE_KEY] = workspace_id
    request.session["user_id"] = str(target.id)
    request.session["workspace_id"] = str(membership.workspace_id)
    return MessageResponse(message=f"Você entrou na conta de {target.full_name}.")


@router.post("/auth/impersonation/stop", response_model=MessageResponse, dependencies=[Depends(require_csrf)])
async def stop_impersonation(request: Request, db: DbSession) -> MessageResponse:
    """Back to the Super Admin's own account; works even if the target account broke meanwhile."""
    impersonator_id = request.session.get(IMPERSONATOR_KEY)
    if not isinstance(impersonator_id, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Você não está na conta de outro usuário.")
    try:
        admin = await db.scalar(select(User).where(User.id == uuid.UUID(impersonator_id)))
    except ValueError:
        admin = None
    if admin is None or not admin.is_active or admin.platform_role != PlatformRole.SUPER_ADMIN.value:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    workspace_id = request.session.pop(_IMPERSONATOR_WORKSPACE_KEY, None)
    request.session.pop(IMPERSONATOR_KEY, None)
    request.session["user_id"] = str(admin.id)
    if isinstance(workspace_id, str):
        request.session["workspace_id"] = workspace_id
    else:
        request.session.pop("workspace_id", None)
    return MessageResponse(message="Você voltou para a sua conta.")
