"""Platform rankings (views for everyone, revenue for the Super Admin) and the useful links."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.crypto import encrypt_value
from app.core.time import local_date
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
