"""SQLAlchemy models and shared metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.system_setting import SystemSetting
from app.models.collaborator_payment import CollaboratorPayment
from app.models.collaborator_work_day import CollaboratorWorkDay
from app.models.instagram_account import InstagramAccount
from app.models.instagram_app_credential import InstagramAppCredential
from app.models.instagram_profile_folder import InstagramProfileFolder
from app.models.instagram_loop import (
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
    SharkEvent,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

__all__ = [
    "Base",
    "CollaboratorPayment",
    "CollaboratorWorkDay",
    "InstagramAccount",
    "InstagramAppCredential",
    "InstagramLoop",
    "InstagramLoopAccount",
    "InstagramLoopMedia",
    "InstagramMedia",
    "InstagramProfileFolder",
    "InstagramPublicationJob",
    "SharkEvent",
    "SystemSetting",
    "User",
    "Workspace",
    "WorkspaceMember",
]
