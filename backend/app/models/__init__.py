"""SQLAlchemy models and shared metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.system_setting import SystemSetting
from app.models.instagram_account import InstagramAccount
from app.models.instagram_app_credential import InstagramAppCredential
from app.models.instagram_loop import (
    InstagramLoop,
    InstagramLoopAccount,
    InstagramPublicationJob,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

__all__ = [
    "Base",
    "InstagramAccount",
    "InstagramAppCredential",
    "InstagramLoop",
    "InstagramLoopAccount",
    "InstagramPublicationJob",
    "SystemSetting",
    "User",
    "Workspace",
    "WorkspaceMember",
]
