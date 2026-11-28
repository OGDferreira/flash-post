"""IG Extension — per-workspace password auth and profile config for the FlashPost Chrome extension."""

import secrets
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models import IgExtensionConfig, User, WorkspaceMember

_EXTENSION_ZIP = Path(__file__).parent.parent.parent.parent / "extensions" / "flashpost-ig-extension.zip"

router = APIRouter(prefix="/api/ig-extension", tags=["IG Extension"])

# ─── Schemas ───────────────────────────────────────────────────────────────────


class PasswordPayload(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class ConfigPayload(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    username: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=500)
    profile_photo_url: str | None = Field(default=None, max_length=2048)
    story_photo_url: str | None = Field(default=None, max_length=2048)
    link_url: str | None = Field(default=None, max_length=2048)
    sticker_text: str | None = Field(default=None, max_length=200)
    highlight_title: str | None = Field(default=None, max_length=100)
    sticker_size: float | None = Field(default=None, ge=0.1, le=1.0)
    sticker_x: float | None = Field(default=None, ge=0.0, le=1.0)
    sticker_y: float | None = Field(default=None, ge=0.0, le=1.0)
    sticker_rotation: float | None = Field(default=None, ge=-3.15, le=3.15)


class ConfigResponse(BaseModel):
    full_name: str | None
    username: str | None
    bio: str | None
    profile_photo_url: str | None
    story_photo_url: str | None
    link_url: str | None
    sticker_text: str | None
    highlight_title: str | None
    sticker_size: float | None
    sticker_x: float | None
    sticker_y: float | None
    sticker_rotation: float | None
    has_password: bool
    updated_at: datetime


class AuthPayload(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=128)


class AuthResponse(BaseModel):
    token: str


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _config_response(item: IgExtensionConfig) -> ConfigResponse:
    return ConfigResponse(
        full_name=item.full_name,
        username=item.username,
        bio=item.bio,
        profile_photo_url=item.profile_photo_url,
        story_photo_url=item.story_photo_url,
        link_url=item.link_url,
        sticker_text=item.sticker_text,
        highlight_title=item.highlight_title,
        sticker_size=item.sticker_size,
        sticker_x=item.sticker_x,
        sticker_y=item.sticker_y,
        sticker_rotation=item.sticker_rotation,
        has_password=item.password_hash is not None,
        updated_at=item.updated_at,
    )


async def _get_or_create(db: AsyncSession, workspace_id: uuid.UUID) -> IgExtensionConfig:
    item = await db.scalar(
        select(IgExtensionConfig).where(IgExtensionConfig.workspace_id == workspace_id)
    )
    if item is None:
        item = IgExtensionConfig(workspace_id=workspace_id)
        db.add(item)
        await db.flush()
    return item


# ─── Platform routes (session auth) ────────────────────────────────────────────


@router.get("", response_model=ConfigResponse)
async def get_config_platform(access: OwnerAccess, db: DbSession) -> ConfigResponse:
    item = await _get_or_create(db, access.workspace.id)
    await db.commit()
    return _config_response(item)


@router.put(
    "",
    response_model=ConfigResponse,
    dependencies=[Depends(require_csrf)],
)
async def put_config_platform(
    payload: ConfigPayload, access: OwnerAccess, db: DbSession
) -> ConfigResponse:
    item = await _get_or_create(db, access.workspace.id)
    item.full_name = (payload.full_name or "").strip() or None
    item.username = (payload.username or "").strip() or None
    item.bio = (payload.bio or "").strip() or None
    item.profile_photo_url = (payload.profile_photo_url or "").strip() or None
    item.story_photo_url = (payload.story_photo_url or "").strip() or None
    item.link_url = (payload.link_url or "").strip() or None
    item.sticker_text = (payload.sticker_text or "").strip() or None
    item.highlight_title = (payload.highlight_title or "").strip() or None
    item.sticker_size = payload.sticker_size
    item.sticker_x = payload.sticker_x
    item.sticker_y = payload.sticker_y
    item.sticker_rotation = payload.sticker_rotation
    await db.commit()
    await db.refresh(item)
    return _config_response(item)


@router.post(
    "/password",
    response_model=ConfigResponse,
    dependencies=[Depends(require_csrf)],
)
async def set_extension_password(
    payload: PasswordPayload, access: OwnerAccess, db: DbSession
) -> ConfigResponse:
    item = await _get_or_create(db, access.workspace.id)
    item.password_hash = hash_password(payload.password)
    item.config_token = secrets.token_urlsafe(32)
    await db.commit()
    await db.refresh(item)
    return _config_response(item)


@router.get("/download")
async def download_extension(access: OwnerAccess) -> FileResponse:
    if not _EXTENSION_ZIP.is_file():
        raise HTTPException(status_code=404, detail="Arquivo de extensão não encontrado.")
    return FileResponse(
        _EXTENSION_ZIP,
        media_type="application/zip",
        filename="flashpost-ig-extension.zip",
    )


# ─── Extension-facing routes (public → token) ──────────────────────────────────


@router.post("/auth", response_model=AuthResponse)
async def auth_extension(payload: AuthPayload, db: DbSession) -> AuthResponse:
    user = await db.scalar(
        select(User).where(sa_func.lower(User.email) == payload.email.strip().lower())
    )
    if user is None:
        verify_password(payload.password, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")

    membership = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.role == "OWNER",
        )
    )
    if membership is None:
        verify_password(payload.password, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")

    item = await db.scalar(
        select(IgExtensionConfig).where(IgExtensionConfig.workspace_id == membership.workspace_id)
    )

    if item is None or item.password_hash is None:
        verify_password(payload.password, None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha de extensão não configurada. Acesse a plataforma FlashPost para criar sua senha.",
        )

    if not verify_password(payload.password, item.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")

    if not item.config_token:
        item.config_token = secrets.token_urlsafe(32)
        await db.commit()
        await db.refresh(item)

    return AuthResponse(token=item.config_token)


@router.get("/config", response_model=ConfigResponse)
async def get_config_extension(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ConfigResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token não fornecido.")
    token = authorization.removeprefix("Bearer ").strip()
    item = await db.scalar(
        select(IgExtensionConfig).where(IgExtensionConfig.config_token == token)
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")
    return _config_response(item)
