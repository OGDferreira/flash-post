from datetime import datetime, timezone
import logging
import re
import unicodedata
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.dependencies import (
    AuthenticatedUser,
    DbSession,
    WorkspaceMemberAccess,
    csrf_token_for,
    require_csrf,
)
from app.core.config import get_settings
from app.core.nickname import nickname_key, normalize_nickname
from app.core.rate_limit import LoginRateLimiter
from app.core.security import PlatformRole, WorkspaceRole, hash_password, verify_password
from app.instagram.storage import SupabaseStorage, SupabaseStorageError
from app.models import User, Workspace, WorkspaceMember
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    NicknameAvailabilityResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    UserResponse,
    WorkspaceResponse,
)

router = APIRouter(prefix="/api", tags=["authentication"])
logger = logging.getLogger(__name__)
MAX_PROFILE_AVATAR_BYTES = 5 * 1024 * 1024
PROFILE_AVATAR_TYPES = {
    "image/jpeg": (".jpg", lambda content: content.startswith(b"\xff\xd8\xff")),
    "image/png": (".png", lambda content: content.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": (
        ".webp",
        lambda content: len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP",
    ),
}
_AVATAR_STORAGE_PREFIX = "avatars/"


def _user_role(user: User, membership: WorkspaceMember | None) -> str:
    if user.platform_role == PlatformRole.SUPER_ADMIN.value:
        return PlatformRole.SUPER_ADMIN.value
    return membership.role if membership is not None else "USER"


def _user_response(user: User, membership: WorkspaceMember | None) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        nickname=user.nickname,
        full_name=user.full_name,
        avatar_url=(
            f"/api/profile/avatar?{urlencode({'v': int(user.updated_at.timestamp())})}"
            if user.avatar_url and user.avatar_url.startswith(_AVATAR_STORAGE_PREFIX)
            else user.avatar_url
        ),
        role=_user_role(user, membership),
        workspace_role=membership.role if membership is not None else None,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_approved=user.is_approved,
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


def _request_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _nickname_in_use(db, nickname: str, exclude_user_id: uuid.UUID | None = None) -> bool:
    query = select(User.id).where(User.nickname_normalized == nickname_key(nickname))
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    return await db.scalar(query) is not None


async def _workspace_slug(db, nickname: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", nickname).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")[:160].rstrip("-") or "workspace"
    candidate = base
    suffix = 2
    while await db.scalar(select(Workspace.id).where(func.lower(Workspace.slug) == candidate)):
        suffix_text = f"-{suffix}"
        candidate = f"{base[:180 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


@router.get("/auth/csrf")
async def get_csrf_token(request: Request) -> dict[str, str]:
    return {"csrf_token": csrf_token_for(request)}


@router.get("/auth/nickname-availability", response_model=NicknameAvailabilityResponse)
async def nickname_availability(
    request: Request,
    db: DbSession,
    nickname: str = Query(min_length=2, max_length=160),
) -> NicknameAvailabilityResponse:
    try:
        normalized = normalize_nickname(nickname)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    settings = get_settings()
    limiter: LoginRateLimiter = request.app.state.nickname_check_rate_limiter
    rate_key = limiter.key(_request_host(request), "nickname-availability")
    if await limiter.is_limited(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many nickname checks. Please try again later.",
            headers={"Retry-After": str(settings.nickname_check_window_seconds)},
        )
    await limiter.record_failure(rate_key)
    return NicknameAvailabilityResponse(
        available=not await _nickname_in_use(db, normalized)
    )


@router.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: DbSession,
) -> AuthResponse:
    settings = get_settings()
    limiter: LoginRateLimiter = request.app.state.registration_rate_limiter
    rate_key = limiter.key(_request_host(request), "registration")
    if await limiter.is_limited(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Please try again later.",
            headers={"Retry-After": str(settings.registration_window_seconds)},
        )
    await limiter.record_failure(rate_key)

    if await db.scalar(select(User.id).where(func.lower(User.email) == str(payload.email))):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    if await _nickname_in_use(db, payload.nickname):
        raise HTTPException(status_code=409, detail="This nickname is already in use.")

    user = User(
        email=str(payload.email),
        nickname=payload.nickname,
        nickname_normalized=nickname_key(payload.nickname),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        platform_role=PlatformRole.USER.value,
        is_active=True,
        is_verified=False,
        is_approved=False,
    )
    db.add(user)
    try:
        await db.flush()
        workspace = Workspace(
            name=f"Operação de {payload.nickname}"[:160],
            slug=await _workspace_slug(db, payload.nickname),
            owner_id=user.id,
            status="ACTIVE",
        )
        db.add(workspace)
        await db.flush()
        membership = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER.value,
            status="ACTIVE",
        )
        db.add(membership)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this email or nickname already exists.",
        ) from None

    await db.refresh(user)
    csrf_token = csrf_token_for(request)
    return AuthResponse(user=_user_response(user, membership), csrf_token=csrf_token)


