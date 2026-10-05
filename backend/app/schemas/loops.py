from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class InstagramLoopCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    interval_min_minutes: Annotated[int, Field(ge=1, le=1440)]
    interval_max_minutes: Annotated[int, Field(ge=1, le=1440)]
    post_type: Literal["reels", "images", "both"] = "reels"
    repeat_media: bool = True
    account_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]
    media_ids: list[UUID] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Enter a name for this loop.")
        return normalized

    @field_validator("account_ids")
    @classmethod
    def unique_account_ids(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Each Instagram account can only be selected once.")
        return values

    @field_validator("media_ids")
    @classmethod
    def unique_media_ids(cls, values: list[UUID] | None) -> list[UUID] | None:
        if values is not None and len(set(values)) != len(values):
            raise ValueError("Each media file can only be selected once.")
        return values

    @model_validator(mode="after")
    def valid_interval(self) -> "InstagramLoopCreateRequest":
        if self.interval_max_minutes < self.interval_min_minutes:
            raise ValueError("Maximum interval must be greater than or equal to minimum interval.")
        return self


class InstagramLoopAccountResponse(BaseModel):
    id: UUID
    profile_folder_id: UUID | None
    username: str
    token_expires_at: datetime
    connected_at: datetime
    error_at: datetime | None
    status: str


class InstagramLoopResponse(BaseModel):
    id: UUID
    name: str
    interval_min_minutes: int
    interval_max_minutes: int
    post_type: Literal["reels", "images", "both"]
    repeat_media: bool
    status: Literal["active", "paused"]
    next_run_at: datetime | None
    last_run_at: datetime | None
    accounts: list[InstagramLoopAccountResponse]
    media_ids: list[UUID]
    media_names: list[str]
    media_count: int
    waiting_for_media_count: int
    published_today_count: int
    failed_count: int


class InstagramLoopsResponse(BaseModel):
    can_manage: bool
    can_configure: bool
    can_delete: bool
    publishing_enabled: bool
    loops: list[InstagramLoopResponse]
    available_accounts: list[InstagramLoopAccountResponse]


class InstagramPublicationFailureResponse(BaseModel):
    id: UUID
    loop_name: str
    account_username: str
    media_filename: str | None
    scheduled_for: datetime
    updated_at: datetime
    attempts: int
    error: str


class InstagramPublicationFailuresResponse(BaseModel):
    failures: list[InstagramPublicationFailureResponse]


class InstagramLoopStatusRequest(BaseModel):
    enabled: bool


class InstagramLoopAccountsUpdateRequest(BaseModel):
    account_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]

    @field_validator("account_ids")
    @classmethod
    def unique_account_ids(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Each Instagram account can only be selected once.")
        return values
