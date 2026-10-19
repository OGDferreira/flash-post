from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class InstagramMediaResponse(BaseModel):
    id: UUID
    filename: str
    mime_type: str
    media_type: Literal["image", "video"]
    size_bytes: int
    caption: str | None
    created_at: datetime
    locked: bool = False
    is_cover: bool = False
    cover_media_id: UUID | None = None


class InstagramMediaListResponse(BaseModel):
    can_manage: bool
    media: list[InstagramMediaResponse]
