from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.scheduling import apply_bot_schedules
from app.core.crypto import encrypt_value
from app.models import TgBot, TgLead, TgOrder


def _bot(workspace_id, *, active, tg_bot_id=551):
    return TgBot(
        workspace_id=workspace_id,
        tg_bot_id=tg_bot_id,
        username="sched_bot",
        name="Sched",
        encrypted_token=encrypt_value("1:x"),
        webhook_secret="s" * 32,
        is_active=active,
    )


@pytest.mark.anyio
async def test_scheduled_bot_activates_when_due(db_session: AsyncSession, owner) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    bot = _bot(workspace.id, active=False, tg_bot_id=561)
    bot.scheduled_activate_at = now - timedelta(minutes=1)
    db_session.add(bot)
    await db_session.commit()

    changed = await apply_bot_schedules(db_session)
    assert changed == 1
    await db_session.refresh(bot)
    assert bot.is_active is True
    assert bot.scheduled_activate_at is None
    assert bot.schedule_activated_at is not None


@pytest.mark.anyio
async def test_future_launch_stays_waiting(db_session: AsyncSession, owner) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    bot = _bot(workspace.id, active=False, tg_bot_id=562)
    bot.scheduled_activate_at = now + timedelta(hours=2)
    db_session.add(bot)
    await db_session.commit()

    changed = await apply_bot_schedules(db_session)
    assert changed == 0
    await db_session.refresh(bot)
    assert bot.is_active is False  # still "aguardando"


@pytest.mark.anyio
async def test_scheduled_deactivation_by_time(db_session: AsyncSession, owner) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    bot = _bot(workspace.id, active=True, tg_bot_id=563)
    bot.scheduled_deactivate_at = now - timedelta(minutes=1)
    db_session.add(bot)
    await db_session.commit()

    await apply_bot_schedules(db_session)
    await db_session.refresh(bot)
    assert bot.is_active is False
    assert bot.scheduled_deactivate_at is None


@pytest.mark.anyio
async def test_deactivation_after_sales_target(db_session: AsyncSession, owner) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    bot = _bot(workspace.id, active=True, tg_bot_id=564)
    bot.auto_deactivate_after_sales = 2
    bot.schedule_activated_at = now - timedelta(hours=1)
    db_session.add(bot)
    await db_session.flush()
    lead = TgLead(workspace_id=workspace.id, bot_id=bot.id, tg_user_id=9, chat_id=9, first_name="L")
    db_session.add(lead)
    await db_session.flush()
    for i in range(2):
        db_session.add(
            TgOrder(
                workspace_id=workspace.id, bot_id=bot.id, lead_id=lead.id,
                offer_id=f"p{i}", offer_name="Plano", amount=Decimal("10.00"),
                status="paid", paid_at=now, gateway_transaction_id=f"tx-{bot.tg_bot_id}-{i}",
            )
        )
    await db_session.commit()

    await apply_bot_schedules(db_session)
    await db_session.refresh(bot)
    assert bot.is_active is False
    assert bot.auto_deactivate_after_sales is None


@pytest.mark.anyio
async def test_sales_before_activation_do_not_count(db_session: AsyncSession, owner) -> None:
    _user, workspace = owner
    now = datetime.now(timezone.utc)
    bot = _bot(workspace.id, active=True, tg_bot_id=565)
    bot.auto_deactivate_after_sales = 1
    bot.schedule_activated_at = now  # activation baseline is now
    db_session.add(bot)
    await db_session.flush()
    lead = TgLead(workspace_id=workspace.id, bot_id=bot.id, tg_user_id=11, chat_id=11, first_name="L")
    db_session.add(lead)
    await db_session.flush()
    # A sale that happened before activation must not trip the target.
    db_session.add(
        TgOrder(
            workspace_id=workspace.id, bot_id=bot.id, lead_id=lead.id,
            offer_id="old", offer_name="Plano", amount=Decimal("10.00"),
            status="paid", paid_at=now - timedelta(hours=3), gateway_transaction_id="tx-old",
        )
    )
    await db_session.commit()

    await apply_bot_schedules(db_session)
    await db_session.refresh(bot)
    assert bot.is_active is True  # pre-launch sale ignored
