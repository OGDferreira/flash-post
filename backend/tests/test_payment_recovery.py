"""Behavioural trigger: generated a Pix but did not pay -> automatic recovery message."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots import engine
from app.models import TgJob, TgOrder

from test_telegram_bots import _flow, _login, _send, _setup, _start, _tap, apis  # noqa: F401
from test_flashbot_v2 import _pay


RECOVERY = {
    "enabled": True,
    "delay_minutes": 15,
    "text": "Vi que você gerou o Pix e não finalizou. Gero um novo?",
    "new_pix_button": True,
    "button_label": "Gerar novo Pix",
}


async def _run_recovery(db: AsyncSession) -> None:
    await db.execute(
        update(TgJob).where(TgJob.kind == "payment_recovery").values(run_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await db.commit()
    await engine.run_due_jobs(db)


@pytest.mark.anyio
async def test_recovery_fires_with_new_pix_button_when_unpaid(client, db_session: AsyncSession, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[], payment_recovery=RECOVERY))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))

    job = await db_session.scalar(select(TgJob).where(TgJob.kind == "payment_recovery"))
    assert job is not None and job.idempotency_key == f"payrec:{job.lead_id}"
    # A second Pix tap does not queue a second recovery (one per lead).
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert len(list(await db_session.scalars(select(TgJob).where(TgJob.kind == "payment_recovery")))) == 1

    await _run_recovery(db_session)
    msg = apis.methods("sendMessage")[-1]
    assert msg["text"] == "Vi que você gerou o Pix e não finalizou. Gero um novo?"
    btn = msg["reply_markup"]["inline_keyboard"][0][0]
    assert btn["text"] == "Gerar novo Pix" and btn["callback_data"] == "plan:vip"


@pytest.mark.anyio
async def test_recovery_is_skipped_after_payment(client, db_session: AsyncSession, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[], payment_recovery=RECOVERY))
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    order = await db_session.scalar(select(TgOrder).where(TgOrder.lead_id.is_not(None)))
    await _pay(client, db_session, order)
    await db_session.commit()

    await _run_recovery(db_session)
    texts = [(b.get("caption") or b.get("text") or "") for _, b in apis.calls]
    assert not any("não finalizou" in t for t in texts)


@pytest.mark.anyio
async def test_recovery_off_queues_nothing(client, db_session: AsyncSession, owner, apis) -> None:
    headers = await _login(client)
    bot, _ = await _setup(client, headers, _flow(welcome=[]))  # payment_recovery disabled by default
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    assert not list(await db_session.scalars(select(TgJob).where(TgJob.kind == "payment_recovery")))
