from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class InstagramProfileFolderAccount(BaseModel):
    id: UUID
    profile_folder_id: UUID | None = None
    username: str
    profile_picture_url: str | None
    status: str
    connected_at: datetime
    error_at: datetime | None


class InstagramProfileFolderResponse(BaseModel):
    id: UUID
    name: str
    color: str
    created_at: datetime
    accounts: list[InstagramProfileFolderAccount]


class InstagramProfileFoldersResponse(BaseModel):
    folders: list[InstagramProfileFolderResponse]
    accounts: list[InstagramProfileFolderAccount]


class InstagramProfileFolderCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")] = "#00c9d8"

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Informe um nome para a pasta.")
        return normalized


class InstagramProfileFolderUpdateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Informe um nome para a pasta.")
        return normalized


class InstagramProfileFolderAccountsRequest(BaseModel):
    account_ids: Annotated[list[UUID], Field(max_length=1000)]

    @field_validator("account_ids")
    @classmethod
    def unique_account_ids(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Cada conta pode ser selecionada apenas uma vez.")
        return values
