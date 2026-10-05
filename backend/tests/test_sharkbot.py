from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.models import InstagramAccount


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def _login(client: AsyncClient, email: str, password: str) -> None:
    token = await _csrf(client)
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_sharkbot_webhook_handles_reference_events_and_idempotently_updates_analytics(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000000",
        username="sharkbot_profile",
        encrypted_access_token=encrypt_value("sharkbot-test-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        status="connected",
    )
    db_session.add(account)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    settings_response = await client.get("/api/sharkbot/webhook/config")
    assert settings_response.status_code == 200, settings_response.text
    webhook_path = urlparse(settings_response.json()["webhook_url"]).path

    payloads = [
        {
            "timestamp": 1789578257,
            "webhook_id": f"fixture-{uuid.uuid4()}",
            "event": "payment_approved",
            "data": {
                "customer": {
                    "first_name": "João",
                    "last_name": "Silva",
                    "username": "joaosilva",
                },
                "transaction": {
                    "id": f"paid-{uuid.uuid4()}",
                    "amount": 97,
                    "plan_name": "Plano Premium",
                },
                "instagram_user_id": account.instagram_user_id,
            },
        },
        {
            "event": "payment_created",
            "timestamp": 1789578257,
            "webhook_id": f"fixture-{uuid.uuid4()}",
            "data": {
                "customer": {"first_name": "João", "last_name": "Silva"},
                "transaction": {"id": f"created-{uuid.uuid4()}", "amount": 97},
                "instagram_user_id": account.instagram_user_id,
            },
        },
        {
            "event": "user_joined",
            "timestamp": 1789578257,
            "webhook_id": f"fixture-{uuid.uuid4()}",
            "data": {
                "customer": {"first_name": "Maria", "last_name": "Souza"},
                "instagram_user_id": account.instagram_user_id,
            },
        },
    ]
    responses = [
        await client.post(webhook_path, json=payload)
        for payload in payloads
    ]
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [response.json()["accepted"] for response in responses] == [1, 1, 1]
    duplicate = await client.post(webhook_path, json=payloads[0])
    assert duplicate.status_code == 200
    assert duplicate.json() == {"accepted": 0, "duplicates": 1}

    metrics = await client.get(
        "/api/analytics/summary",
        params=[("period", "all"), ("account_ids", str(account.id))],
    )
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["leads"] == 1
    assert body["pix_generated"] == 1
    assert body["pix_paid"] == 1
    assert body["pix_paid_amount"] == "97.00"
    account_metrics = body["accounts"][0]
    assert account_metrics["leads"] == 1
    assert account_metrics["pix_generated"] == 1
    assert account_metrics["pix_paid"] == 1
    assert account_metrics["pix_paid_amount"] == "97.00"
    assert len(body["daily_revenue"]) == 1
    assert body["daily_revenue"][0]["amount"] == "97.00"


@pytest.mark.anyio
async def test_sharkbot_webhook_settings_are_owner_only_and_rotatable(
    client: AsyncClient,
    owner,
    collaborator,
) -> None:
    await _login(client, "collaborator@example.com", "collaborator password")
    forbidden = await client.get("/api/sharkbot/webhook/config")
    assert forbidden.status_code == 403

    await _login(client, "owner@example.com", "correct horse battery staple")
    original = await client.get("/api/sharkbot/webhook/config")
    assert original.status_code == 200
    csrf = await _csrf(client)
    rotated = await client.post(
        "/api/sharkbot/webhook/rotate",
        headers={"X-CSRF-Token": csrf},
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["webhook_url"] != original.json()["webhook_url"]
    assert (
        await client.post(
            urlparse(original.json()["webhook_url"]).path,
            json={"event": "user_joined", "data": {}},
        )
    ).status_code == 404


@pytest.mark.anyio
async def test_naive_sharkbot_timestamps_are_interpreted_as_brasilia_local_time(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000001",
        username="local_time_revenue",
        encrypted_access_token=encrypt_value("local-time-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        status="connected",
    )
    db_session.add(account)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    settings = await client.get("/api/sharkbot/webhook/config")
    webhook_path = urlparse(settings.json()["webhook_url"]).path

    received = await client.post(
        webhook_path,
        json={
            "event": "payment_approved",
            "webhook_id": f"local-time-{uuid.uuid4()}",
            "timestamp": "2026-09-16T01:30:00",
            "data": {
                "instagram_user_id": account.instagram_user_id,
                "transaction": {"id": f"local-time-{uuid.uuid4()}", "amount": "12.34"},
            },
        },
    )
    assert received.status_code == 200, received.text

    summary = await client.get(
        "/api/analytics/summary",
        params={
            "period": "custom",
            "start_date": "2026-09-16",
            "end_date": "2026-09-16",
        },
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["pix_paid_amount"] == "12.34"
    assert summary.json()["daily_revenue"] == [
        {"day": "2026-09-16", "amount": "12.34"}
    ]


@pytest.mark.anyio
async def test_sharkbot_rejects_unknown_token_and_invalid_event_payload(
    client: AsyncClient,
    owner,
) -> None:
    _user, _workspace = owner
    assert (
        await client.post(
            "/api/sharkbot/webhook/not-a-valid-token",
            json={"event": "user_joined", "data": {}},
        )
    ).status_code == 404

    await _login(client, "owner@example.com", "correct horse battery staple")
    config = await client.get("/api/sharkbot/webhook/config")
    assert (
        await client.post(
            urlparse(config.json()["webhook_url"]).path,
            json={"event": "unsupported_action", "data": {}},
        )
    ).status_code == 422
