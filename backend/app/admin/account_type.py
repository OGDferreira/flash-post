"""Super Admin: change what kind of account a user has. The user's panel follows on their
next request, with no new sign-in.

* owner        — independent owner of their own operation (created if they never had one)
* partner      — owner of their own operation and "sócio" of a chief (the chief can share
                 funnels and loops with them; the chief's commission is the given percent)
* collaborator — works in another owner's operation (Flash Post collaborator panel)

Nothing is deleted: the user's own operation and old team memberships are only suspended
(``SUSPENDED``) and come back if the account is switched back; a partnership is ended
(``ENDED``) and reused if they become a partner again.
"""

import re
import uuid
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models import Affiliation, User, Workspace, WorkspaceMember

AccountType = Literal["owner", "partner", "collaborator"]


class AccountTypeRequest(BaseModel):
    type: AccountType
    chief_user_id: uuid.UUID | None = None  # partner
    percent: Decimal = Field(default=Decimal("0"), ge=0, le=90, decimal_places=2)  # partner
    workspace_id: uuid.UUID | None = None  # collaborator


async def options(db: AsyncSession, user: User) -> dict:
    """Who can be the chief (owners that are not partners themselves) and which operations
    can take a collaborator."""
    partners = set(await db.scalars(select(Affiliation.affiliate_user_id).where(Affiliation.status == "ACTIVE")))
    owners = (await db.execute(
        select(User.id, User.full_name, Workspace.id, Workspace.name)
        .join(Workspace, Workspace.owner_id == User.id)
        .join(WorkspaceMember, (WorkspaceMember.workspace_id == Workspace.id) & (WorkspaceMember.user_id == User.id))
        .where(User.is_active.is_(True), Workspace.status == "ACTIVE", WorkspaceMember.status == "ACTIVE",
               WorkspaceMember.role == "OWNER")
        .order_by(User.full_name)
    )).all()
    link = await db.scalar(select(Affiliation).where(Affiliation.affiliate_user_id == user.id))
    return {
        "chiefs": [
            {"id": str(uid), "name": name} for uid, name, _wid, _wname in owners
            if uid != user.id and uid not in partners
        ],
        "workspaces": [
            {"id": str(wid), "name": wname, "owner_name": name} for uid, name, wid, wname in owners if uid != user.id
        ],
        "current": {
            "chief_user_id": str(link.chief_user_id) if link and link.status == "ACTIVE" else None,
            "percent": str(link.participation_percent) if link and link.status == "ACTIVE" else None,
        },
    }


async def _own_workspace(db: AsyncSession, user: User) -> Workspace:
    """The user's own operation, active again; a new one when they never had it."""
    workspace = await db.scalar(
        select(Workspace).where(Workspace.owner_id == user.id).order_by(Workspace.created_at).limit(1)
    )
    if workspace is None:
        base = re.sub(r"[^a-z0-9-]+", "-", (user.nickname or user.full_name or "operacao").lower()).strip("-")[:40] or "operacao"
        slug, n = base, 1
        while await db.scalar(select(Workspace.id).where(Workspace.slug == slug)):
            n += 1
            slug = f"{base}-{n}"
        workspace = Workspace(name=f"Operação de {user.nickname or user.full_name}"[:160], slug=slug,
                              owner_id=user.id, status="ACTIVE")
        db.add(workspace)
        await db.flush()
    workspace.status = "ACTIVE"
    member = await db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == user.id)
    )
    if member is None:
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    else:
        member.role, member.status = "OWNER", "ACTIVE"
    return workspace


async def _suspend_teams(db: AsyncSession, user: User, keep: uuid.UUID | None = None) -> None:
    """Leave the other owners' teams (suspended, payment history kept)."""
    for member in await db.scalars(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id, WorkspaceMember.role != "OWNER")
    ):
        if member.workspace_id != keep:
            member.status = "SUSPENDED"


async def _end_partnership(db: AsyncSession, user: User) -> None:
    link = await db.scalar(select(Affiliation).where(Affiliation.affiliate_user_id == user.id))
    if link is not None and link.status == "ACTIVE":
        link.status = "ENDED"


async def _has_partners(db: AsyncSession, user: User) -> bool:
    return bool(await db.scalar(
        select(Affiliation.id).where(Affiliation.chief_user_id == user.id, Affiliation.status == "ACTIVE").limit(1)
    ))


async def change(db: AsyncSession, user: User, payload: AccountTypeRequest) -> None:
    if user.platform_role == "SUPER_ADMIN":
        raise HTTPException(status_code=409, detail="O Super Admin não muda de tipo de conta.")

    if payload.type == "owner":
        await _own_workspace(db, user)
        await _suspend_teams(db, user)
        await _end_partnership(db, user)
        return

    if payload.type == "partner":
        if payload.chief_user_id is None or payload.chief_user_id == user.id:
            raise HTTPException(status_code=422, detail="Escolha de quem ele vai ser sócio.")
        chief = await db.get(User, payload.chief_user_id)
        if chief is None or not chief.is_active:
            raise HTTPException(status_code=422, detail="Dono não encontrado.")
        if await db.scalar(select(Affiliation.id).where(
            Affiliation.affiliate_user_id == chief.id, Affiliation.status == "ACTIVE"
        )):
            raise HTTPException(status_code=422, detail="Esse dono já é sócio de outra pessoa: escolha um dono principal.")
        if await _has_partners(db, user):
            raise HTTPException(status_code=409, detail="Este usuário tem sócios próprios. Encerre essas sociedades antes.")
        await _own_workspace(db, user)
        await _suspend_teams(db, user)
        link = await db.scalar(select(Affiliation).where(Affiliation.affiliate_user_id == user.id))
        if link is None:
            link = Affiliation(chief_user_id=chief.id, affiliate_user_id=user.id)
            db.add(link)
        link.chief_user_id = chief.id
        link.status = "ACTIVE"
        link.participation_percent = payload.percent
        # Set by the Super Admin: the commission is already agreed.
        link.accepted_percent = payload.percent
        link.accepted_at = utc_now()
        return

    # collaborator
    if payload.workspace_id is None:
        raise HTTPException(status_code=422, detail="Escolha a operação em que ele vai colaborar.")
    workspace = await db.get(Workspace, payload.workspace_id)
    if workspace is None or workspace.status != "ACTIVE":
        raise HTTPException(status_code=422, detail="Operação não encontrada.")
    if workspace.owner_id == user.id:
        raise HTTPException(status_code=422, detail="Essa operação é dele mesmo: escolha a operação de outro dono.")
    if await _has_partners(db, user):
        raise HTTPException(status_code=409, detail="Este usuário tem sócios próprios. Encerre essas sociedades antes.")
    # Their own operation is kept (suspended), never deleted.
    for member in await db.scalars(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id, WorkspaceMember.role == "OWNER")
    ):
        member.status = "SUSPENDED"
    await _suspend_teams(db, user, keep=workspace.id)
    member = await db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == user.id)
    )
    if member is None:
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="COLLABORATOR", status="ACTIVE"))
    else:
        member.role, member.status = "COLLABORATOR", "ACTIVE"
    await _end_partnership(db, user)
    if user.home_panel == "flashbot":
        user.home_panel = None  # the Flash Bot panel is the owners'
