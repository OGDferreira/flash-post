from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse
import logging
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.core.redaction import install_log_redaction, redact_secrets
from app.models import InstagramAccount, SharkEvent, SharkTransaction


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


def test_redact_secrets_removes_tokens_from_urls_json_and_webhook_paths() -> None:
    text = (
        "Client error '400' for url "
        "'https://graph.instagram.com/v25.0/me?fields=id&access_token=IGAAsecretsecretsecretsecret1' "
        '{"client_secret": "abc123"} Authorization: Bearer abcdefghijklmnop '
        "POST /api/sharkbot/webhook/AbCdEfGhIjKlMnOpQrStUvWx"
    )
    redacted = redact_secrets(text)
    assert "IGAAsecret" not in redacted
    assert "abc123" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "AbCdEfGhIjKlMnOpQrStUvWx" not in redacted
    assert "access_token=[redacted]" in redacted


def test_log_records_are_redacted_without_breaking_args(caplog) -> None:
    install_log_redaction()
    logger = logging.getLogger("flashpost.test.redaction")
    with caplog.at_level(logging.WARNING, logger="flashpost.test.redaction"):
        logger.warning("calling %s", "https://x.test/?access_token=EAAsecretsecretsecretsecret99")
    assert "EAAsecret" not in caplog.text
    assert "access_token=[redacted]" in caplog.text


@pytest.mark.anyio
async def test_sharkbot_payment_resend_with_new_webhook_id_is_not_counted_twice(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    await _login(client, "owner@example.com", "correct horse battery staple")
    config = await client.get("/api/sharkbot/webhook/config")
    webhook_path = urlparse(config.json()["webhook_url"]).path
    transaction_id = f"tx-{uuid.uuid4()}"

    def payload(timestamp: int) -> dict:
        return {
            "event": "payment_approved",
            "webhook_id": f"delivery-{uuid.uuid4()}",
            "timestamp": timestamp,
            "data": {"transaction": {"id": transaction_id, "amount": 50}},
        }

    first = await client.post(webhook_path, json=payload(1789578257))
    resend = await client.post(webhook_path, json=payload(1789578300))
    assert first.json() == {"accepted": 1, "duplicates": 0, "ignored": 0}
    assert resend.json() == {"accepted": 0, "duplicates": 1, "ignored": 0}
    stored = await db_session.scalar(
        select(func.count(SharkTransaction.id)).where(
            SharkTransaction.workspace_id == workspace.id,
            SharkTransaction.transaction_id == transaction_id,
        )
    )
    assert stored == 1


@pytest.mark.anyio
async def test_sharkbot_rejects_unknown_token_before_parsing_body(client: AsyncClient) -> None:
    response = await client.post(
        "/api/sharkbot/webhook/not-a-real-token-value-123456",
        content=b"not json",
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_analytics_account_filter_excludes_unattributed_shark_events(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000999",
        username="filtered_profile",
        encrypted_access_token=encrypt_value("token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        status="connected",
    )
    db_session.add(account)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            SharkTransaction(
                workspace_id=workspace.id,
                account_id=account.id,
                transaction_key=f"tx:{uuid.uuid4().hex}",
                status="paid",
                amount=Decimal("10.00"),
                created_at_source=now,
                paid_at=now,
            ),
            SharkTransaction(
                workspace_id=workspace.id,
                account_id=None,
                transaction_key=f"tx:{uuid.uuid4().hex}",
                status="paid",
                amount=Decimal("99.00"),
                created_at_source=now,
                paid_at=now,
            ),
        ]
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    filtered = await client.get(
        f"/api/analytics/summary?period=today&account_ids={account.id}"
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["pix_paid"] == 1
    assert Decimal(str(filtered.json()["pix_paid_amount"])) == Decimal("10.00")

    workspace_total = await client.get("/api/analytics/summary?period=today")
    assert workspace_total.json()["pix_paid"] == 2


@pytest.mark.anyio
async def test_partial_video_view_failures_are_reported_as_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.analytics import router as analytics_router

    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000555",
        username="partial_views",
        encrypted_access_token=encrypt_value("token-partial"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        connected_at=datetime.now(timezone.utc) - timedelta(days=10),
        status="connected",
    )
    db_session.add(account)
    await db_session.commit()

    async def profile_metrics(*_args):
        return 10, 3, 2

    async def media_views(*_args):
        return 500, 4, ["HTTP 500"]

    async def period_views(*_args):
        return 1234

    monkeypatch.setattr(analytics_router, "fetch_instagram_profile_metrics", profile_metrics)
    monkeypatch.setattr(analytics_router, "fetch_instagram_media_views", media_views)
    monkeypatch.setattr(analytics_router, "fetch_instagram_views", period_views)
    await _login(client, "owner@example.com", "correct horse battery staple")
    response = await client.get(
        "/api/analytics/summary",
        params={"period": "7d", "include_meta_insights": "true", "account_ids": str(account.id)},
    )
    body = response.json()
    assert response.status_code == 200, response.text
    assert body["views_count"] is None
    assert body["views_partial"] is True
    assert body["period_views_count"] == 1234
