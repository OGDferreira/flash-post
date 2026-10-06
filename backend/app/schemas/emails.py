from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


EmailAccountStatus = Literal[
    "available", "in_use", "completed", "error", "returned"
]


class EmailAccountCreateRequest(BaseModel):
    supplier: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)
    two_factor_code: str = Field(min_length=1, max_length=512)
    two_factor_password: str = Field(default="", max_length=1024)

    @field_validator("supplier")
    @classmethod
    def clean_supplier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Informe o fornecedor.")
        return cleaned

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value


class EmailAccountUpdateRequest(EmailAccountCreateRequest):
    pass


class EmailAccountStatusRequest(BaseModel):
    status: EmailAccountStatus


class EmailAccountObservationRequest(BaseModel):
    observation: str | None = Field(default=None, max_length=4000)

    @field_validator("observation")
    @classmethod
    def normalize_observation(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class EmailAccountItem(BaseModel):
    id: UUID
    supplier: str
    email: str
    password: str
    responsible: str | None
    status: EmailAccountStatus
    observation: str | None
    two_factor_code: str
    two_factor_password: str
    attachment_url: str | None
    created_at: datetime
    updated_at: datetime


class EmailAccountCounts(BaseModel):
    total: int
    available: int
    in_use: int
    completed: int
    error: int
    returned: int


class EmailAccountsResponse(BaseModel):
    can_manage: bool
    accounts: list[EmailAccountItem]
    counts: EmailAccountCounts


class EmailAccountAttachmentResponse(BaseModel):
    attachment_url: str


class EmailAccountsImportResponse(BaseModel):
    imported_count: int
