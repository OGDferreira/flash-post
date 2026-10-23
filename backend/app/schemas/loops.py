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
    # Max confirmed publications per account per calendar day (app time zone).
    # Instagram itself allows at most 100 API publications per 24 h.
    daily_limit_per_account: Annotated[int, Field(ge=1, le=100)] = 100
    account_ids: Annotated[list[UUID], Field(max_length=1000)]
    # Folders whose accounts join this loop automatically.
    auto_folder_ids: Annotated[list[UUID], Field(max_length=100)] = []
    media_ids: list[UUID] | None = None
    # Edited post captions of media in this loop (update only); empty clears it.
    media_captions: Annotated[dict[UUID, str | None], Field(max_length=1000)] | None = None
    # per_media: each video keeps its own caption; all: ``caption`` goes on every post.
    caption_mode: Literal["per_media", "all"] = "per_media"
    caption: Annotated[str, Field(max_length=2200)] | None = None
    # Reels cover: auto (Instagram picks), all (``cover_media_id`` on every video)
    # or per_media (``media_covers``: video id -> cover image id, None clears it).
    cover_mode: Literal["auto", "all", "per_media"] = "auto"
    cover_media_id: UUID | None = None
    media_covers: Annotated[dict[UUID, UUID | None], Field(max_length=1000)] | None = None

    @field_validator("caption")
    @classmethod
    def clean_caption(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @field_validator("media_captions")
    @classmethod
    def clean_captions(cls, values: dict[UUID, str | None] | None) -> dict[UUID, str | None] | None:
        if values is None:
            return None
        cleaned: dict[UUID, str | None] = {}
        for media_id, caption in values.items():
            text = (caption or "").strip()
            if len(text) > 2200:
                raise ValueError("A legenda pode ter no máximo 2200 caracteres.")
            cleaned[media_id] = text or None
        return cleaned

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
    def needs_accounts_or_folders(self) -> "InstagramLoopCreateRequest":
        if not self.account_ids and not self.auto_folder_ids:
            raise ValueError("Select at least one account or one folder.")
        return self

    @model_validator(mode="after")
    def cover_chosen(self) -> "InstagramLoopCreateRequest":
        if self.cover_mode == "all" and self.cover_media_id is None and self.post_type != "images":
            raise ValueError("Escolha a imagem de capa usada em todos os vídeos.")
        return self

    @model_validator(mode="after")
    def valid_interval(self) -> "InstagramLoopCreateRequest":
        if self.interval_max_minutes < self.interval_min_minutes:
            raise ValueError(
                "O intervalo máximo precisa ser maior ou igual ao intervalo mínimo."
            )
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
    daily_limit_per_account: int = 100
    post_type: Literal["reels", "images", "both"]
    repeat_media: bool
    caption_mode: Literal["per_media", "all"] = "per_media"
    caption: str | None = None
    cover_mode: Literal["auto", "all", "per_media"] = "auto"
    cover_media_id: UUID | None = None
    status: Literal["active", "paused"]
    shared: bool = False
    shared_with: list[UUID] | None = None
    from_template: bool = False
    # follows a loop the chief shares: media and schedule come from the chief, accounts are the partner's
    linked: bool = False
    customized: bool = False  # a partner's copy that stopped following the chief's loop
    linked_available: bool = False
    next_run_at: datetime | None
    last_run_at: datetime | None
    auto_folder_ids: list[UUID] = []
    accounts: list[InstagramLoopAccountResponse]
    accounts_count: int = 0
    active_accounts_count: int
    media_ids: list[UUID]
    media_names: list[str]
    media_count: int
    video_count: int
    waiting_for_media_count: int
    queued_publication_count: int
    attempts_count: int
    attempts_today_count: int = 0
    published_today_count: int
    failed_today_count: int
    failed_count: int
    latest_failed_at: datetime | None


class InstagramLoopsResponse(BaseModel):
    can_manage: bool
    can_configure: bool
    can_delete: bool
    publishing_enabled: bool
    loops: list[InstagramLoopResponse]
    available_accounts: list[InstagramLoopAccountResponse]
    available_accounts_count: int = 0


class InstagramLoopAccountsPage(BaseModel):
    accounts: list[InstagramLoopAccountResponse]
    total: int
    offset: int
    limit: int
    selected_ids: list[UUID] = []


class InstagramPublicationFailureResponse(BaseModel):
    id: UUID
    account_id: UUID
    loop_name: str
    account_username: str
    media_filename: str | None
    scheduled_for: datetime
    updated_at: datetime
    attempts: int
    error: str
    account_in_loop: bool
    error_category: str | None = None
    loop_id: UUID | None = None
    account_status: str | None = None


class InstagramRetryFailuresRequest(BaseModel):
    job_ids: list[UUID] | None = None
    loop_id: UUID | None = None


class InstagramRetryFailuresResponse(BaseModel):
    requeued: int


class InstagramAccountDailyProgress(BaseModel):
    account_id: UUID
    username: str
    published_today: int
    failed_today: int
    target: int
    token_expires_at: datetime
    # Real state of the account inside this loop:
    # publishing | queued | scheduled | due | daily_limit | loop_paused |
    # disconnected | needs_review | no_media | instagram_cap | failing
    state: str = "scheduled"
    connection_status: str = "connected"
    in_loop: bool = True
    next_run_at: datetime | None = None
    last_published_at: datetime | None = None
    next_video_number: int | None = None
    playlist_size: int = 0
    cycles_completed: int = 0
    last_error: str | None = None
    last_error_at: datetime | None = None
    review_job_id: UUID | None = None


class InstagramLoopHealthResponse(BaseModel):
    loop_id: UUID
    target_per_account: int
    accounts: list[InstagramAccountDailyProgress]


class InstagramAlertsResponse(BaseModel):
    expiring_accounts: list[str]
    expiring_within_days: int
    disconnected_count: int
    restricted_accounts: list[str] = []
    suspended_accounts: list[str] = []
    published_today: int
    failed_today: int
    failure_rate: float
    high_failure_rate: bool

class InstagramPublicationFailuresResponse(BaseModel):
    failures: list[InstagramPublicationFailureResponse]


class InstagramLoopStatusRequest(BaseModel):
    enabled: bool


class InstagramLoopAccountsUpdateRequest(BaseModel):
    account_ids: Annotated[list[UUID], Field(max_length=1000)]
    # Sent (even empty) to also set the folders whose accounts join the loop.
    auto_folder_ids: Annotated[list[UUID], Field(max_length=100)] | None = None

    @model_validator(mode="after")
    def needs_accounts(self) -> "InstagramLoopAccountsUpdateRequest":
        if not self.account_ids and self.auto_folder_ids is None:
            raise ValueError("Select at least one account.")
        return self

    @field_validator("account_ids")
    @classmethod
    def unique_account_ids(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Each Instagram account can only be selected once.")
        return values
