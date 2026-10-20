"""iPhone widget: a read-only token shows today's FlashBot numbers and nothing else."""

import pytest
from sqlalchemy import select

from app.models import TgOrder
from tests.test_partners import CHIEF_PASSWORD, _as
from tests.test_telegram_bots import _paid_event, _send, _setup, _signed, _start, _tap, apis  # noqa: F401


@pytest.mark.anyio
async def test_widget_token_reads_today_and_is_replaced_by_a_new_one(client, db_session, owner, apis) -> None:
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    raw, sig = _signed(_paid_event(order.id))
    assert (await client.post("/api/bots/pay/smokepay", content=raw, headers=sig)).status_code == 200

    assert (await client.post("/api/widget/token")).status_code in (401, 403)  # needs the session + CSRF
    token = (await client.post("/api/widget/token", headers=headers)).json()["token"]
    assert token.startswith("fpw_")

    client.cookies.clear()  # the phone has no session: the token alone
    today = await client.get("/api/widget/today", headers={"Authorization": f"Bearer {token}"})
    assert today.status_code == 200, today.text
    data = today.json()
    assert data["pix_generated"] == 1 and data["pix_paid"] == 1
    assert data["revenue"] == 19.9 and data["profit"] == 18.9  # fake SmokePay: R$ 1,00 fee
    assert data["series"][-1] == 19.9 and data["name"] == "FlashBot"

    # the token reads nothing else, a wrong one is refused, and a new script turns the old one off
    assert (await client.get("/api/wallet", headers={"Authorization": f"Bearer {token}"})).status_code in (401, 403)
    assert (await client.get("/api/widget/today", headers={"Authorization": "Bearer fpw_wrong"})).status_code == 401
    headers = await _as(client, "owner@example.com", CHIEF_PASSWORD)
    newer = (await client.post("/api/widget/token", headers=headers)).json()["token"]
    client.cookies.clear()
    assert (await client.get(f"/api/widget/today?token={token}")).status_code == 401
    assert (await client.get(f"/api/widget/today?token={newer}")).status_code == 200
