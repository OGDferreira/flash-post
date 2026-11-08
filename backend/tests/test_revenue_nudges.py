"""Daytime revenue pushes for owners: 12h already billed, 16h the projection, 19h with the
active accounts; once each per day, only inside their hour window."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.time import BRAZIL_TIME_ZONE, utc_now
from app.models import InstagramAccount, PushSubscription
from app.notifications.engagement import run_engagement_tick
from tests.test_wallet import _paid


def _at(hour: int, minute: int = 30) -> datetime:
    local = utc_now().astimezone(BRAZIL_TIME_ZONE)
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(timezone.utc)


@pytest.mark.anyio
async def test_revenue_nudges_once_each_in_their_window(db_session, owner) -> None:
    chief, ws = owner
    db_session.add(PushSubscription(user_id=chief.id, workspace_id=ws.id, endpoint="https://push.example/1", p256dh="k", auth="a"))
    db_session.add(InstagramAccount(workspace_id=ws.id, instagram_user_id="1784000000000777", username="conta_ativa",
                                    token_expires_at=utc_now() + timedelta(days=30)))
    await db_session.commit()
    await _paid(db_session, ws)  # R$ 19,90 paid now (today)
    sent: list[dict] = []

    async def push_to(db, subs, payload, keys, client, topic):
        sent.append(payload)
        return 1, 0

    async def keys():
        return object()

    async def views(*_args):
        return None

    async def tick(when: datetime) -> list[dict]:
        before = len(sent)
        await run_engagement_tick(db_session, when, client=None, keys_getter=keys, push_to=push_to, views_today=views)
        return [p for p in sent[before:] if p["tag"] == "fun-revenue_nudge"]

    noon = await tick(_at(12))
    assert len(noon) == 1 and "R$ 19,90" in noon[0]["body"]
    assert await tick(_at(13)) == []  # once a day
    afternoon = await tick(_at(16))
    assert len(afternoon) == 1 and "R$ 19,90" in afternoon[0]["body"]
    assert "R$ 28,95" in afternoon[0]["body"]  # 19,90 x 24 / 16,5h
    evening = await tick(_at(19))
    assert len(evening) == 1 and "1 conta ativa" in evening[0]["body"]
    assert await tick(_at(22)) == []  # past every window: nothing late
