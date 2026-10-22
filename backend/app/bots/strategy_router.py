"""Falcon Bot > Pastas de funis and Estratégia.

* A folder groups funnels to test against each other. A bot connected to a folder gives
  each new lead one of its funnels at random (see ``engine.assign_folder_flow``).
* Estratégia compares funnels and folders with real numbers of this operation: starts,
  Pix generated, sales, conversion, gross, net and what each plan sold.
"""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update

from app.analytics.periods import AnalyticsPeriod, period_bounds, period_label
from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.core.time import utc_now
from app.models import TgBot, TgFlow, TgFlowFolder, TgFlowFolderItem, TgLead, TgOrder
from app.partners.service import shared_funnel_access

router = APIRouter(prefix="/api/bots", tags=["Falcon Bot strategy"])
csrf = [Depends(require_csrf)]


class FolderInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    flow_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


async def _usable_flows(db, access, flow_ids: list[uuid.UUID]) -> list[TgFlow]:
    """Own funnels, or funnels shared with this operation (run only, never read)."""
    flows = []
    for flow_id in dict.fromkeys(flow_ids):
        flow = await db.get(TgFlow, flow_id)
        if flow is None or (
            flow.workspace_id != access.workspace.id and await shared_funnel_access(db, flow, access.workspace.id) is None
        ):
            raise HTTPException(status_code=422, detail="Escolha só funis seus ou compartilhados com você.")
        flows.append(flow)
    return flows


async def _owned_folder(db, folder_id: uuid.UUID, access) -> TgFlowFolder:
    folder = await db.get(TgFlowFolder, folder_id)
    if folder is None or folder.workspace_id != access.workspace.id:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")
    return folder


async def _folders_out(db, workspace_id: uuid.UUID) -> list[dict]:
    folders = list(
        await db.scalars(select(TgFlowFolder).where(TgFlowFolder.workspace_id == workspace_id).order_by(TgFlowFolder.name))
    )
    ids = [folder.id for folder in folders] or [uuid.uuid4()]
    items = defaultdict(list)
    for folder_id, flow_id, name, flow_ws in await db.execute(
        select(TgFlowFolderItem.folder_id, TgFlow.id, TgFlow.name, TgFlow.workspace_id)
        .join(TgFlow, TgFlow.id == TgFlowFolderItem.flow_id)
        .where(TgFlowFolderItem.folder_id.in_(ids))
        .order_by(TgFlow.name)
    ):
        items[folder_id].append({"id": str(flow_id), "name": name, "shared": flow_ws != workspace_id})
    bots = defaultdict(list)
    for folder_id, username in await db.execute(
        select(TgBot.folder_id, TgBot.username).where(TgBot.workspace_id == workspace_id, TgBot.folder_id.in_(ids))
    ):
        bots[folder_id].append(username)
    return [
        {"id": str(folder.id), "name": folder.name, "flows": items[folder.id], "bots": sorted(bots[folder.id])}
        for folder in folders
    ]


@router.get("/folders")
async def list_folders(access: OwnerAccess, db: DbSession) -> dict:
    return {"folders": await _folders_out(db, access.workspace.id)}


@router.post("/folders", status_code=201, dependencies=csrf)
async def create_folder(payload: FolderInput, access: OwnerAccess, db: DbSession) -> dict:
    flows = await _usable_flows(db, access, payload.flow_ids)
    folder = TgFlowFolder(workspace_id=access.workspace.id, name=payload.name.strip())
    db.add(folder)
    await db.flush()
    db.add_all(TgFlowFolderItem(folder_id=folder.id, flow_id=flow.id) for flow in flows)
    await db.commit()
    return {"id": str(folder.id), "folders": await _folders_out(db, access.workspace.id)}


@router.put("/folders/{folder_id}", dependencies=csrf)
async def update_folder(folder_id: uuid.UUID, payload: FolderInput, access: OwnerAccess, db: DbSession) -> dict:
    folder = await _owned_folder(db, folder_id, access)
    flows = await _usable_flows(db, access, payload.flow_ids)
    folder.name = payload.name.strip()
    await db.execute(delete(TgFlowFolderItem).where(TgFlowFolderItem.folder_id == folder.id))
    db.add_all(TgFlowFolderItem(folder_id=folder.id, flow_id=flow.id) for flow in flows)
    await db.commit()
    return {"id": str(folder.id), "folders": await _folders_out(db, access.workspace.id)}


@router.delete("/folders/{folder_id}", dependencies=csrf)
async def delete_folder(folder_id: uuid.UUID, access: OwnerAccess, db: DbSession) -> dict:
    """Bots connected to it stop sending funnels until they get a funnel or folder again;
    leads keep the funnel they got."""
    folder = await _owned_folder(db, folder_id, access)
    await db.execute(update(TgBot).where(TgBot.folder_id == folder.id).values(folder_id=None))
    await db.delete(folder)
    await db.commit()
    return {"folders": await _folders_out(db, access.workspace.id)}


# ---------------------------------------------------------------- strategy


def _f(value) -> float:
    return float(value or 0)


def _rate(part: int, base: int) -> float | None:
    return round(part / base * 100, 1) if base else None


