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
from app.main import _OAuthCallbackAccessLogFilter
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

    assert _OAuthCallbackAccessLogFilter().filter(record)
    assert "one-time-code" not in record.getMessage()
    assert "private-state" not in record.getMessage()
    assert "/api/instagram/callback" in record.getMessage()


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
    assert "private-access-token" not in response.text
    assert "encrypted_access_token" not in response.text


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
async def test_collaborator_can_view_but_cannot_manage_instagram_accounts(
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
    assert connect.status_code == 403


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)

    async def fake_meta_info(_app_id: str, _app_secret: str):
        return "Meta app name", "Business", "https://www.facebook.com/apps/123456789"

    monkeypatch.setattr(instagram_router, "fetch_meta_app_info", fake_meta_info)
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
    assert app["meta_app_name"] == "Meta app name"
    assert app["category"] == "Business"
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
async def test_collaborator_cannot_read_or_change_workspace_meta_app(
    client: AsyncClient,
    collaborator,
) -> None:
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

    assert read.status_code == 403
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
    monkeypatch: pytest.MonkeyPatch,
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

    async def fake_meta_info(_app_id: str, app_secret: str):
        assert app_secret == "new-secret"
        return "Updated Meta name", "Business", "https://example.com/app"

    monkeypatch.setattr(instagram_router, "fetch_meta_app_info", fake_meta_info)
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    response = await client.patch(
        f"/api/instagram/apps/{app.id}",
        headers={"X-CSRF-Token": token},
        json={"display_name": "After", "app_secret": "new-secret"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "After"
    assert response.json()["meta_app_name"] == "Updated Meta name"
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
            encrypted_app_secret=encrypt_value("other-app-secret"),
            is_selected=False,
            revision=uuid.uuid4(),
        )
    )
    await db_session.commit()

    async def fake_exchange(
        _code: str,
        _redirect_uri: str,
        app_id: str,
        app_secret: str,
    ):
        assert app_id == "123456"
        assert app_secret == "test-app-secret"
        return (
            "17840000000000000",
            "flashpost_demo",
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
    assert account.encrypted_access_token != "private-access-token"
    assert decrypt_value(account.encrypted_access_token) == "private-access-token"


def test_instagram_authorization_url_requests_only_basic_access() -> None:
    authorization_url = oauth.build_authorization_url(
        "123456",
        "https://flashpost.example/api/instagram/callback",
        "state-value",
    )
    parameters = parse_qs(urlparse(authorization_url).query)

    assert urlparse(authorization_url).netloc == "www.instagram.com"
    assert parameters["scope"] == ["instagram_business_basic"]
    assert parameters["state"] == ["state-value"]
    assert parameters["enable_fb_login"] == ["false"]


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
                            "permissions": "instagram_business_basic",
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
            assert params["fields"] == "user_id,username"
            assert params["access_token"] == "long-token"
            return FakeResponse(
                {"data": [{"user_id": "17840000000000000", "username": "flashpost_demo"}]}
            )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", FakeClient)
    user_id, username, token, expires_at = await oauth.exchange_instagram_authorization_code(
        "one-time-code",
        "https://flashpost.example/api/instagram/callback",
        "123456",
        "test-app-secret",
    )

    assert user_id == "17840000000000000"
    assert username == "flashpost_demo"
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
