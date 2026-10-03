from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class InstagramAccountResponse(BaseModel):
    id: UUID
    username: str
    token_expires_at: datetime
    connected_at: datetime


class InstagramAccountsResponse(BaseModel):
    can_manage: bool
    accounts: list[InstagramAccountResponse]


class InstagramAppSettingsRequest(BaseModel):
    app_id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^\d+$")]
    app_secret: Annotated[str | None, Field(max_length=512)] = None

    @field_validator("app_id", mode="before")
    @classmethod
    def strip_app_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("app_secret")
    @classmethod
    def strip_app_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class InstagramAppSettingsResponse(BaseModel):
    configured: bool
    app_id: str | None
    app_secret_configured: bool


class InstagramConnectResponse(BaseModel):
    authorization_url: str


class InstagramDisconnectResponse(BaseModel):
    meta_revoked: bool
