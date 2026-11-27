from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.service import resolve_account_diagnostics
from app.models import DiagnosticsEvent
from tests.test_loops import _active_account, _csrf, _login


async def _login_owner(client: AsyncClient) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")


def _server_event(workspace_id, account_id, category="unknown", status="pending"):
    return DiagnosticsEvent(
        workspace_id=workspace_id,
        source="server",
        level="error",
        message=f"Falha {category}",
        path="/workers/loop_scheduler",
        account_id=account_id,
        category=category,
        status=status,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.anyio
async def test_owner_sees_account_health_grouped_by_account(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "conta_saude")
    db_session.add(account)
    await db_session.flush()
    db_session.add_all(
        [
            _server_event(workspace.id, account.id, "unknown"),
            _server_event(workspace.id, account.id, "token"),
        ]
    )
    await db_session.commit()

    await _login_owner(client)
    response = await client.get("/api/diagnostics/account-health")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pending_total"] == 2
    accounts = {a["username"]: a for a in body["accounts"]}
    assert "conta_saude" in accounts
    assert accounts["conta_saude"]["pending_count"] == 2
    assert len(accounts["conta_saude"]["events"]) == 2


@pytest.mark.anyio
async def test_owner_can_resolve_a_single_event(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "resolver")
    db_session.add(account)
    await db_session.flush()
    event = _server_event(workspace.id, account.id, "network")
    db_session.add(event)
    await db_session.commit()

    await _login_owner(client)
    token = await _csrf(client)
    resolved = await client.post(
        f"/api/diagnostics/events/{event.id}/resolve",
        headers={"X-CSRF-Token": token},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"

    health = (await client.get("/api/diagnostics/account-health")).json()
    account_row = next(a for a in health["accounts"] if a["username"] == "resolver")
    assert account_row["pending_count"] == 0
    assert health["pending_total"] == 0


@pytest.mark.anyio
async def test_reconnect_helper_closes_token_events_only(
    db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    account = _active_account(workspace.id, "reconecta")
    db_session.add(account)
    await db_session.flush()
    token_event = _server_event(workspace.id, account.id, "account_disconnected")
    send_event = _server_event(workspace.id, account.id, "video_format")
    db_session.add_all([token_event, send_event])
    await db_session.commit()

    closed = await resolve_account_diagnostics(db_session, account.id)
    await db_session.commit()
    assert closed == 1

    await db_session.refresh(token_event)
    await db_session.refresh(send_event)
    assert token_event.status == "resolved"
    assert send_event.status == "pending"  # a send failure is not cleared by reconnecting


@pytest.mark.anyio
async def test_disconnect_notifies_owner_in_app(
    db_session: AsyncSession, owner
) -> None:
    from app.models import AppNotification
    from app.notifications.account_alerts import notify_account_disconnected
    from sqlalchemy import select as _select

    _user, workspace = owner
    account = _active_account(workspace.id, "offline_conta")
    account.status = "disconnected"
    db_session.add(account)
    await db_session.commit()

    await notify_account_disconnected(db_session, account, "token expirado")
    await db_session.commit()

    notices = list(
        await db_session.scalars(
            _select(AppNotification).where(AppNotification.user_id == workspace.owner_id)
        )
    )
    assert any(n.kind == "account_disconnected" for n in notices)
    notice = next(n for n in notices if n.kind == "account_disconnected")
    assert "offline_conta" in notice.body
    assert str(account.id) in (notice.url or "")


@pytest.mark.anyio
async def test_owner_configures_telegram_alert_channel(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    await _login_owner(client)
    token = await _csrf(client)

    saved = await client.put(
        "/api/diagnostics/alerts/telegram",
        headers={"X-CSRF-Token": token},
        json={"chat_id": 123456789, "bot_id": None},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["chat_id"] == 123456789

    current = await client.get("/api/diagnostics/alerts/telegram")
    assert current.status_code == 200
    assert current.json()["chat_id"] == 123456789
