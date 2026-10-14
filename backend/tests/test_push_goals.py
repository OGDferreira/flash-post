import base64
import json
from datetime import date, datetime, timedelta, timezone
import os

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_value
from app.models import (
    DailyViewsGoal,
    DailyViewsGoalNotification,
    InstagramAccount,
    PushSubscription,
)
from app.notifications import goals as goals_module
from app.notifications.webpush import (
    PushResult,
    b64url_decode,
    b64url_encode,
    encrypt_payload,
    get_vapid_keys,
    is_allowed_push_endpoint,
    vapid_authorization,
)

ENDPOINT = "https://fcm.googleapis.com/fcm/send/fake-subscription-id-123456"


def _browser_keys() -> tuple[ec.EllipticCurvePrivateKey, str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return private_key, b64url_encode(public), b64url_encode(os.urandom(16))


def _browser_decrypt(body: bytes, private_key, p256dh: str, auth: str) -> bytes:
    """User-agent side of RFC 8291, used to prove the server encryption is valid."""
    salt, record_size, key_length = body[:16], body[16:20], body[20]
    assert int.from_bytes(record_size, "big") == 4096
    server_public = body[21 : 21 + key_length]
    ciphertext = body[21 + key_length :]
    server_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), server_public)
    shared = private_key.exchange(ec.ECDH(), server_key)
    ikm = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b64url_decode(auth),
        info=b"WebPush: info\x00" + b64url_decode(p256dh) + server_public,
    ).derive(shared)
    key = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    assert plaintext.endswith(b"\x02")
    return plaintext[:-1]


def test_payload_encryption_round_trips_with_browser_keys() -> None:
    private_key, p256dh, auth = _browser_keys()
    message = json.dumps({"title": "Meta diária atingida"}).encode()
    body = encrypt_payload(message, p256dh, auth)
    assert _browser_decrypt(body, private_key, p256dh, auth) == message


@pytest.mark.anyio
async def test_vapid_header_is_a_valid_es256_jwt(db_session: AsyncSession) -> None:
    keys = await get_vapid_keys(db_session)
    again = await get_vapid_keys(db_session)
    assert again.public_key_b64 == keys.public_key_b64  # generated once, persisted
    header_value = vapid_authorization(ENDPOINT, keys, "mailto:ops@example.com")
    token = header_value.split("t=", 1)[1].split(",", 1)[0]
    head, claims, signature = token.split(".")
    raw_signature = b64url_decode(signature)
    der = encode_dss_signature(
        int.from_bytes(raw_signature[:32], "big"), int.from_bytes(raw_signature[32:], "big")
    )
    public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b64url_decode(keys.public_key_b64)
    )
    public_key.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    decoded = json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))
    assert decoded["aud"] == "https://fcm.googleapis.com"
    assert decoded["sub"] == "mailto:ops@example.com"


def test_push_endpoint_allowlist_blocks_arbitrary_hosts() -> None:
    assert is_allowed_push_endpoint(ENDPOINT)
    assert is_allowed_push_endpoint("https://web.push.apple.com/QAbc")
    assert is_allowed_push_endpoint("https://updates.push.services.mozilla.com/wpush/v2/x")
    assert not is_allowed_push_endpoint("http://fcm.googleapis.com/fcm/send/x")
    assert not is_allowed_push_endpoint("https://evil.example/fcm.googleapis.com")
    assert not is_allowed_push_endpoint("https://fcm.googleapis.com.evil.example/x")
    assert not is_allowed_push_endpoint("https://169.254.169.254/latest")
    assert not is_allowed_push_endpoint("https://fcm.googleapis.com:8443/x")


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    return response.json()["csrf_token"]


async def _login(client: AsyncClient, email: str, password: str) -> str:
    token = await _csrf(client)
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json().get("csrf_token") or await _csrf(client)


