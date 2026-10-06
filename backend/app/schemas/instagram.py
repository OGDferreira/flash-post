from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class InstagramAccountResponse(BaseModel):
    id: UUID
    profile_folder_id: UUID | None
    has_highlights: bool
    username: str
    profile_picture_url: str | None
    follower_count: int | None
    media_count: int | None
    token_expires_at: datetime
    connected_at: datetime
    error_at: datetime | None
    status: str
    status_reason: str | None


class InstagramAccountsResponse(BaseModel):
    can_manage: bool
    can_connect: bool
    accounts: list[InstagramAccountResponse]


class InstagramMetaAppCreateRequest(BaseModel):
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    app_id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^\d+$")]
    app_secret: Annotated[str, Field(min_length=1, max_length=512)]

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Enter a name for this Instagram Login app.")
        return normalized

    @field_validator("app_id", mode="before")
    @classmethod
    def strip_app_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("app_secret")
    @classmethod
    def strip_app_secret(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Enter the Instagram App Secret.")
        return normalized


class InstagramMetaAppUpdateRequest(BaseModel):
    display_name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    app_secret: Annotated[str | None, Field(min_length=1, max_length=512)] = None

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Enter a name for this Instagram Login app.")
        return normalized

    @field_validator("app_secret")
    @classmethod
    def strip_app_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Enter the Instagram App Secret.")
        return normalized

    @model_validator(mode="after")
    def require_update_value(self) -> "InstagramMetaAppUpdateRequest":
        if self.display_name is None and self.app_secret is None:
            raise ValueError("Provide a name or a new Instagram App Secret.")
        return self


class InstagramMetaAppResponse(BaseModel):
    id: UUID
    display_name: str
    meta_app_name: str
    app_id: str
    credential_kind: Literal["legacy", "instagram_business_login"]
    category: str | None
    app_link: str | None
    is_selected: bool
    app_secret_configured: bool


class InstagramMetaAppsResponse(BaseModel):
    can_manage: bool
    selected_app_id: UUID | None
    apps: list[InstagramMetaAppResponse]


class InstagramMetaAppActionResponse(BaseModel):
    selected_app_id: UUID | None
    app: InstagramMetaAppResponse | None


class InstagramConnectResponse(BaseModel):
    authorization_url: str


class InstagramDisconnectResponse(BaseModel):
    meta_revoked: bool


class InstagramAccountHighlightsRequest(BaseModel):
    has_highlights: bool


class InstagramFeedMediaResponse(BaseModel):
    id: str
    media_type: str
    media_url: str | None
    thumbnail_url: str | None
    permalink: str | None
    timestamp: datetime | None
    caption: str | None
    like_count: int | None
    comments_count: int | None


class InstagramAccountFeedResponse(BaseModel):
    account_id: UUID
    username: str
    followers_count: int | None
    media_count: int | None
    follows_count: int | None
    profile_metrics_error: str | None
    media: list[InstagramFeedMediaResponse]
