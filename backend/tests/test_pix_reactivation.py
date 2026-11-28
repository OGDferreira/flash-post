"""Pix expiration with automatic reactivation: the bot regenerates a new Pix on expiry."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import engine
from app.models import TgJob, TgOrder

from test_telegram_bots import _flow, _login, _send, _setup, _start, _tap, apis  # noqa: F401


async def _expire_due(db: AsyncSession) -> None:
    await db.execute(
        update(TgJob).where(TgJob.kind == "expire_order", TgJob.status == "pending")
        .values(run_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await db.commit()
    await engine.run_due_jobs(db)


def _payment(**over) -> dict:
    base = {"expiration_minutes": 15, "reactivation_enabled": True, "reactivation_limit": 1,
            "reactivation_text": "Venceu, gerei um novo pra você."}
    base.update(over)
    return base


async def _pending(db: AsyncSession) -> TgOrder | None:
    return await db.scalar(select(TgOrder).where(TgOrder.status == "pending").order_by(TgOrder.created_at.desc()))


@pytest.mark.anyio
async def test_expiry_reactivates_once_then_falls_back_to_manual(client, db_session: AsyncSession, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[], payment=_payment(reactivation_limit=1)))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert len(apis.methods("pix.create")) == 1

    # First expiry: auto-reactivation sends the notice and a brand-new Pix (no manual button).
    await _expire_due(db_session)
    assert any(b.get("text") == "Venceu, gerei um novo pra você." for _, b in apis.calls)
    assert len(apis.methods("pix.create")) == 2
    orders = list(await db_session.scalars(select(TgOrder).where(TgOrder.offer_id == "vip")))
    assert len(orders) == 2
    assert await db_session.scalar(select(func.count(TgOrder.id)).where(TgOrder.status == "pending")) == 1

    # Second expiry: the limit (1) is reached -> the manual "Pix expirado" message with a button.
    await _expire_due(db_session)
    assert len(apis.methods("pix.create")) == 2  # no third Pix
    last = apis.methods("sendMessage")[-1]
    assert "Gerar novo Pix" in last["reply_markup"]["inline_keyboard"][0][0]["text"]


@pytest.mark.anyio
async def test_reactivation_off_keeps_manual_button(client, db_session: AsyncSession, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[], payment=_payment(reactivation_enabled=False)))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await _expire_due(db_session)
    assert len(apis.methods("pix.create")) == 1  # nothing regenerated
    last = apis.methods("sendMessage")[-1]
    assert "Gerar novo Pix" in last["reply_markup"]["inline_keyboard"][0][0]["text"]


@pytest.mark.anyio
async def test_unlimited_reactivates_every_time(client, db_session: AsyncSession, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[], payment=_payment(reactivation_limit=0)))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    for expected in (2, 3, 4):
        await _expire_due(db_session)
        assert len(apis.methods("pix.create")) == expected