@router.post("/auth/login", response_model=AuthResponse, dependencies=[Depends(require_csrf)])
async def login(payload: LoginRequest, request: Request, db: DbSession) -> AuthResponse:
    settings = get_settings()
    limiter: LoginRateLimiter = request.app.state.login_rate_limiter
    rate_key = limiter.key(_request_host(request), str(payload.email))
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
    if not user.is_approved:
        await limiter.record_failure(rate_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta aguarda aprovação do administrador.",
        )

    membership = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id, WorkspaceMember.status == "ACTIVE")
        .order_by(WorkspaceMember.created_at, WorkspaceMember.workspace_id)
        .limit(1)
    )
    if (
        membership is None
        and user.platform_role != PlatformRole.SUPER_ADMIN.value
        and await db.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.status == "SUSPENDED",
            ).limit(1)
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="O acesso ao workspace foi bloqueado pelo administrador.",
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
    if await _nickname_in_use(db, payload.nickname, user.id):
        raise HTTPException(status_code=409, detail="This nickname is already in use.")
    user.full_name = payload.full_name.strip()
    user.nickname = payload.nickname
    user.nickname_normalized = nickname_key(payload.nickname)
    if "avatar_url" in payload.model_fields_set:
        user.avatar_url = str(payload.avatar_url) if payload.avatar_url else None
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This nickname is already in use.") from None
    await db.refresh(user)
    membership = await _primary_membership(user, db)
    return _user_response(user, membership)


@router.post(
    "/profile/avatar",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_csrf)],
)
async def upload_profile_avatar(
    request: Request,
    user: AuthenticatedUser,
    db: DbSession,
) -> UserResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    avatar_type = PROFILE_AVATAR_TYPES.get(content_type)
    if avatar_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Envie uma imagem JPEG, PNG ou WebP.",
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_PROFILE_AVATAR_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="A imagem do perfil deve ter até 5 MB.",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível verificar o tamanho da imagem.",
            ) from None

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PROFILE_AVATAR_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="A imagem do perfil deve ter até 5 MB.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content or not avatar_type[1](content):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="O conteúdo enviado não corresponde a uma imagem JPEG, PNG ou WebP válida.",
        )

    try:
        storage = SupabaseStorage.from_settings()
    except RuntimeError as exc:
        logger.error("Profile avatar storage is not configured (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O armazenamento de imagens de perfil não está configurado no servidor.",
        ) from None

    previous_path = user.avatar_url
    avatar_path = f"{_AVATAR_STORAGE_PREFIX}{user.id}/{uuid.uuid4()}{avatar_type[0]}"
    try:
        await storage.upload(avatar_path, content, content_type)
    except (SupabaseStorageError, httpx.HTTPError) as exc:
        logger.error("Profile avatar upload failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível salvar a imagem de perfil.",
        ) from None

    user.avatar_url = avatar_path
    try:
        await db.commit()
        await db.refresh(user)
    except SQLAlchemyError as exc:
        await db.rollback()
        try:
            await storage.delete(avatar_path)
        except (SupabaseStorageError, httpx.HTTPError) as cleanup_exc:
            logger.error(
                "Orphaned profile avatar cleanup failed (%s) after database failure (%s).",
                type(cleanup_exc).__name__,
                type(exc).__name__,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A imagem foi enviada, mas não foi possível atualizar o perfil.",
        ) from None

    if previous_path and previous_path.startswith(f"{_AVATAR_STORAGE_PREFIX}{user.id}/"):
        try:
            await storage.delete(previous_path)
        except (SupabaseStorageError, httpx.HTTPError) as exc:
            logger.warning("Old profile avatar cleanup failed (%s).", type(exc).__name__)
    membership = await _primary_membership(user, db)
    return _user_response(user, membership)


@router.get("/profile/avatar")
async def get_profile_avatar(user: AuthenticatedUser) -> RedirectResponse:
    if not user.avatar_url or not user.avatar_url.startswith(_AVATAR_STORAGE_PREFIX):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile avatar not found.")
    try:
        storage = SupabaseStorage.from_settings()
        signed_url = await storage.create_signed_url(user.avatar_url)
    except RuntimeError as exc:
        logger.error("Profile avatar storage is not configured (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O armazenamento de imagens de perfil não está configurado no servidor.",
        ) from None
    except (SupabaseStorageError, httpx.HTTPError) as exc:
        logger.error("Profile avatar URL signing failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível abrir a imagem de perfil.",
        ) from None
    return RedirectResponse(signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


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
