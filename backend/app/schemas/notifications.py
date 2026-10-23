from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PushConfigResponse(BaseModel):
    supported: bool
    public_key: str | None
    devices: int
    enabled: bool = False  # the user's choice, saved on the account
    prompt_done: bool = False  # the "ativar notificações" prompt was answered once
    impersonating: bool = False


class PushPreferenceRequest(BaseModel):
    enabled: bool | None = None
    prompt_done: bool | None = None


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=40, max_length=200)
    auth: str = Field(min_length=16, max_length=100)


class PushSubscriptionRequest(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2048)
    keys: PushSubscriptionKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2048)


class PushTestResponse(BaseModel):
    delivered: int
    devices: int


class DailyViewsGoalUpdate(BaseModel):
    target_views: int = Field(ge=1, le=1_000_000_000)
    enabled: bool = True
    timezone: str = Field(default="America/Sao_Paulo", min_length=3, max_length=64)


class DailyViewsGoalResponse(BaseModel):
    user_id: UUID
    full_name: str | None = None
    role: str | None = None
    configured: bool
    target_views: int | None
    enabled: bool
    timezone: str
    # Progress for `progress_date` (local day); null views = unknown, not zero.
    progress_date: date | None
    progress_views: int | None
    progress_accounts: int | None
    progress_checked_at: datetime | None
    progress_error: str | None
    notified_today: bool
    # Views are the account-level Insights "views" metric for the local day.
    metric: str = "views_today"


class DailyViewsGoalsResponse(BaseModel):
    goals: list[DailyViewsGoalResponse]
