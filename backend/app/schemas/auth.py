from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=256)]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class ProfileUpdateRequest(BaseModel):
    full_name: Annotated[str, Field(min_length=1, max_length=160)]
    avatar_url: HttpUrl | None = None

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be blank.")
        return normalized


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: str | None
    full_name: str
    avatar_url: str | None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class AuthResponse(BaseModel):
    user: UserResponse
    csrf_token: str


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    role: str
    created_at: datetime


class MessageResponse(BaseModel):
    message: str
    csrf_token: str | None = None