@router.get("/strategy")
async def strategy(
    access: OwnerAccess, db: DbSession, period: AnalyticsPeriod = "30d",
    start_date: date | None = None, end_date: date | None = None,
) -> dict:
    """Per funnel and per folder, inside the period: starts (new leads), Pix generated, sales,
    conversion (sales / starts), gross, net (what stayed with this operation after the
    gateway fee, commission and fees) and the sales of each plan. Only this operation's data."""
    workspace_id = access.workspace.id
    start, end = period_bounds(period, start_date, end_date, utc_now())
    starts = dict(
        (
            await db.execute(
                select(TgLead.flow_id, func.count(TgLead.id))
                .where(TgLead.workspace_id == workspace_id, TgLead.created_at >= start, TgLead.created_at < end, TgLead.flow_id.is_not(None))
                .group_by(TgLead.flow_id)
            )
        ).all()
    )
    pix = dict(
        (
            await db.execute(
                select(TgOrder.flow_id, func.count(TgOrder.id))
                .where(TgOrder.workspace_id == workspace_id, TgOrder.created_at >= start, TgOrder.created_at < end, TgOrder.flow_id.is_not(None))
                .group_by(TgOrder.flow_id)
            )
        ).all()
    )
    net = func.coalesce(TgOrder.partner_net, TgOrder.net_amount - func.coalesce(TgOrder.platform_fee, 0), TgOrder.amount)
    paid_where = [
        TgOrder.workspace_id == workspace_id, TgOrder.status == "paid", TgOrder.paid_at >= start, TgOrder.paid_at < end,
        TgOrder.flow_id.is_not(None),
    ]
    sales = {
        flow_id: (int(count), Decimal(gross), Decimal(profit))
        for flow_id, count, gross, profit in await db.execute(
            select(TgOrder.flow_id, func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0), func.coalesce(func.sum(net), 0))
            .where(*paid_where)
            .group_by(TgOrder.flow_id)
        )
    }
    plans = defaultdict(list)
    for flow_id, offer_id, offer_name, count, gross in await db.execute(
        select(TgOrder.flow_id, TgOrder.offer_id, func.max(TgOrder.offer_name), func.count(TgOrder.id), func.coalesce(func.sum(TgOrder.amount), 0))
        .where(*paid_where)
        .group_by(TgOrder.flow_id, TgOrder.offer_id)
    ):
        plans[flow_id].append({"id": offer_id, "name": offer_name, "sales": int(count), "gross": _f(gross)})

    # Funnels of this operation, plus any other funnel its leads or sales came from (shared ones).
    used = set(starts) | set(pix) | set(sales)
    own = list(await db.scalars(select(TgFlow).where(TgFlow.workspace_id == workspace_id)))
    flows = {flow.id: flow for flow in own}
    for flow_id in used - set(flows):
        flow = await db.get(TgFlow, flow_id)
        if flow is not None:
            flows[flow_id] = flow

    def row(flow_ids: list[uuid.UUID]) -> dict:
        s = sum(starts.get(i, 0) for i in flow_ids)
        p = sum(pix.get(i, 0) for i in flow_ids)
        n = sum(sales.get(i, (0, 0, 0))[0] for i in flow_ids)
        gross = sum((sales.get(i, (0, Decimal(0), 0))[1] for i in flow_ids), Decimal(0))
        profit = sum((sales.get(i, (0, 0, Decimal(0)))[2] for i in flow_ids), Decimal(0))
        return {
            "starts": s, "pix": p, "sales": n, "conversion": _rate(n, s), "pix_conversion": _rate(n, p),
            "gross": _f(gross), "net": _f(profit), "ticket": _f(gross / n) if n else None,
        }

    flow_rows = []
    for flow in sorted(flows.values(), key=lambda f: f.name.lower()):
        data = row([flow.id])
        data.update({
            "id": str(flow.id), "name": flow.name, "shared": flow.workspace_id != workspace_id,
            "plans": sorted(plans.get(flow.id, []), key=lambda p: (-p["sales"], p["name"] or "")),
        })
        flow_rows.append(data)

    folder_rows = []
    for folder in await _folders_out(db, workspace_id):
        ids = [uuid.UUID(item["id"]) for item in folder["flows"]]
        data = row(ids)
        members = [r for r in flow_rows if r["id"] in {item["id"] for item in folder["flows"]}]
        best = max(members, key=lambda r: (r["net"], r["sales"]), default=None)
        data.update({
            "id": folder["id"], "name": folder["name"], "bots": folder["bots"],
            "flows": [{"id": r["id"], "name": r["name"], "sales": r["sales"], "conversion": r["conversion"], "net": r["net"]} for r in members],
            "leader": best["name"] if best and best["sales"] else None,
        })
        folder_rows.append(data)

    def top(key: str) -> dict | None:
        ranked = [r for r in flow_rows if r[key] is not None and r["sales"]]
        best = max(ranked, key=lambda r: r[key], default=None)
        return {"id": best["id"], "name": best["name"], "value": best[key]} if best else None

    return {
        "period_label": period_label(start, end),
        "criteria": {
            "starts": "Leads novos do funil no período (/start).",
            "conversion": "Vendas pagas no período ÷ starts no período.",
            "net": "O que ficou com você: líquido após taxa do gateway, comissão e taxas.",
        },
        "leaders": {"sales": top("sales"), "conversion": top("conversion"), "net": top("net")},
        "flows": flow_rows,
        "folders": folder_rows,
    }
