from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_validator

from app.core.cpf import InvalidCpf, validate_cpf
from app.core.nickname import normalize_nickname


def _normalize_cpf_field(value: str) -> str:
    try:
        return validate_cpf(value)
    except InvalidCpf as exc:
        raise ValueError(str(exc)) from None


class RegisterRequest(BaseModel):
    full_name: Annotated[str, Field(min_length=1, max_length=160)]
    cpf: Annotated[str, Field(min_length=1, max_length=20)]
    email: EmailStr
    nickname: str
    password: Annotated[str, Field(min_length=8, max_length=256)]
    confirm_password: Annotated[str, Field(min_length=8, max_length=256)]
    invite_code: Annotated[str | None, Field(max_length=40)] = None
    # Signed commission offer from the invite link; agreeing is part of signing up.
    invite_terms: Annotated[str | None, Field(max_length=300)] = None

    @field_validator("cpf")
    @classmethod
    def validate_cpf_field(cls, value: str) -> str:
        return _normalize_cpf_field(value)

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
    # The full e-mail OR just the part before the @ (unique per account).
    email: Annotated[str, Field(min_length=1, max_length=320)]
    password: Annotated[str, Field(min_length=1, max_length=256)]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("E-mail ou usuário inválido.")
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
    home_panel: Literal["flashpost", "flashbot"] | None = None
    hide_from_rankings: bool | None = None
    # A one-time pop-up the user closed (e.g. "novidades-2026-11")
    seen_notice: str | None = Field(default=None, max_length=60, pattern=r"^[a-z0-9-]+$")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: str | None
    nickname: str
    full_name: str
    # Formatted CPF (000.000.000-00) or null for accounts that haven't filled it yet.
    cpf: str | None = None
    # False while a required field (today: CPF) is still missing — the app forces
    # the "complete seu cadastro" pop-up until it's true.
    profile_complete: bool = True
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
    # Removed from the platform Instagram app: back to the workspace's own Meta apps.
    platform_app_blocked: bool = False
    hide_from_rankings: bool = False
    seen_notices: list[str] = []


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


class ProfileCompleteRequest(BaseModel):
    """What an existing (incomplete) account fills in to keep using the app.
    Today that's only the CPF; full_name is accepted too in case it's blank."""

    cpf: Annotated[str, Field(min_length=1, max_length=20)]
    full_name: Annotated[str | None, Field(max_length=160)] = None

    @field_validator("cpf")
    @classmethod
    def validate_cpf_field(cls, value: str) -> str:
        return _normalize_cpf_field(value)

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class PasswordChangeRequest(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=256)]
    new_password: Annotated[str, Field(min_length=8, max_length=256)]
    confirm_password: Annotated[str, Field(min_length=8, max_length=256)]
