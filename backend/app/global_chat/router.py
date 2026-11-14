"""Global chat: every platform user in one room, messages gone after 36h.

Text and photos are allowed; sharing a way to reach someone off-platform
(phone, @handle, a number split up with spaces or symbols) is rejected.
"""

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthenticatedUser, DbSession, require_csrf
from app.core.security import PlatformRole
from app.core.time import utc_now
from app.global_chat.filters import contains_contact
from app.models import GlobalChatMessage, User
from app.models.global_chat import MESSAGE_TTL_HOURS

router = APIRouter(prefix="/api/global-chat", tags=["Global chat"])

MAX_BODY_CHARS = 1000
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_MESSAGES_PER_MINUTE = 12
DEFAULT_LIMIT = 60

# Same validators the avatar upload uses: the bytes must really be this image.
_IMAGE_TYPES = {
    "image/jpeg": lambda c: c.startswith(b"\xff\xd8\xff"),
    "image/png": lambda c: c.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda c: len(c) >= 12 and c.startswith(b"RIFF") and c[8:12] == b"WEBP",
}


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)


class MessageView(BaseModel):
    id: UUID
    author_id: UUID
    author_nickname: str
    author_avatar_url: str | None
    body: str | None
    has_image: bool
    image_url: str | None
    is_mine: bool
    can_delete: bool
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageView]
    server_time: datetime


def _is_admin(user: User) -> bool:
    return user.platform_role == PlatformRole.SUPER_ADMIN.value


def _external_avatar(user: User) -> str | None:
    # Only a plain external URL is safe to show cross-workspace; stored/DB avatars
    # need a membership to serve, so the chat falls back to initials for those.
    url = user.avatar_url
    if url and url.startswith(("http://", "https://")):
        return url
    return None


def _view(message: GlobalChatMessage, user: User) -> MessageView:
    is_mine = message.author_user_id == user.id
    return MessageView(
        id=message.id,
        author_id=message.author_user_id,
        author_nickname=message.author_nickname,
        author_avatar_url=message.author_avatar_url,
        body=message.body,
        has_image=message.image_content_type is not None,
        image_url=(
            f"/api/global-chat/messages/{message.id}/photo"
            if message.image_content_type is not None
            else None
        ),
        is_mine=is_mine,
        can_delete=is_mine or _is_admin(user),
        created_at=message.created_at,
    )


async def _enforce_rate_limit(db: AsyncSession, user: User) -> None:
    since = utc_now() - timedelta(seconds=60)
    recent = await db.scalar(
        select(func.count(GlobalChatMessage.id)).where(
            GlobalChatMessage.author_user_id == user.id,
            GlobalChatMessage.created_at >= since,
        )
    )
    if (recent or 0) >= MAX_MESSAGES_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Você está enviando mensagens rápido demais. Espere um instante.",
        )


def _reject_if_contact(text: str | None) -> None:
    if text and contains_contact(text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Não é permitido compartilhar telefone, @ ou contatos no chat.",
        )


@router.get("/messages", response_model=MessageListResponse)
async def list_messages(
    user: AuthenticatedUser,
    db: DbSession,
    after: datetime | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=100),
) -> MessageListResponse:
    now = utc_now()
    base = select(GlobalChatMessage).where(GlobalChatMessage.expires_at > now)
    if after is not None:
        rows = (
            await db.scalars(
                base.where(GlobalChatMessage.created_at > after)
                .order_by(GlobalChatMessage.created_at.asc())
                .limit(limit)
            )
        ).all()
    else:
        latest = (
            await db.scalars(
                base.order_by(GlobalChatMessage.created_at.desc()).limit(limit)
            )
        ).all()
        rows = list(reversed(latest))
    return MessageListResponse(items=[_view(m, user) for m in rows], server_time=now)


@router.post(
    "/messages",
    response_model=MessageView,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def post_message(
    payload: MessageCreate, user: AuthenticatedUser, db: DbSession
) -> MessageView:
    body = " ".join(payload.body.split())
    if not body:
        raise HTTPException(status_code=422, detail="Mensagem vazia.")
    _reject_if_contact(body)
    await _enforce_rate_limit(db, user)
    now = utc_now()
    message = GlobalChatMessage(
        author_user_id=user.id,
        author_nickname=user.nickname,
        author_avatar_url=_external_avatar(user),
        body=body,
        expires_at=now + timedelta(hours=MESSAGE_TTL_HOURS),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return _view(message, user)


@router.post(
    "/messages/photo",
    response_model=MessageView,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def post_photo(
    request: Request,
    user: AuthenticatedUser,
    db: DbSession,
    caption: str = Query(default="", max_length=MAX_BODY_CHARS),
) -> MessageView:
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    validator = _IMAGE_TYPES.get(content_type)
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Envie uma imagem JPEG, PNG ou WebP.",
        )
    caption_text = " ".join(caption.split())
    _reject_if_contact(caption_text)

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="A imagem deve ter até 2 MB.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content or not validator(content):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="O conteúdo enviado não é uma imagem válida.",
        )

    await _enforce_rate_limit(db, user)
    now = utc_now()
    message = GlobalChatMessage(
        author_user_id=user.id,
        author_nickname=user.nickname,
        author_avatar_url=_external_avatar(user),
        body=caption_text or None,
        image_data=content,
        image_content_type=content_type,
        expires_at=now + timedelta(hours=MESSAGE_TTL_HOURS),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return _view(message, user)


@router.get("/messages/{message_id}/photo")
async def get_photo(message_id: UUID, user: AuthenticatedUser, db: DbSession) -> Response:
    now = utc_now()
    message = await db.scalar(
        select(GlobalChatMessage).where(
            GlobalChatMessage.id == message_id,
            GlobalChatMessage.expires_at > now,
        )
    )
    if message is None or message.image_content_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Imagem não encontrada.")
    data = await db.scalar(
        select(GlobalChatMessage.image_data).where(GlobalChatMessage.id == message_id)
    )
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Imagem não encontrada.")
    return Response(
        content=data,
        media_type=message.image_content_type,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/messages/{message_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_message(message_id: UUID, user: AuthenticatedUser, db: DbSession) -> Response:
    message = await db.scalar(
        select(GlobalChatMessage).where(GlobalChatMessage.id == message_id)
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mensagem não encontrada.")
    if message.author_user_id != user.id and not _is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
    await db.delete(message)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def purge_expired_messages(db: AsyncSession) -> int:
    """Delete messages past their 36h life. Returns how many were removed."""
    result = await db.execute(
        delete(GlobalChatMessage).where(GlobalChatMessage.expires_at <= utc_now())
    )
    await db.commit()
    return result.rowcount or 0
