"""Super admin: edit milestone push texts and send a test push with real data."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.dependencies import DbSession, SuperAdminUser, require_csrf
from app.core.security import WorkspaceRole
from app.models import InstagramAccount, PushSubscription, SystemSetting, WorkspaceMember
from app.notifications import milestones as ms
from app.notifications.goals import local_day_window, resolve_time_zone
from app.notifications.webpush import WebPushError, get_vapid_keys

router = APIRouter(prefix="/api/admin/notifications", tags=["platform administration"])


class Template(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=240)


class MessagesUpdate(BaseModel):
    messages: dict[str, dict[str, list[Template]]]


class TestRequest(BaseModel):
    kind: str
    threshold: int
    variant: int | None = Field(default=None, ge=0, le=50)


def _serialize(messages) -> dict:
    return {kind: {str(t): v for t, v in table.items()} for kind, table in messages.items()}


@router.get("/messages")
async def get_messages(_admin: SuperAdminUser, db: DbSession) -> dict:
    stored = await db.get(SystemSetting, ms.MESSAGES_SETTING_KEY)
    return {
        "kinds": [
            {"kind": kind, "label": ms.KIND_LABELS[kind], "thresholds": list(thresholds)}
            for kind, thresholds in ms.THRESHOLDS.items()
        ],
        "placeholders": ms.PLACEHOLDERS,
        "messages": _serialize(ms.merge_messages(stored.value if stored else None)),
        "defaults": _serialize(ms.DEFAULT_MESSAGES),
        "customized": stored is not None,
    }


@router.put("/messages", dependencies=[Depends(require_csrf)])
async def save_messages(payload: MessagesUpdate, admin: SuperAdminUser, db: DbSession) -> dict:
    clean: dict[str, dict[str, list[dict[str, str]]]] = {}
    for kind, table in payload.messages.items():
        if kind not in ms.THRESHOLDS:
            raise HTTPException(status_code=422, detail=f"Tipo desconhecido: {kind}.")
        for raw, variants in table.items():
            if not raw.isdigit() or int(raw) not in ms.THRESHOLDS[kind]:
                raise HTTPException(status_code=422, detail=f"Marco inválido: {kind} {raw}.")
            if not 1 <= len(variants) <= 10:
                raise HTTPException(status_code=422, detail="Cada marco precisa de 1 a 10 frases.")
            clean.setdefault(kind, {})[raw] = [v.model_dump() for v in variants]
    stored = await db.get(SystemSetting, ms.MESSAGES_SETTING_KEY)
    if stored is None:
        db.add(SystemSetting(key=ms.MESSAGES_SETTING_KEY, value=clean, updated_by_user_id=admin.id))
    else:
        stored.value = clean
        stored.updated_by_user_id = admin.id
    await db.commit()
    return await get_messages(admin, db)


@router.delete("/messages", dependencies=[Depends(require_csrf)])
async def reset_messages(admin: SuperAdminUser, db: DbSession) -> dict:
    stored = await db.get(SystemSetting, ms.MESSAGES_SETTING_KEY)
    if stored is not None:
        await db.delete(stored)
        await db.commit()
    return await get_messages(admin, db)


@router.post("/test", dependencies=[Depends(require_csrf)])
async def send_test(payload: TestRequest, admin: SuperAdminUser, db: DbSession) -> dict:
    if payload.kind not in ms.THRESHOLDS or payload.threshold not in ms.THRESHOLDS[payload.kind]:
        raise HTTPException(status_code=422, detail="Tipo ou marco inválido.")
    messages = await ms.load_messages(db)
    variants = messages[payload.kind][payload.threshold]
    template = variants[payload.variant % len(variants)] if payload.variant is not None else ms.pick(
        messages, payload.kind, payload.threshold
    )
    now = datetime.now(timezone.utc)
    membership = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == admin.id, WorkspaceMember.status == "ACTIVE")
        .order_by(WorkspaceMember.role.desc())
        .limit(1)
    )
    real_value: int | None = None
    account_name: str | None = None
    source = "simulado (sem workspace)"
    if membership is not None:
        scope = ms._Scope(membership.workspace_id, admin.id)
        _day, start, end = local_day_window(now, resolve_time_zone(None))
        if payload.kind == "views":
            real_value = await ms.views_today(db, scope, now, start, {})
        elif payload.kind == "posts":
            real_value = await ms.posts_today(db, scope, membership.role, start, end)
        elif payload.kind == "sales":
            real_value = await ms.sales_today(db, scope, start, end)
        else:
            account = await db.scalar(
                select(InstagramAccount)
                .where(
                    InstagramAccount.workspace_id == membership.workspace_id,
                    InstagramAccount.follower_count.is_not(None),
                )
                .order_by(InstagramAccount.follower_count.desc())
                .limit(1)
            )
            if account is not None:
                real_value, account_name = account.follower_count, account.username
        source = "dados reais do seu workspace de hoje" if real_value is not None else "simulado (sem dados)"
    value = real_value if real_value is not None else payload.threshold
    title, body = ms.render(template, value, account_name, admin.nickname or admin.full_name)
    subscriptions = (
        await db.scalars(select(PushSubscription).where(PushSubscription.user_id == admin.id))
    ).all()
    delivered = 0
    if subscriptions:
        try:
            keys = await get_vapid_keys(db)
        except (WebPushError, RuntimeError, ValueError):
            raise HTTPException(status_code=503, detail="Notificações push indisponíveis.") from None
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            delivered, _transient = await ms.push_to(
                db,
                subscriptions,
                {"title": title, "body": body, "url": "/admin/notifications", "tag": "admin-milestone-test"},
                keys,
                client,
                "admintest",
            )
        await db.commit()
    return {
        "title": title,
        "body": body,
        "value": value,
        "source": source,
        "devices": len(subscriptions),
        "delivered": delivered,
        "is_owner": membership is not None and membership.role == WorkspaceRole.OWNER.value,
    }
