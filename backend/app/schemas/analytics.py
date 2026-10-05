from datetime import date
from decimal import Decimal
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
    status: str
    leads: int
    pix_generated: int
    pix_paid: int
    pix_paid_amount: Decimal


class DailyPublicationMetric(BaseModel):
    day: date
    published_posts: int


class DailyRevenueMetric(BaseModel):
    day: date
    amount: Decimal


class DailyAccountConnectionMetric(BaseModel):
    day: date
    connected_accounts: int


class AccountConnectionRank(BaseModel):
    user_id: UUID
    full_name: str
    role: str
    connected_accounts: int


class InstagramAnalyticsSummary(BaseModel):
    period: str
    followers_count: int | None
    media_count: int | None
    views_count: int
    missing_permissions: list[str]
    insights_unavailable: bool
    profile_metrics_unavailable: bool
    active_accounts: int
    errored_accounts: int
    disconnected_accounts: int
    expired_accounts: int
    active_collaborators: int
    published_posts: int
    queued_posts: int
    failed_posts: int
    owner_connections_today: int
    team_connections_today: int
    leads: int
    pix_generated: int
    pix_paid: int
    pix_paid_amount: Decimal
    accounts: list[InstagramAccountAnalytics]
    daily_publications: list[DailyPublicationMetric]
    daily_revenue: list[DailyRevenueMetric]
    daily_account_connections: list[DailyAccountConnectionMetric]
    account_connection_ranking: list[AccountConnectionRank]
