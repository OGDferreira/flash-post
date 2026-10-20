"""Home preference persistence and FlashBot calendar/PIX regressions."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import DailyViewsGoal, TgOrder
from tests.test_telegram_bots import _login, _setup, _send, _start, _tap, _signed, _paid_event, apis  # noqa: F401


@pytest.mark.anyio
async def test_home_preference_persists_and_is_user_scoped(client, db_session, owner, collaborator):
    headers = await _login(client)
    assert (await client.get('/api/auth/me')).json()['home_panel'] is None
    assert (await client.patch('/api/profile/preferences', json={'home_panel': 'flashbot'})).status_code == 403
    assert (await client.patch('/api/profile/preferences', headers=headers, json={'home_panel': 'invalid'})).status_code == 422
    for panel in ('flashbot', 'flashpost'):
        response = await client.patch('/api/profile/preferences', headers=headers, json={'home_panel': panel})
        assert response.status_code == 200, response.text
        assert response.json()['home_panel'] == panel
        await db_session.refresh(owner[0])
        assert owner[0].home_panel == panel
        assert (await client.get('/api/auth/me')).json()['home_panel'] == panel
    client.cookies.clear()
    csrf = (await client.get('/api/auth/csrf')).json()['csrf_token']
    response = await client.post('/api/auth/login', headers={'X-CSRF-Token': csrf}, json={'email': collaborator.email, 'password': 'collaborator password'})
    assert response.status_code == 200
    assert response.json()['user']['home_panel'] is None
    headers = {'X-CSRF-Token': response.json()['csrf_token']}
    assert (await client.patch('/api/profile/preferences', headers=headers, json={'home_panel': 'flashbot'})).status_code == 403
    assert owner[0].home_panel == 'flashpost'


@pytest.mark.anyio
async def test_pix_conversion_uses_gateway_orders_and_deduplicated_payments(client, db_session, owner, apis, monkeypatch):
    headers = await _login(client)
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot['id'], _start())
    await _send(client, db_session, bot['id'], _tap('plan:vip'))
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    raw, sig = _signed(_paid_event(order.id))
    for _ in range(2):
        assert (await client.post('/api/bots/pay/smokepay', content=raw, headers=sig)).status_code == 200
    await db_session.refresh(order)
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    monkeypatch.setattr('app.bots.router.utc_now', lambda: now)
    order.created_at = now - timedelta(hours=1)
    order.paid_at = now
    def extra(tx, status, created, paid=None):
        return TgOrder(workspace_id=order.workspace_id, bot_id=order.bot_id, lead_id=order.lead_id,
                       flow_id=order.flow_id, offer_id='vip', offer_name='VIP', amount=Decimal('19.90'),
                       gateway_transaction_id=tx, status=status, created_at=created, paid_at=paid)
    db_session.add_all([
        extra('pending-pix', 'pending', now),
        extra(None, 'failed', now),  # gateway failed: no PIX was generated
        extra('', 'failed', now),
        extra('tomorrow', 'paid', now + timedelta(days=1), now + timedelta(days=1)),
    ])
    await db_session.commit()
    data = (await client.get('/api/bots/stats?period=today')).json()
    assert data['totals']['pix_generated'] == 2
    assert data['totals']['pix_paid'] == 1
    assert data['totals']['conversion'] == 50.0
    assert data['totals']['sales'] == 1  # duplicate webhook was not another sale
    # Existing convention: created_at for generation, paid_at for payment.
    order.created_at = now - timedelta(days=2)
    await db_session.commit()
    data = (await client.get('/api/bots/stats?period=today')).json()
    assert data['totals']['pix_generated'] == 1 and data['totals']['pix_paid'] == 1
    assert data['totals']['conversion'] == 100
    zero = (await client.get('/api/bots/stats?period=custom&start_date=2026-09-01&end_date=2026-09-01')).json()
    assert zero['totals']['conversion'] == 0 and zero['totals']['pix_generated'] == 0


@pytest.mark.anyio
async def test_user_calendar_and_rolling_30_days_fill_empty_days(client, db_session, owner, apis, monkeypatch):
    headers = await _login(client)
    bot, _ = await _setup(client, headers)
    await _send(client, db_session, bot['id'], _start())
    await _send(client, db_session, bot['id'], _tap('plan:vip'))
    await db_session.commit()
    order = await db_session.scalar(select(TgOrder))
    # 00:30 on Oct 20 in Brasília; still Oct 19 in Rio Branco.
    now = datetime(2026, 10, 20, 3, 30, tzinfo=timezone.utc)
    monkeypatch.setattr('app.bots.router.utc_now', lambda: now)
    order.created_at = datetime(2026, 10, 19, 5, tzinfo=timezone.utc)  # local midnight, included
    order.paid_at = now
    order.status = 'paid'
    db_session.add(DailyViewsGoal(workspace_id=owner[1].id, user_id=owner[0].id, target_views=100, timezone='America/Rio_Branco'))
    await db_session.commit()
    today = (await client.get('/api/bots/stats')).json()
    assert today['time_zone'] == 'America/Rio_Branco'
    assert today['period_label'] == '19/10/2026'
    assert len(today['series']) == 1 and today['series'][0]['date'] == '2026-10-19'
    assert today['totals']['pix_paid'] == 1 and today['totals']['pix_generated'] == 1
    chart = (await client.get('/api/bots/stats?period=30d')).json()
    assert len(chart['series']) == 30
    assert chart['series'][0]['date'] == '2026-09-20'
    assert chart['series'][-1]['date'] == '2026-10-19'
    assert all(point['revenue'] == 0 for point in chart['series'][:-1])
    assert chart['series'][-1]['revenue'] == 19.9
    assert (await client.get('/api/bots/stats?period=all')).status_code == 422