@pytest.mark.anyio
async def test_push_subscription_api_validates_endpoint_and_keys(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    csrf = await _login(client, "owner@example.com", "correct horse battery staple")
    _private, p256dh, auth = _browser_keys()

    blocked = await client.post(
        "/api/notifications/push/subscriptions",
        headers={"X-CSRF-Token": csrf},
        json={"endpoint": "https://attacker.example/collect", "keys": {"p256dh": p256dh, "auth": auth}},
    )
    assert blocked.status_code == 422

    saved = await client.post(
        "/api/notifications/push/subscriptions",
        headers={"X-CSRF-Token": csrf},
        json={"endpoint": ENDPOINT, "keys": {"p256dh": p256dh, "auth": auth}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["devices"] == 1
    assert saved.json()["supported"] is True
    assert saved.json()["public_key"]

    removed = await client.request(
        "DELETE",
        "/api/notifications/push/subscriptions",
        headers={"X-CSRF-Token": csrf},
        json={"endpoint": ENDPOINT},
    )
    assert removed.status_code == 204
    assert await db_session.scalar(select(func.count(PushSubscription.id))) == 0


@pytest.mark.anyio
async def test_goal_permissions_owner_manages_members_collaborator_only_self(
    client: AsyncClient, db_session: AsyncSession, owner, collaborator
) -> None:
    csrf = await _login(client, "collaborator@example.com", "collaborator password")
    own = await client.put(
        "/api/notifications/goals/me",
        headers={"X-CSRF-Token": csrf},
        json={"target_views": 5000, "enabled": True, "timezone": "America/Manaus"},
    )
    assert own.status_code == 200, own.text
    assert own.json()["target_views"] == 5000
    assert own.json()["progress_views"] is None  # unknown, never a fake zero
    assert (await client.get("/api/notifications/goals")).status_code == 403
    bad_zone = await client.put(
        "/api/notifications/goals/me",
        headers={"X-CSRF-Token": csrf},
        json={"target_views": 10, "timezone": "Mars/Olympus"},
    )
    assert bad_zone.status_code == 422

    await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    client.cookies.clear()
    owner_csrf = await _login(client, "owner@example.com", "correct horse battery staple")
    listed = await client.get("/api/notifications/goals")
    assert listed.status_code == 200
    by_user = {item["user_id"]: item for item in listed.json()["goals"]}
    assert by_user[str(collaborator.id)]["target_views"] == 5000
    updated = await client.put(
        f"/api/notifications/goals/{collaborator.id}",
        headers={"X-CSRF-Token": owner_csrf},
        json={"target_views": 8000, "enabled": True, "timezone": "America/Sao_Paulo"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["target_views"] == 8000


def _account(workspace_id, user_id, suffix: str) -> InstagramAccount:
    return InstagramAccount(
        workspace_id=workspace_id,
        instagram_user_id=f"178400000{suffix}",
        username=f"goal_{suffix}",
        encrypted_access_token=encrypt_value(f"token-{suffix}"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        connected_at=datetime.now(timezone.utc) - timedelta(days=3),
        status="connected",
        connected_by_user_id=user_id,
    )


@pytest.mark.anyio
async def test_goal_tick_notifies_once_per_day_and_target_in_goal_time_zone(
    db_session: AsyncSession, owner, collaborator, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_user, workspace = owner
    collaborator_account = _account(workspace.id, collaborator.id, "101")
    owner_account = _account(workspace.id, owner_user.id, "202")
    db_session.add_all([collaborator_account, owner_account])
    _private, p256dh, auth = _browser_keys()
    db_session.add(
        PushSubscription(
            user_id=collaborator.id, workspace_id=workspace.id, endpoint=ENDPOINT, p256dh=p256dh, auth=auth
        )
    )
    goal = DailyViewsGoal(
        workspace_id=workspace.id, user_id=collaborator.id, target_views=1000, timezone="America/Manaus"
    )
    db_session.add(goal)
    await db_session.commit()

    measured_accounts: list[str] = []
    views_by_account = {"178400000101": 1200, "178400000202": 99999}

    async def fake_views(instagram_user_id, _token, since, until):
        measured_accounts.append(instagram_user_id)
        assert since < until
        return views_by_account[instagram_user_id]

    sent: list[dict] = []

    async def fake_send(_client, **kwargs):
        sent.append(kwargs["payload"])
        return PushResult(ok=True, gone=False, status_code=201)

    monkeypatch.setattr(goals_module, "fetch_instagram_views", fake_views)
    monkeypatch.setattr(goals_module, "send_web_push", fake_send)

    # 02:30 UTC on Oct 15 is still Oct 14 in Manaus (UTC-4).
    now = datetime(2026, 10, 15, 2, 30, tzinfo=timezone.utc)
    assert await goals_module.run_daily_views_goal_tick(db_session, now) == 1
    assert await goals_module.run_daily_views_goal_tick(db_session, now + timedelta(minutes=15)) == 0
    # Collaborators are measured only on the accounts they connected.
    assert set(measured_accounts) == {"178400000101"}
    assert len(sent) == 1 and "1.200" in sent[0]["body"]
    marker = await db_session.scalar(select(DailyViewsGoalNotification))
    assert marker.local_date == date(2026, 10, 14)

    # Raising the target the same day is a new goal: notified again once reached.
    goal.target_views = 1100
    await db_session.commit()
    assert await goals_module.run_daily_views_goal_tick(db_session, now + timedelta(minutes=30)) == 1
    # Next local day starts a new cycle.
    views_by_account["178400000101"] = 50
    next_day = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)
    assert await goals_module.run_daily_views_goal_tick(db_session, next_day) == 0
    refreshed = await db_session.get(DailyViewsGoal, goal.id)
    assert refreshed.progress_views == 50
    assert refreshed.progress_date == date(2026, 10, 15)


@pytest.mark.anyio
async def test_goal_tick_retries_when_push_delivery_fails_transiently(
    db_session: AsyncSession, owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_user, workspace = owner
    db_session.add(_account(workspace.id, owner_user.id, "303"))
    _private, p256dh, auth = _browser_keys()
    db_session.add(
        PushSubscription(
            user_id=owner_user.id, workspace_id=workspace.id, endpoint=ENDPOINT, p256dh=p256dh, auth=auth
        )
    )
    db_session.add(DailyViewsGoal(workspace_id=workspace.id, user_id=owner_user.id, target_views=10))
    await db_session.commit()

    async def fake_views(*_args):
        return 20

    outcomes = [PushResult(ok=False, gone=False, status_code=503), PushResult(ok=True, gone=False, status_code=201)]

    async def fake_send(_client, **_kwargs):
        return outcomes.pop(0)

    monkeypatch.setattr(goals_module, "fetch_instagram_views", fake_views)
    monkeypatch.setattr(goals_module, "send_web_push", fake_send)
    now = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)
    assert await goals_module.run_daily_views_goal_tick(db_session, now) == 0
    assert await db_session.scalar(select(func.count(DailyViewsGoalNotification.id))) == 0
    assert await goals_module.run_daily_views_goal_tick(db_session, now + timedelta(minutes=15)) == 1
    assert await db_session.scalar(select(func.count(DailyViewsGoalNotification.id))) == 1
