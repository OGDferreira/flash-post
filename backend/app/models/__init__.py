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
from app.models.financial_expense import FinancialExpense
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
from app.models.admin_audit_log import AdminAuditLog
from app.models.affiliation import Affiliation
from app.models.app_notification import AppNotification
from app.models.shark_account import SharkAccount
from app.models.extension import Extension
from app.models.support import SupportTicket
from app.models.daily_views import InstagramAccountDailyViews
from app.models.sharkbot import SharkLead, SharkTransaction
from app.models.media_insight import InstagramMediaInsight
from app.models.push import (
    DailyViewsGoal,
    DailyViewsGoalNotification,
    AccountFollowerMilestone,
    MilestoneNotification,
    PushSubscription,
)
from app.models.workspace import Workspace, WorkspaceMember
from app.models.fee_change_log import FeeChangeLog
from app.models.telegram_bot import (
    AuditEvent,
    TgBot,
    TgCampaign,
    TgCampaignRun,
    TgFlow,
    TgFlowFolder,
    TgFlowFolderItem,
    TgFlowShare,
    TgGatewaySetting,
    TgGroup,
    TgJob,
    TgLead,
    TgMedia,
    TgOrder,
    TgSubscription,
    TgUpdateSeen,
)

__all__ = [
    "AuditEvent",
    "TgFlowFolder",
    "TgFlowFolderItem",
    "TgFlowShare",
    "TgGatewaySetting",
    "AdminAuditLog",
    "AppNotification",
    "TgBot",
    "TgCampaign",
    "TgCampaignRun",
    "TgFlow",
    "TgGroup",
    "TgJob",
    "TgLead",
    "TgMedia",
    "TgOrder",
    "TgSubscription",
    "TgUpdateSeen",
    "Affiliation",
    "Base",
    "Extension",
    "FeeChangeLog",
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
    "FinancialExpense",
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
    "MilestoneNotification",
    "AccountFollowerMilestone",
    "SharkEvent",
    "SharkLead",
    "SharkTransaction",
    "SmokepayOperation",
    "SystemSetting",
    "User",
    "Workspace",
    "WorkspaceMember",
]
