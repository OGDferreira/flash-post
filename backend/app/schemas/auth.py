from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_validator

from app.core.nickname import normalize_nickname


class RegisterRequest(BaseModel):
    full_name: Annotated[str, Field(min_length=1, max_length=160)]
    email: EmailStr
    nickname: str
    password: Annotated[str, Field(min_length=8, max_length=256)]
    confirm_password: Annotated[str, Field(min_length=8, max_length=256)]
    invite_code: Annotated[str | None, Field(max_length=40)] = None
    # Signed commission offer from the invite link; agreeing is part of signing up.
    invite_terms: Annotated[str | None, Field(max_length=300)] = None

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be blank.")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Enter a valid email address.")
        return value.strip().casefold()

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, value: str) -> str:
        return normalize_nickname(value)

    @model_validator(mode="after")
    def passwords_must_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class NicknameAvailabilityResponse(BaseModel):
    available: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=256)]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class ProfileUpdateRequest(BaseModel):
    full_name: Annotated[str, Field(min_length=1, max_length=160)]
    nickname: str
    avatar_url: HttpUrl | None = None

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be blank.")
        return normalized

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, value: str) -> str:
        return normalize_nickname(value)


class PreferencesUpdateRequest(BaseModel):
    home_panel: Literal["flashpost", "flashbot"]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: str | None
    nickname: str
    full_name: str
    avatar_url: str | None
    role: str
    workspace_role: str | None
    home_panel: Literal["flashpost", "flashbot"] | None = None
    is_active: bool
    is_verified: bool
    is_approved: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    # Set while a Super Admin is inside this account via "Entrar".
    impersonator_name: str | None = None


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


class PasswordChangeRequest(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=256)]
    new_password: Annotated[str, Field(min_length=8, max_length=256)]
    confirm_password: Annotated[str, Field(min_length=8, max_length=256)]
