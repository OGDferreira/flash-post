"""Funnel folders: a bot runs a folder of funnels and each lead is given one of them, drawn at
random on /start and kept. The lead's own funnel (``lead.flow_id``) is what the engine then runs,
charges and delivers — never the bot's (a folder bot has no ``flow_id``)."""
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TgBot, TgFlow, TgFlowFolderItem, TgLead


async def usable_folder_flow_ids(db: AsyncSession, bot: TgBot) -> list[uuid.UUID]:
    """The funnels in the bot's folder the bot may actually run now: its own (not hidden) or a
    shared funnel still available to it."""
    if bot.folder_id is None:
        return []
    from app.partners.service import shared_funnel_access

    flows = await db.scalars(
        select(TgFlow)
        .join(TgFlowFolderItem, TgFlowFolderItem.flow_id == TgFlow.id)
        .where(TgFlowFolderItem.folder_id == bot.folder_id)
    )
    usable: list[uuid.UUID] = []
    for flow in flows:
        if flow.hidden_by_admin:
            continue
        if flow.workspace_id == bot.workspace_id:
            usable.append(flow.id)
        elif await shared_funnel_access(db, flow, bot.workspace_id) is not None:
            usable.append(flow.id)
    return usable


async def draw_folder_flow(db: AsyncSession, bot: TgBot, lead: TgLead) -> uuid.UUID | None:
    """Give a folder bot's lead a funnel from the folder: drawn once and kept, drawn again only if
    its funnel left the folder or stopped being available. No-op for a single-funnel bot."""
    if bot.folder_id is None:
        return lead.flow_id
    usable = await usable_folder_flow_ids(db, bot)
    if lead.flow_id in usable:
        return lead.flow_id
    lead.flow_id = secrets.choice(usable) if usable else None
    return lead.flow_id


def flow_id_for(bot: TgBot, lead: TgLead | None) -> uuid.UUID | None:
    """The funnel this interaction runs: the lead's own (folder bot) or the bot's single funnel."""
    if bot.folder_id is not None:
        return lead.flow_id if lead is not None else None
    return bot.flow_id
