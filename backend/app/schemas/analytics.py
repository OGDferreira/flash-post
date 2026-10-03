from datetime import date
from uuid import UUID

from pydantic import BaseModel


class InstagramAccountAnalytics(BaseModel):
    account_id: UUID
    username: str
    profile_picture_url: str | None
    follower_count: int | None
    media_count: int | None
    published_posts: int
    queued_posts: int
    failed_posts: int


class DailyPublicationMetric(BaseModel):
    day: date
    published_posts: int


class InstagramAnalyticsSummary(BaseModel):
    period: str
    followers_count: int | None
    media_count: int | None
    active_accounts: int
    published_posts: int
    queued_posts: int
    failed_posts: int
    accounts: list[InstagramAccountAnalytics]
    daily_publications: list[DailyPublicationMetric]
