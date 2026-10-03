import logging
import uuid
from pathlib import PurePosixPath

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import (
    DbSession,
    OwnerAccess,
    WorkspaceMemberAccess,
    require_csrf,
)
from app.core.security import WorkspaceRole
from app.instagram.storage import SupabaseStorage, SupabaseStorageError
from app.models import InstagramMedia, InstagramPublicationJob
from app.schemas.media import InstagramMediaListResponse, InstagramMediaResponse

router = APIRouter(prefix="/api/media", tags=["Instagram media"])
logger = logging.getLogger(__name__)
MAX_MEDIA_BYTES = 50 * 1024 * 1024
SUPPORTED_MEDIA_TYPES = {
    "image/jpeg": "image",
    "video/mp4": "video",
}


def _media_response(media: InstagramMedia) -> InstagramMediaResponse:
    return InstagramMediaResponse(
        id=media.id,
        filename=media.filename,
        mime_type=media.mime_type,
        media_type=media.media_type,
        size_bytes=media.size_bytes,
        caption=media.caption,
        created_at=media.created_at,
    )


def _storage_or_http_error() -> SupabaseStorage:
    try:
        return SupabaseStorage.from_settings()
    except RuntimeError as exc:
        logger.error("Supabase Storage is not configured (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Private media storage is not configured on the server.",
        ) from None


@router.get("", response_model=InstagramMediaListResponse)
async def list_media(
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> InstagramMediaListResponse:
    media = (
        await db.scalars(
            select(InstagramMedia)
            .where(InstagramMedia.workspace_id == access.workspace.id)
            .order_by(InstagramMedia.created_at.desc(), InstagramMedia.id)
        )
    ).all()
    return InstagramMediaListResponse(
        can_manage=access.membership.role == WorkspaceRole.OWNER.value,
        media=[_media_response(item) for item in media],
    )


@router.post(
    "",
    response_model=InstagramMediaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_media(
    request: Request,
    access: OwnerAccess,
    db: DbSession,
    filename: str = Query(min_length=1, max_length=255),
    caption: str | None = Query(default=None, max_length=2200),
) -> InstagramMediaResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    media_type = SUPPORTED_MEDIA_TYPES.get(content_type)
    if media_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a JPEG image or an MP4 video.",
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_MEDIA_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Media files must be 50 MB or smaller.",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The upload size could not be verified.",
            ) from None

    chunks: list[bytes] = []
    size_bytes = 0
    async for chunk in request.stream():
        size_bytes += len(chunk)
        if size_bytes > MAX_MEDIA_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Media files must be 50 MB or smaller.",
            )
        chunks.append(chunk)
    if not size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded media file is empty.",
        )
    content = b"".join(chunks)
    matches_type = (
        content.startswith(b"\xff\xd8\xff")
        if media_type == "image"
        else len(content) >= 12 and content[4:8] == b"ftyp"
    )
    if not matches_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file contents do not match the selected JPEG or MP4 format.",
        )

    safe_filename = PurePosixPath(filename.replace("\\", "/")).name.strip()
    if not safe_filename or safe_filename in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The media filename is invalid.",
        )

    storage = _storage_or_http_error()
    media_id = uuid.uuid4()
    storage_path = f"{access.workspace.id}/{media_id}/{safe_filename}"
    try:
        await storage.upload(storage_path, content, content_type)
    except (SupabaseStorageError, httpx.HTTPError) as exc:
        logger.error("Private media upload failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The media could not be saved to private storage.",
        ) from None

    media = InstagramMedia(
        id=media_id,
        workspace_id=access.workspace.id,
        storage_path=storage_path,
        filename=safe_filename,
        mime_type=content_type,
        media_type=media_type,
        size_bytes=size_bytes,
        caption=caption.strip() if caption and caption.strip() else None,
    )
    db.add(media)
    try:
        await db.commit()
        await db.refresh(media)
    except SQLAlchemyError as exc:
        await db.rollback()
        try:
            await storage.delete(storage_path)
        except (SupabaseStorageError, httpx.HTTPError) as cleanup_exc:
            logger.error(
                "Orphaned media cleanup failed (%s) after metadata persistence failed (%s).",
                type(cleanup_exc).__name__,
                type(exc).__name__,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The media metadata could not be saved.",
        ) from None
    return _media_response(media)


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_media(
    media_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> None:
    media = await db.scalar(
        select(InstagramMedia).where(
            InstagramMedia.id == media_id,
            InstagramMedia.workspace_id == access.workspace.id,
        )
    )
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found.")

    active_job = await db.scalar(
        select(InstagramPublicationJob.id)
        .where(
            InstagramPublicationJob.media_id == media.id,
            InstagramPublicationJob.status.in_(("queued", "publishing")),
        )
        .limit(1)
    )
    if active_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This media is assigned to a publication that is already in progress.",
        )

    storage = _storage_or_http_error()
    try:
        await storage.delete(media.storage_path)
    except (SupabaseStorageError, httpx.HTTPError) as exc:
        logger.error("Private media deletion failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The media could not be removed from private storage.",
        ) from None
    await db.delete(media)
    await db.commit()
