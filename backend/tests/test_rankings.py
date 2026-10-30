"""Platform rankings (views for everyone, revenue for the Super Admin) and the useful links."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.crypto import encrypt_value
from app.core.time import local_date
from sqlalchemy import select

from app.models import InstagramAccount, InstagramAccountDailyViews, TgBot, TgLead, TgOrder
from tests.test_affiliates import PASSWORD
from tests.test_partners import CHIEF_PASSWORD, _as, _partner


def _account(workspace_id, username: str) -> InstagramAccount:
    return InstagramAccount(
        workspace_id=workspace_id, instagram_user_id=f"1784{abs(hash(username)) % 10**9}", username=username,
        encrypted_access_token=encrypt_value("t"), token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
        status="connected",
    )


async def _paid(db, workspace_id, amount: str) -> None:
    bot = TgBot(workspace_id=workspace_id, tg_bot_id=abs(hash(str(workspace_id))) % 10**9, username="b", name="b",
                encrypted_token="x", webhook_secret="s" * 32)
    db.add(bot)
    await db.flush()
    lead = TgLead(workspace_id=workspace_id, bot_id=bot.id, tg_user_id=7, chat_id=1)
    db.add(lead)
    await db.flush()
    now = datetime.now(timezone.utc)
    db.add(TgOrder(workspace_id=workspace_id, bot_id=bot.id, lead_id=lead.id, kind="plan", offer_id="vip", offer_name="VIP",
                   offer_snapshot={}, amount=Decimal(amount), status="paid", paid_at=now, expires_at=now))


@pytest.mark.anyio
async def test_views_ranking_orders_users_by_views_in_the_period(client, db_session, owner, super_admin) -> None:
    chief, chief_ws = owner
    partner, partner_ws, _link = await _partner(db_session, owner)
    mine, theirs = _account(chief_ws.id, "chefe_conta"), _account(partner_ws.id, "socio_conta")
    db_session.add_all([mine, theirs])
    await db_session.flush()
    today = local_date(datetime.now(timezone.utc))
    now = datetime.now(timezone.utc)
    db_session.add_all([
        InstagramAccountDailyViews(workspace_id=chief_ws.id, account_id=mine.id, day=today, views=1200, fetched_at=now),
        InstagramAccountDailyViews(workspace_id=partner_ws.id, account_id=theirs.id, day=today, views=5000, fetched_at=now),
        # an old day is outside "today"
        InstagramAccountDailyViews(workspace_id=chief_ws.id, account_id=mine.id, day=today - timedelta(days=40), views=99999, fetched_at=now),
    ])
    await db_session.commit()

    # any signed-in user sees the views ranking (the partner included)
    await _as(client, "socio@example.com", PASSWORD)
    ranking = (await client.get("/api/rankings/views?period=today")).json()["ranking"]
    assert [(row["full_name"], row["views"], row["position"]) for row in ranking] == [
        (partner.full_name, 5000, 1), (chief.full_name, 1200, 2),
    ]
    # the whole history includes the old day
    everything = (await client.get("/api/rankings/views?period=all")).json()["ranking"]
    assert everything[0]["full_name"] == chief.full_name and everything[0]["views"] == 101199

    # a user who opts out disappears and the positions close the gap
    headers = await _as(client, "socio@example.com", PASSWORD)
    saved = await client.patch("/api/profile/preferences", headers=headers, json={"hide_from_rankings": True})
    assert saved.status_code == 200 and saved.json()["hide_from_rankings"] is True
    ranking = (await client.get("/api/rankings/views?period=today")).json()["ranking"]
    assert [(row["full_name"], row["position"]) for row in ranking] == [(chief.full_name, 1)]


@pytest.mark.anyio
async def test_revenue_ranking_is_for_the_super_admin_only(client, db_session, owner, super_admin) -> None:
    chief, chief_ws = owner
    partner, partner_ws, _link = await _partner(db_session, owner)
    await _paid(db_session, chief_ws.id, "19.90")
    await _paid(db_session, partner_ws.id, "49.90")
    await db_session.commit()

    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    assert (await client.get("/api/rankings/revenue?period=today")).status_code in (401, 403)

    await _as(client, "superadmin@example.com", "super admin password")
    ranking = (await client.get("/api/rankings/revenue?period=today")).json()["ranking"]
    assert [(row["full_name"], row["revenue"], row["sales"]) for row in ranking] == [
        (partner.full_name, 49.9, 1), (chief.full_name, 19.9, 1),
    ]


@pytest.mark.anyio
async def test_super_admin_curates_useful_links_everyone_reads_them(client, db_session, owner, super_admin) -> None:
    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    assert (await client.get("/api/links")).json() == {"links": []}
    owner_headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    refused = await client.put("/api/links", headers=owner_headers, json={"links": [{"title": "x", "url": "https://x.com"}]})
    assert refused.status_code in (401, 403)

    admin = await _as(client, "superadmin@example.com", "super admin password")
    saved = await client.put("/api/links", headers=admin, json={"links": [
        {"title": "Grupo de avisos", "url": "https://t.me/flash", "description": "Novidades da plataforma"},
    ]})
    assert saved.status_code == 200
    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    links = (await client.get("/api/links")).json()["links"]
    assert links == [{"title": "Grupo de avisos", "url": "https://t.me/flash", "description": "Novidades da plataforma"}]



@pytest.mark.anyio
async def test_daily_performance_has_views_and_revenue_per_day(client, db_session, owner) -> None:
    _user, workspace = owner
    account = _account(workspace.id, "perf_one")
    db_session.add(account)
    await db_session.flush()
    today = local_date(datetime.now(timezone.utc))
    db_session.add(InstagramAccountDailyViews(workspace_id=workspace.id, account_id=account.id, day=today, views=321, fetched_at=datetime.now(timezone.utc)))
    await _paid(db_session, workspace.id, "5.90")
    await db_session.commit()

    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    response = await client.get("/api/analytics/performance?period=today")
    assert response.status_code == 200, response.text
    days = response.json()["days"]
    assert len(days) == 7  # a one-day period still draws a week
    assert days[-1] == {"day": today.isoformat(), "views": 321, "revenue": 5.9}
    assert days[0]["day"] == (today - timedelta(days=6)).isoformat()


@pytest.mark.anyio
async def test_flash_funnel_counts_each_upsell_step(client, db_session, owner) -> None:
    from app.models import TgJob

    _user, workspace = owner
    await _paid(db_session, workspace.id, "19.90")
    await db_session.flush()
    main = await db_session.scalar(select(TgOrder))
    now = datetime.now(timezone.utc)
    db_session.add_all([
        TgOrder(workspace_id=workspace.id, bot_id=main.bot_id, lead_id=main.lead_id, kind="upsell", offer_id="up0", offer_name="Up",
                offer_snapshot={}, amount=Decimal("9.90"), status="paid", paid_at=now, expires_at=now),
        TgJob(workspace_id=workspace.id, bot_id=main.bot_id, lead_id=main.lead_id, kind="send_upsell", payload={"index": 0, "chain": "c"},
              run_at=now, status="done", idempotency_key="upsell:c:0"),
        TgJob(workspace_id=workspace.id, bot_id=main.bot_id, lead_id=main.lead_id, kind="send_upsell", payload={"index": 1, "chain": "c"},
              run_at=now, status="done", idempotency_key="upsell:c:1"),
    ])
    await db_session.commit()

    await _as(client, "owner@example.com", CHIEF_PASSWORD)
    bots = (await client.get("/api/analytics/flash-funnel?period=today")).json()["bots"]
    assert len(bots) == 1
    bot = bots[0]
    assert (bot["leads"], bot["pix"], bot["sales"], bot["revenue"]) == (1, 1, 1, 29.8)
    assert [(u["step"], u["offered"], u["paid"], u["take_rate"]) for u in bot["upsells"]] == [(1, 1, 1, 100.0), (2, 1, 0, 0.0)]


@pytest.mark.anyio
async def test_super_admin_reads_the_error_log_of_every_workspace(client, db_session, owner, super_admin) -> None:
    from app.models import DiagnosticsEvent

    _user, workspace = owner
    db_session.add(DiagnosticsEvent(workspace_id=workspace.id, source="browser", level="error", message="boom", path="/dashboard"))
    await db_session.commit()
    await _as(client, "superadmin@example.com", "super admin password")
    events = (await client.get("/api/diagnostics/events")).json()["events"]
    assert ("boom", workspace.name) in [(e["message"], e["workspace_name"]) for e in events]
