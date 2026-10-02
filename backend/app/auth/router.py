from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.auth.dependencies import (
    AuthenticatedUser,
    DbSession,
    WorkspaceMemberAccess,
    csrf_token_for,
    require_csrf,
)
from app.core.config import get_settings
from app.core.rate_limit import LoginRateLimiter
from app.core.security import PlatformRole, verify_password
from app.models import User, Workspace, WorkspaceMember
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    ProfileUpdateRequest,
    UserResponse,
    WorkspaceResponse,
)

router = APIRouter(prefix="/api", tags=["authentication"])


def _user_role(user: User, membership: WorkspaceMember | None) -> str:
    if user.platform_role == PlatformRole.SUPER_ADMIN.value:
        return PlatformRole.SUPER_ADMIN.value
    return membership.role if membership is not None else "USER"


def _user_response(user: User, membership: WorkspaceMember | None) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        role=_user_role(user, membership),
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


async def _primary_membership(user: User, db):
    return await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id, WorkspaceMember.status == "ACTIVE")
        .order_by(WorkspaceMember.created_at, WorkspaceMember.workspace_id)
        .limit(1)
    )


@router.get("/auth/csrf")
async def get_csrf_token(request: Request) -> dict[str, str]:
    return {"csrf_token": csrf_token_for(request)}


@router.post("/auth/login", response_model=AuthResponse, dependencies=[Depends(require_csrf)])
async def login(payload: LoginRequest, request: Request, db: DbSession) -> AuthResponse:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    limiter: LoginRateLimiter = request.app.state.login_rate_limiter
    rate_key = limiter.key(client_host, str(payload.email))
    if await limiter.is_limited(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Please try again later.",
            headers={"Retry-After": str(settings.login_window_seconds)},
        )

    user = await db.scalar(select(User).where(User.email == str(payload.email)))
    is_valid = verify_password(payload.password, user.password_hash if user else None)
    if user is None or not user.is_active or not is_valid:
        await limiter.record_failure(rate_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect.")

    membership = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id, WorkspaceMember.status == "ACTIVE")
        .order_by(WorkspaceMember.created_at, WorkspaceMember.workspace_id)
        .limit(1)
    )
    request.session.clear()
    request.session["user_id"] = str(user.id)
    if membership is not None:
        request.session["workspace_id"] = str(membership.workspace_id)
    csrf_token = csrf_token_for(request)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    await limiter.clear(rate_key)
    return AuthResponse(user=_user_response(user, membership), csrf_token=csrf_token)


@router.post("/auth/logout", response_model=MessageResponse, dependencies=[Depends(require_csrf)])
async def logout(request: Request) -> MessageResponse:
    request.session.clear()
    csrf_token = csrf_token_for(request)
    return MessageResponse(message="Signed out.", csrf_token=csrf_token)


@router.get("/auth/me", response_model=UserResponse)
async def auth_me(user: AuthenticatedUser, db: DbSession) -> UserResponse:
    membership = await _primary_membership(user, db)
    return _user_response(user, membership)


@router.get("/profile", response_model=UserResponse)
async def get_profile(user: AuthenticatedUser, db: DbSession) -> UserResponse:
    membership = await _primary_membership(user, db)
    return _user_response(user, membership)


@router.patch("/profile", response_model=UserResponse, dependencies=[Depends(require_csrf)])
async def update_profile(
    payload: ProfileUpdateRequest,
    user: AuthenticatedUser,
    db: DbSession,
) -> UserResponse:
    user.full_name = payload.full_name.strip()
    user.avatar_url = str(payload.avatar_url) if payload.avatar_url else None
    await db.commit()
    await db.refresh(user)
    membership = await _primary_membership(user, db)
    return _user_response(user, membership)


@router.get("/workspace", response_model=WorkspaceResponse)
async def current_workspace(
    access: WorkspaceMemberAccess,
) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=access.workspace.id,
        name=access.workspace.name,
        slug=access.workspace.slug,
        status=access.workspace.status,
        role=access.membership.role,
        created_at=access.workspace.created_at,
    )
