import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.models import InstagramAppCredential


@pytest.mark.anyio
async def test_meta_webhook_verification_returns_challenge_for_configured_token(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/instagram/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-instagram-webhook-verify-token",
            "hub.challenge": "meta-challenge-123",
        },
    )

    assert response.status_code == 200
    assert response.text == "meta-challenge-123"
    assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.anyio
async def test_meta_webhook_verification_rejects_a_wrong_token(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/instagram/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "incorrect-token",
            "hub.challenge": "meta-challenge-123",
        },
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_meta_webhook_accepts_valid_signature_and_instagram_payload(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    app_secret = "private-meta-app-secret"
    db_session.add(
        InstagramAppCredential(
            workspace_id=workspace.id,
            display_name="Selected Meta app",
            meta_app_name="Selected Meta app",
            app_id="1234567890",
            encrypted_app_secret=encrypt_value("selected-app-secret"),
            is_selected=True,
        )
    )
    db_session.add(
        InstagramAppCredential(
            workspace_id=workspace.id,
            display_name="Other Meta app",
            meta_app_name="Other Meta app",
            app_id="9876543210",
            encrypted_app_secret=encrypt_value(app_secret),
            is_selected=False,
        )
    )
    await db_session.commit()
    body = json.dumps(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": "17840000000000000",
                    "changes": [{"field": "comments", "value": {"id": "comment-id"}}],
                }
            ],
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()

    response = await client.post(
        "/api/instagram/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"received": True, "entry_count": 1}


@pytest.mark.anyio
async def test_meta_webhook_rejects_invalid_signature(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    db_session.add(
        InstagramAppCredential(
            workspace_id=workspace.id,
            display_name="Test Meta app",
            meta_app_name="Test Meta app",
            app_id="1234567890",
            encrypted_app_secret=encrypt_value("private-meta-app-secret"),
            is_selected=True,
        )
    )
    await db_session.commit()
    body = b'{"object":"instagram","entry":[]}'

    response = await client.post(
        "/api/instagram/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_meta_webhook_rejects_oversized_payload(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/instagram/webhook",
        content=b"x" * (1_048_577),
    )

    assert response.status_code == 413
