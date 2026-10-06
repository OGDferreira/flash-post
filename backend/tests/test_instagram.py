from datetime import datetime, timedelta, timezone
import logging
import os
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import decrypt_value, encrypt_value
from app.main import _SensitiveAccessLogFilter
from app.instagram import oauth
from app.instagram import router as instagram_router
from app.instagram.oauth import InstagramOAuthError
from app.models import InstagramAccount, InstagramAppCredential, Workspace


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


def test_oauth_callback_access_logs_redact_code_and_state() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1",
            "GET",
            "/api/instagram/callback?code=one-time-code&state=private-state",
            "1.1",
            303,
        ),
        None,
    )

    assert _SensitiveAccessLogFilter().filter(record)
    assert "one-time-code" not in record.getMessage()
    assert "private-state" not in record.getMessage()
    assert "/api/instagram/callback" in record.getMessage()


def test_sharkbot_webhook_access_logs_redact_the_workspace_token() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1",
            "POST",
            "/api/sharkbot/webhook/secret-workspace-token",
            "1.1",
            200,
        ),
        None,
    )

    assert _SensitiveAccessLogFilter().filter(record)
    assert "secret-workspace-token" not in record.getMessage()
    assert "/api/sharkbot/webhook/[redacted]" in record.getMessage()


@pytest.mark.anyio
async def test_instagram_accounts_are_workspace_scoped_and_tokens_are_not_returned(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    expires_at = datetime.now(timezone.utc) + timedelta(days=50)
    db_session.add(
        InstagramAccount(
            workspace_id=workspace.id,
            instagram_user_id="17840000000000000",
            username="flashpost_demo",
            encrypted_access_token=encrypt_value("private-access-token"),
            token_expires_at=expires_at,
        )
    )
    await db_session.commit()

    await _login(client, "owner@example.com", "correct horse battery staple")
    response = await client.get("/api/instagram/accounts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_manage"] is True
    assert [account["username"] for account in payload["accounts"]] == ["flashpost_demo"]
    assert payload["accounts"][0]["connected_at"]
    assert payload["accounts"][0]["error_at"] is None
    assert "private-access-token" not in response.text
    assert "encrypted_access_token" not in response.text


@pytest.mark.anyio
async def test_errored_account_response_includes_error_timestamp(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    connected_at = datetime.now(timezone.utc) - timedelta(days=2, hours=3)
    error_at = datetime.now(timezone.utc) - timedelta(days=1, hours=1)
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000000002",
        username="errored_connection",
        connected_at=connected_at,
        updated_at=error_at,
        status="error",
        token_expires_at=error_at + timedelta(days=30),
    )
    db_session.add(account)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    response = await client.get("/api/instagram/accounts")

    assert response.status_code == 200, response.text
    result = response.json()["accounts"][0]
    assert result["status"] == "error"
    assert datetime.fromisoformat(result["connected_at"]) == connected_at
    assert datetime.fromisoformat(result["error_at"]) == error_at


@pytest.mark.anyio
async def test_disconnected_account_remains_visible_without_its_token(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    db_session.add(
        InstagramAccount(
            workspace_id=workspace.id,
            instagram_user_id="17840000000000001",
            username="previously_connected",
            encrypted_access_token=None,
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=10),
            status="disconnected",
        )
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    response = await client.get("/api/instagram/accounts")

    assert response.status_code == 200
    assert response.json()["accounts"][0]["username"] == "previously_connected"
    assert response.json()["accounts"][0]["status"] == "disconnected"
    assert "encrypted_access_token" not in response.text
    assert "private-access-token" not in response.text


@pytest.mark.anyio
async def test_collaborator_can_start_connect_but_cannot_manage_meta_apps(
    client: AsyncClient,
    collaborator,
) -> None:
    await _login(client, "collaborator@example.com", "collaborator password")

    response = await client.get("/api/instagram/accounts")
    token = await _csrf(client)
    connect = await client.post(
        "/api/instagram/connect",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 200
    assert response.json()["can_manage"] is False
    assert response.json()["can_connect"] is True
    assert connect.status_code == 503
    assert "Instagram App ID and App Secret" in connect.json()["detail"]


@pytest.mark.anyio
async def test_instagram_connect_requires_app_configuration(
    client: AsyncClient,
    owner,
) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.post(
        "/api/instagram/connect",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 503
    assert "must be configured" in response.json()["detail"]


@pytest.mark.anyio
async def test_owner_can_add_and_read_meta_app_without_secret(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    saved = await client.post(
        "/api/instagram/apps",
        headers={"X-CSRF-Token": token},
        json={
            "display_name": "My publishing app",
            "app_id": "123456789",
            "app_secret": "private-meta-secret",
        },
    )

    assert saved.status_code == 201
    assert "private-meta-secret" not in saved.text
    app = saved.json()["app"]
    assert app["display_name"] == "My publishing app"
    assert app["meta_app_name"] == "My publishing app"
    assert app["credential_kind"] == "instagram_business_login"
    assert app["category"] is None
    assert app["is_selected"] is True

    stored = await db_session.get(InstagramAppCredential, uuid.UUID(app["id"]))
    assert stored is not None
    assert stored.encrypted_app_secret != "private-meta-secret"
    assert decrypt_value(stored.encrypted_app_secret) == "private-meta-secret"

    apps = await client.get("/api/instagram/apps")
    assert apps.status_code == 200
    assert apps.json()["selected_app_id"] == app["id"]
    assert apps.json()["apps"][0]["app_id"] == "123456789"
    assert "encrypted_app_secret" not in apps.text
    assert "private-meta-secret" not in apps.text


@pytest.mark.anyio
async def test_collaborator_can_read_but_cannot_manage_workspace_meta_apps(
    client: AsyncClient,
    db_session: AsyncSession,
    collaborator,
    owner,
) -> None:
    _owner_user, workspace = owner
    db_session.add(
        InstagramAppCredential(
            workspace_id=workspace.id,
            display_name="Workspace app",
            meta_app_name="Meta workspace app",
            app_id="123456789",
            encrypted_app_secret=encrypt_value("private-meta-secret"),
            is_selected=True,
        )
    )
    await db_session.commit()
    await _login(client, "collaborator@example.com", "collaborator password")
    token = await _csrf(client)

    read = await client.get("/api/instagram/apps")
    write = await client.post(
        "/api/instagram/apps",
        headers={"X-CSRF-Token": token},
        json={
            "display_name": "My app",
            "app_id": "123456789",
            "app_secret": "private-meta-secret",
        },
    )

    assert read.status_code == 200
    assert read.json()["can_manage"] is False
    assert read.json()["apps"][0]["app_id"] == "123456789"
    assert "private-meta-secret" not in read.text
    assert write.status_code == 403


@pytest.mark.anyio
async def test_meta_app_cannot_be_removed_while_accounts_are_connected(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    db_session.add(
        InstagramAppCredential(
            workspace_id=workspace.id,
            display_name="My app",
            meta_app_name="Meta app",
            app_id="123456789",
            category=None,
            app_link=None,
            encrypted_app_secret=encrypt_value("private-meta-secret"),
            is_selected=True,
            revision=uuid.uuid4(),
        )
    )
    db_session.add(
        InstagramAccount(
            workspace_id=workspace.id,
            instagram_user_id="17840000000000000",
            username="flashpost_demo",
            encrypted_access_token=encrypt_value("private-access-token"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
        )
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    app = await db_session.scalar(
        select(InstagramAppCredential).where(
            InstagramAppCredential.workspace_id == workspace.id
        )
    )
    assert app is not None
    linked_account = await db_session.scalar(
        select(InstagramAccount).where(
            InstagramAccount.workspace_id == workspace.id
        )
    )
    assert linked_account is not None
    linked_account.app_credential_id = app.id
    await db_session.commit()
    response = await client.delete(
        f"/api/instagram/apps/{app.id}",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 409
    assert "connected with this app" in response.json()["detail"]


@pytest.mark.anyio
async def test_owner_can_disconnect_only_an_account_in_their_workspace(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000000000",
        username="flashpost_demo",
        encrypted_access_token=encrypt_value("private-access-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
    )
    db_session.add(account)
    await db_session.commit()

    async def fake_revoke(_access_token: str) -> bool:
        return True

    monkeypatch.setattr(instagram_router, "revoke_instagram_permissions", fake_revoke)
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    response = await client.delete(
        f"/api/instagram/accounts/{account.id}",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 200
    assert response.json() == {"meta_revoked": True}
    await db_session.refresh(account)
    assert account.status == "disconnected"
    assert account.encrypted_access_token is None


@pytest.mark.anyio
async def test_owner_can_load_recent_media_for_selected_instagram_account(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000000789",
        username="feed_profile",
        encrypted_access_token=encrypt_value("feed-access-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
        follower_count=42,
        media_count=7,
    )
    db_session.add(account)
    await db_session.commit()
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def __init__(self, payload: object):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self.payload

    media_payload = {
                "data": [
                    {
                        "id": "media-1",
                        "media_type": "VIDEO",
                        "media_url": "https://cdn.instagram.com/reel.mp4",
                        "thumbnail_url": "https://cdn.instagram.com/reel.jpg",
                        "permalink": "https://www.instagram.com/p/example/",
                        "timestamp": "2026-10-03T12:30:00+0000",
                        "caption": "A recent Reel",
                        "like_count": 12,
                        "comments_count": 3,
                    }
                ]
            }
    profile_payload = {
        "user_id": "17840000000000789",
        "followers_count": 420,
        "follows_count": 180,
        "media_count": 70,
    }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str, *, params: dict[str, str]):
            calls.append((url, params))
            if url.endswith("/me"):
                return FakeResponse(profile_payload)
            return FakeResponse(media_payload)

    monkeypatch.setattr(instagram_router.httpx, "AsyncClient", FakeClient)
    await _login(client, "owner@example.com", "correct horse battery staple")

    response = await client.get(f"/api/instagram/accounts/{account.id}/feed")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["username"] == "feed_profile"
    assert result["followers_count"] == 420
    assert result["media_count"] == 70
    assert result["follows_count"] == 180
    assert result["media"][0]["id"] == "media-1"
    assert result["media"][0]["like_count"] == 12
    assert calls[0][0] == "https://graph.instagram.com/v25.0/me"
    assert calls[0][1]["fields"] == (
        "user_id,followers_count,follows_count,media_count"
    )
    assert calls[0][1]["access_token"] == "feed-access-token"
    assert calls[1][0].endswith("/17840000000000789/media")
    await db_session.refresh(account)
    assert account.follower_count == 420
    assert account.media_count == 70
    assert "feed-access-token" not in response.text


@pytest.mark.anyio
async def test_owner_can_save_highlights_flag_on_account(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000000890",
        username="highlights_profile",
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
    )
    db_session.add(account)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.patch(
        f"/api/instagram/accounts/{account.id}/highlights",
        headers={"X-CSRF-Token": token},
        json={"has_highlights": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["has_highlights"] is True
    await db_session.refresh(account)
    assert account.has_highlights is True


@pytest.mark.anyio
async def test_owner_can_create_color_folder_and_assign_accounts(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000000123",
        username="folder_test_account",
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
    )
    db_session.add(account)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    created = await client.post(
        "/api/instagram/folders",
        headers={"X-CSRF-Token": token},
        json={"name": "Humor", "color": "#ff3399"},
    )
    assert created.status_code == 201, created.text
    folder_id = created.json()["id"]
    assert created.json()["color"] == "#ff3399"

    assigned = await client.put(
        f"/api/instagram/folders/{folder_id}/accounts",
        headers={"X-CSRF-Token": token},
        json={"account_ids": [str(account.id)]},
    )
    assert assigned.status_code == 200, assigned.text
    assert [item["username"] for item in assigned.json()["accounts"]] == [
        "folder_test_account"
    ]
    assert assigned.json()["accounts"][0]["connected_at"]
    assert assigned.json()["accounts"][0]["error_at"] is None

    listed = await client.get("/api/instagram/folders")
    assert listed.status_code == 200
    assert listed.json()["accounts"][0]["profile_folder_id"] == folder_id
    assert listed.json()["folders"][0]["accounts"][0]["connected_at"]
    assert listed.json()["folders"][0]["color"] == "#ff3399"

    deleted = await client.delete(
        f"/api/instagram/folders/{folder_id}",
        headers={"X-CSRF-Token": token},
    )
    assert deleted.status_code == 204
    await db_session.refresh(account)
    assert account.profile_folder_id is None


@pytest.mark.anyio
async def test_owner_can_remove_an_errored_account(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000000456",
        username="errored_account",
        encrypted_access_token=encrypt_value("private-access-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
        status="error",
    )
    db_session.add(account)
    await db_session.commit()

    async def fake_revoke(_access_token: str) -> bool:
        return True

    monkeypatch.setattr(instagram_router, "revoke_instagram_permissions", fake_revoke)
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    response = await client.delete(
        f"/api/instagram/accounts/{account.id}/remove",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 200
    assert response.json() == {"meta_revoked": True}
    assert await db_session.get(InstagramAccount, account.id) is None


@pytest.mark.anyio
async def test_account_is_removed_locally_when_meta_revocation_cannot_be_confirmed(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, workspace = owner
    account = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000000000",
        username="flashpost_demo",
        encrypted_access_token=encrypt_value("private-access-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
    )
    db_session.add(account)
    await db_session.commit()

    async def failed_revoke(_access_token: str) -> bool:
        return False

    monkeypatch.setattr(instagram_router, "revoke_instagram_permissions", failed_revoke)
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    response = await client.delete(
        f"/api/instagram/accounts/{account.id}",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 200
    assert response.json() == {"meta_revoked": False}
    await db_session.refresh(account)
    assert account.status == "disconnected"
    assert account.encrypted_access_token is None


@pytest.mark.anyio
async def test_owner_cannot_disconnect_account_from_another_workspace(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    user, _workspace = owner
    other_workspace = Workspace(
        name="Other workspace",
        slug="other-workspace",
        owner_id=user.id,
        status="ACTIVE",
    )
    db_session.add(other_workspace)
    await db_session.flush()
    account = InstagramAccount(
        workspace_id=other_workspace.id,
        instagram_user_id="17840000000000000",
        username="private_account",
        encrypted_access_token=encrypt_value("private-access-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=50),
    )
    db_session.add(account)
    await db_session.commit()

    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    response = await client.delete(
        f"/api/instagram/accounts/{account.id}",
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 404
    assert await db_session.get(InstagramAccount, account.id) is not None


@pytest.mark.anyio
async def test_owner_can_select_one_of_multiple_meta_apps(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    first = InstagramAppCredential(
        workspace_id=workspace.id,
        display_name="First",
        meta_app_name="First Meta app",
        app_id="111111",
        encrypted_app_secret=encrypt_value("first-secret"),
        is_selected=True,
        revision=uuid.uuid4(),
    )
    second = InstagramAppCredential(
        workspace_id=workspace.id,
        display_name="Second",
        meta_app_name="Second Meta app",
        app_id="222222",
        encrypted_app_secret=encrypt_value("second-secret"),
        is_selected=False,
        revision=uuid.uuid4(),
    )
    db_session.add_all([first, second])
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    response = await client.put(
        f"/api/instagram/apps/{second.id}/select",
        headers={"X-CSRF-Token": token},
    )
    apps = await client.get("/api/instagram/apps")

    assert response.status_code == 200
    assert apps.status_code == 200
    assert apps.json()["selected_app_id"] == str(second.id)
    assert {app["id"]: app["is_selected"] for app in apps.json()["apps"]} == {
        str(first.id): False,
        str(second.id): True,
    }


@pytest.mark.anyio
async def test_owner_can_rename_and_rotate_meta_app_secret(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, workspace = owner
    app = InstagramAppCredential(
        workspace_id=workspace.id,
        display_name="Before",
        meta_app_name="Old Meta name",
        app_id="123456789",
        encrypted_app_secret=encrypt_value("old-secret"),
        is_selected=True,
        revision=uuid.uuid4(),
    )
    db_session.add(app)
    await db_session.commit()
    old_revision = app.revision

    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    response = await client.patch(
        f"/api/instagram/apps/{app.id}",
        headers={"X-CSRF-Token": token},
        json={"display_name": "After", "app_secret": "new-secret"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "After"
    assert response.json()["meta_app_name"] == "Old Meta name"
    assert "new-secret" not in response.text
    await db_session.refresh(app)
    assert decrypt_value(app.encrypted_app_secret) == "new-secret"
    assert app.revision != old_revision


@pytest.mark.anyio
async def test_oauth_callback_persists_encrypted_token_and_redirects(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, workspace = owner
    settings = Settings(
        public_base_url="http://testserver",
        master_encryption_key=SecretStr(os.environ["MASTER_ENCRYPTION_KEY"]),
        _env_file=None,
    )
    db_session.add(
        InstagramAppCredential(
            workspace_id=workspace.id,
            display_name="Selected app",
            meta_app_name="Meta selected app",
            app_id="123456",
            credential_kind="legacy",
            category="Business",
            app_link="https://example.com/app",
            encrypted_app_secret=encrypt_value("test-app-secret"),
            is_selected=True,
            revision=uuid.uuid4(),
        )
    )
    db_session.add(
        InstagramAppCredential(
            workspace_id=workspace.id,
            display_name="Not selected",
            meta_app_name="Other Meta app",
            app_id="654321",
            credential_kind="instagram_business_login",
            encrypted_app_secret=encrypt_value("other-app-secret"),
            is_selected=False,
            revision=uuid.uuid4(),
        )
    )
    await db_session.commit()

    async def fake_exchange(
        code: str,
        _redirect_uri: str,
        app_id: str,
        app_secret: str,
    ):
        expected_credentials = (
            ("654321", "other-app-secret")
            if code == "second-one-time-code"
            else ("123456", "test-app-secret")
        )
        assert (app_id, app_secret) == expected_credentials
        return (
            "17840000000000000",
            "flashpost_demo",
            "https://scontent.cdninstagram.com/profile.jpg",
            128,
            42,
            "private-access-token",
            datetime.now(timezone.utc) + timedelta(days=50),
        )

    monkeypatch.setattr(instagram_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        instagram_router,
        "exchange_instagram_authorization_code",
        fake_exchange,
    )
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    start = await client.post(
        "/api/instagram/connect",
        headers={"X-CSRF-Token": token},
    )
    assert start.status_code == 200
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]

    callback = await client.get(
        "/api/instagram/callback",
        params={"code": "one-time-code", "state": state},
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == (
        "http://testserver/feature/accounts?instagram=connected"
    )
    account = await db_session.scalar(
        select(InstagramAccount).where(
            InstagramAccount.instagram_user_id == "17840000000000000"
        )
    )
    assert account is not None
    assert account.app_credential_id is not None
    assert account.connected_by_user_id == _user.id
    assert account.first_connected_at is not None
    first_connected_at = account.first_connected_at

    second_token = await _csrf(client)
    second_app = await db_session.scalar(
        select(InstagramAppCredential).where(
            InstagramAppCredential.workspace_id == workspace.id,
            InstagramAppCredential.app_id == "654321",
        )
    )
    assert second_app is not None
    second_start = await client.post(
        f"/api/instagram/connect?app_id={second_app.id}",
        headers={"X-CSRF-Token": second_token},
    )
    assert second_start.status_code == 200
    assert parse_qs(urlparse(second_start.json()["authorization_url"]).query)[
        "client_id"
    ] == ["654321"]
    second_state = parse_qs(
        urlparse(second_start.json()["authorization_url"]).query
    )["state"][0]
    second_callback = await client.get(
        "/api/instagram/callback",
        params={"code": "second-one-time-code", "state": second_state},
    )
    assert second_callback.status_code == 303
    await db_session.refresh(account)
    assert account.connected_by_user_id == _user.id
    assert account.first_connected_at == first_connected_at
    assert account.profile_picture_url == "https://scontent.cdninstagram.com/profile.jpg"
    assert account.follower_count == 128
    assert account.media_count == 42
    assert account.encrypted_access_token != "private-access-token"
    assert decrypt_value(account.encrypted_access_token) == "private-access-token"
    assert account.app_credential_id == second_app.id


def test_instagram_authorization_url_requests_publishing_access() -> None:
    authorization_url = oauth.build_authorization_url(
        "123456",
        "https://flashpost.example/api/instagram/callback",
        "state-value",
    )
    parameters = parse_qs(urlparse(authorization_url).query)

    assert urlparse(authorization_url).netloc == "www.instagram.com"
    assert parameters["scope"] == [
        "instagram_business_basic,instagram_business_content_publish,"
        "instagram_business_manage_insights"
    ]
    assert parameters["state"] == ["state-value"]
    assert parameters["enable_fb_login"] == ["false"]


@pytest.mark.parametrize(
    ("error_code", "error_message", "permission_is_explicit"),
    [
        (
            10,
            "Missing permission instagram_business_manage_insights",
            True,
        ),
        (10, "Unsupported request for this metric", False),
        (200, "Unsupported request for this metric", False),
    ],
)
@pytest.mark.anyio
async def test_insights_only_reports_permission_missing_when_meta_identifies_it(
    monkeypatch: pytest.MonkeyPatch,
    error_code: int,
    error_message: str,
    permission_is_explicit: bool,
) -> None:
    class FakeResponse:
        is_error = True

        def json(self) -> object:
            return {"error": {"code": error_code, "message": error_message}}

        def raise_for_status(self) -> None:
            request = oauth.httpx.Request("GET", "https://graph.instagram.com/insights")
            response = oauth.httpx.Response(400, request=request)
            raise oauth.httpx.HTTPStatusError(
                "Meta Insights request failed",
                request=request,
                response=response,
            )

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)
    expected_error = (
        oauth.InstagramInsightsPermissionError
        if permission_is_explicit
        else oauth.httpx.HTTPStatusError
    )
    with pytest.raises(expected_error):
        await oauth.fetch_instagram_views(
            "17840000000000000",
            "private-test-token",
            datetime.now(timezone.utc) - timedelta(days=1),
            datetime.now(timezone.utc),
        )


@pytest.mark.anyio
async def test_instagram_profile_metrics_are_fetched_from_me_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        is_error = False

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return {
                "user_id": "17840000000000000",
                "followers_count": 2468,
                "follows_count": 805,
                "media_count": 137,
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str, *, params: dict[str, str]):
            calls.append((url, params))
            return FakeResponse()

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)

    metrics = await oauth.fetch_instagram_profile_metrics(
        "private-test-token",
    )

    assert metrics == (2468, 805, 137)
    assert calls == [
        (
            "https://graph.instagram.com/v25.0/me",
            {
                "fields": "user_id,followers_count,follows_count,media_count",
                "access_token": "private-test-token",
            },
        )
    ]


@pytest.mark.anyio
async def test_instagram_views_use_supported_total_metric_and_timestamp_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    class FakeResponse:
        def __init__(self, payload: object):
            self.payload = payload
            self.is_error = False
            self.request = oauth.httpx.Request("GET", "https://graph.instagram.com/insights")

        def json(self) -> object:
            return self.payload

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url: str, *, params: dict[str, str]):
            calls.append(params)
            return FakeResponse(
                {
                    "data": [
                        {
                            "name": "views",
                            "total_value": {"value": 425},
                        }
                    ]
                }
            )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)

    views = await oauth.fetch_instagram_views(
        "17840000000000000",
        "private-test-token",
        datetime(2026, 10, 1, 3, tzinfo=timezone.utc),
        datetime(2026, 10, 3, 3, tzinfo=timezone.utc),
    )

    assert views == 425
    assert len(calls) == 1
    assert calls[0]["metric"] == "views"
    assert calls[0]["period"] == "day"
    assert calls[0]["metric_type"] == "total_value"
    assert calls[0]["since"] == str(
        int(datetime(2026, 10, 1, 3, tzinfo=timezone.utc).timestamp())
    )
    assert calls[0]["until"] == str(
        int(datetime(2026, 10, 3, 3, tzinfo=timezone.utc).timestamp()) - 1
    )


@pytest.mark.anyio
async def test_instagram_media_views_sum_video_insights_in_requested_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_pages = [
        {
            "data": [
                {
                    "id": "video-a",
                    "media_type": "VIDEO",
                    "timestamp": "2026-10-03T12:00:00+00:00",
                },
                {
                    "id": "image-a",
                    "media_type": "IMAGE",
                    "timestamp": "2026-10-02T10:00:00+00:00",
                },
                {
                    "id": "video-b",
                    "media_type": "VIDEO",
                    "timestamp": "2026-10-02T08:00:00+00:00",
                },
            ],
            "paging": {"cursors": {"after": "page-two"}},
        },
        {
            "data": [
                {
                    "id": "video-c",
                    "media_type": "VIDEO",
                    "timestamp": "2026-10-01T00:00:00+00:00",
                },
                {
                    "id": "video-old",
                    "media_type": "VIDEO",
                    "timestamp": "2026-09-30T23:59:59+00:00",
                },
            ],
            "paging": {"cursors": {"after": "page-three"}},
        },
    ]
    media_calls: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def __init__(self, payload: object):
            self.payload = payload
            self.is_error = False
            self.request = oauth.httpx.Request(
                "GET", "https://graph.instagram.com/test"
            )

        def json(self) -> object:
            return self.payload

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str, *, params: dict[str, str]):
            if url.endswith("/media"):
                return FakeResponse(media_pages.pop(0))
            media_id = url.rsplit("/", 2)[-2]
            media_calls.append((media_id, params))
            count = {"video-a": 100, "video-b": 200, "video-c": 300}[media_id]
            return FakeResponse(
                {"data": [{"name": "views", "values": [{"value": count}]}]}
            )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)

    result = await oauth.fetch_instagram_media_views(
        "17840000000000000",
        "private-test-token",
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 4, tzinfo=timezone.utc),
    )

    assert result == (600, 3, [])
    assert len(media_calls) == 3
    assert all(params["metric"] == "views" for _, params in media_calls)
    assert all("period" not in params for _, params in media_calls)


@pytest.mark.anyio
async def test_instagram_account_insights_fetch_supported_metrics_for_local_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    class FakeResponse:
        def __init__(self, metric_name: str):
            self.metric_name = metric_name

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return {
                "data": [
                    {
                        "name": self.metric_name,
                        "total_value": {"value": 17},
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url: str, *, params: dict[str, str]):
            calls.append(params)
            return FakeResponse(params["metric"])

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)

    metrics, errors = await oauth.fetch_instagram_account_insights(
        "17840000000000000",
        "private-test-token",
        datetime(2026, 10, 1, 3, tzinfo=timezone.utc),
        datetime(2026, 10, 3, 3, tzinfo=timezone.utc),
    )

    assert metrics["views"] is None
    assert metrics["reach"] == 17
    assert metrics["profile_links_taps"] == 17
    assert metrics["impressions"] is None
    assert metrics["profile_views"] is None
    assert errors == {
        "impressions": "A Meta descontinuou esta métrica; use Visualizações.",
        "profile_views": "A Meta não oferece esta métrica neste endpoint.",
        "website_clicks": "A Meta não oferece esta métrica neste endpoint.",
    }
    assert len(calls) == 10
    assert all(call["metric"] != "views" for call in calls)
    assert all(call["period"] == "day" for call in calls)
    assert all(call["metric_type"] == "total_value" for call in calls)
    assert all(
        call["since"]
        == str(int(datetime(2026, 10, 1, 3, tzinfo=timezone.utc).timestamp()))
        for call in calls
    )
    assert all(
        call["until"]
        == str(int(datetime(2026, 10, 3, 3, tzinfo=timezone.utc).timestamp()) - 1)
        for call in calls
    )


@pytest.mark.anyio
async def test_instagram_oauth_exchanges_code_for_long_lived_token_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __init__(self, payload: object):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self.payload

    class FakeClient:
        def __init__(self, **_kwargs):
            self.get_count = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, *, data: dict[str, str]):
            assert url == oauth.INSTAGRAM_TOKEN_ENDPOINT
            assert data["grant_type"] == "authorization_code"
            assert data["code"] == "one-time-code"
            return FakeResponse(
                {
                    "data": [
                        {
                            "access_token": "short-token",
                        }
                    ]
                }
            )

        async def get(self, url: str, *, params: dict[str, str]):
            self.get_count += 1
            if url.endswith("/access_token"):
                assert params["grant_type"] == "ig_exchange_token"
                assert params["access_token"] == "short-token"
                return FakeResponse(
                    {"access_token": "long-token", "expires_in": 5183944}
                )
            assert url.endswith("/me")
            assert params["fields"] == (
                "user_id,username,profile_picture_url,followers_count,media_count"
            )
            assert params["access_token"] == "long-token"
            return FakeResponse(
                {
                    "data": [
                        {
                            "user_id": "17840000000000000",
                            "username": "flashpost_demo",
                            "profile_picture_url": "https://scontent.cdninstagram.com/profile.jpg",
                            "followers_count": 128,
                            "media_count": 42,
                        }
                    ]
                }
            )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)
    user_id, username, profile_picture_url, followers_count, media_count, token, expires_at = (
        await oauth.exchange_instagram_authorization_code(
            "one-time-code",
            "https://flashpost.example/api/instagram/callback",
            "123456",
            "test-app-secret",
        )
    )

    assert user_id == "17840000000000000"
    assert username == "flashpost_demo"
    assert profile_picture_url == "https://scontent.cdninstagram.com/profile.jpg"
    assert followers_count == 128
    assert media_count == 42
    assert token == "long-token"
    assert expires_at > datetime.now(timezone.utc)


@pytest.mark.anyio
async def test_instagram_oauth_rejects_missing_basic_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return {"data": [{"access_token": "short-token", "permissions": ""}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)
    with pytest.raises(InstagramOAuthError, match="permission"):
        await oauth.exchange_instagram_authorization_code(
            "one-time-code",
            "https://flashpost.example/api/instagram/callback",
            "123456",
            "test-app-secret",
        )


@pytest.mark.anyio
async def test_instagram_long_lived_token_refresh_extends_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return {"access_token": "refreshed-token", "expires_in": 5183944}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str, *, params: dict[str, str]):
            assert url == oauth.INSTAGRAM_TOKEN_REFRESH_ENDPOINT
            assert params == {
                "grant_type": "ig_refresh_token",
                "access_token": "valid-long-lived-token",
            }
            return FakeResponse()

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)
    refreshed_token, expires_at = await oauth.refresh_instagram_long_lived_token(
        "valid-long-lived-token"
    )

    assert refreshed_token == "refreshed-token"
    assert expires_at > datetime.now(timezone.utc) + timedelta(days=59)


@pytest.mark.anyio
async def test_instagram_permission_revocation_uses_meta_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return {"success": True}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def delete(self, url: str, *, params: dict[str, str]):
            assert url == f"{oauth.INSTAGRAM_GRAPH_ENDPOINT}/me/permissions"
            assert params == {"access_token": "private-token"}
            return FakeResponse()

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)

    assert await oauth.revoke_instagram_permissions("private-token") is True
