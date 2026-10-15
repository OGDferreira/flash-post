"""SQLAlchemy models and shared metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.system_setting import SystemSetting
from app.models.diagnostics_event import DiagnosticsEvent
from app.models.smokepay import SmokepayOperation
from app.models.collaborator_invite import CollaboratorInvite
from app.models.collaborator_payment import CollaboratorPayment
from app.models.collaborator_work_day import CollaboratorWorkDay
from app.models.email_account import EmailAccount
from app.models.financial_withdrawal import FinancialWithdrawal
from app.models.instagram_account import InstagramAccount
from app.models.instagram_app_credential import InstagramAppCredential
from app.models.instagram_profile_folder import InstagramProfileFolder
from app.models.instagram_loop import (
    InstagramLoop,
    InstagramLoopAccount,
    InstagramLoopAccountState,
    InstagramLoopMedia,
    InstagramMedia,
    InstagramPublicationJob,
    SharkEvent,
)
from app.models.user import User
from app.models.affiliation import Affiliation
from app.models.shark_account import SharkAccount
from app.models.extension import Extension
from app.models.support import SupportTicket
from app.models.daily_views import InstagramAccountDailyViews
from app.models.sharkbot import SharkLead, SharkTransaction
from app.models.media_insight import InstagramMediaInsight
from app.models.push import DailyViewsGoal, DailyViewsGoalNotification, PushSubscription
from app.models.workspace import Workspace, WorkspaceMember

__all__ = [
    "Affiliation",
    "Base",
    "Extension",
    "InstagramAccountDailyViews",
    "SharkAccount",
    "SupportTicket",
    "CollaboratorInvite",
    "CollaboratorPayment",
    "CollaboratorWorkDay",
    "DailyViewsGoal",
    "DailyViewsGoalNotification",
    "DiagnosticsEvent",
    "EmailAccount",
    "FinancialWithdrawal",
    "InstagramAccount",
    "InstagramAppCredential",
    "InstagramLoop",
    "InstagramLoopAccount",
    "InstagramLoopAccountState",
    "InstagramLoopMedia",
    "InstagramMediaInsight",
    "InstagramMedia",
    "InstagramProfileFolder",
    "InstagramPublicationJob",
    "PushSubscription",
    "SharkEvent",
    "SharkLead",
    "SharkTransaction",
    "SmokepayOperation",
    "SystemSetting",
    "User",
    "Workspace",
    "WorkspaceMember",
]
