import uuid

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value
from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.models import User, Workspace, WorkspaceMember


async def csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def login(client: AsyncClient, email: str, password: str) -> dict:
    token = await csrf(client)
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_argon2_password_hashing() -> None:
    encoded = hash_password("long secure password")

    assert encoded.startswith("$argon2id$")
    assert verify_password("long secure password", encoded)
    assert not verify_password("incorrect", encoded)
    assert not verify_password("incorrect", None)


def test_encryption_round_trip() -> None:
    ciphertext = encrypt_value("private integration value")

    assert ciphertext != "private integration value"
    assert decrypt_value(ciphertext) == "private integration value"


def test_invalid_ciphertext_is_rejected() -> None:
    with pytest.raises(ValueError, match="could not be decrypted"):
        decrypt_value("not-valid-ciphertext")


def test_postgres_url_uses_async_driver_without_changing_async_urls() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql://db.example.test/postgres?sslmode=require"),
        _env_file=None,
    )
    async_settings = Settings(
        database_url=SecretStr("postgresql+asyncpg://db.example.test/postgres?sslmode=require"),
        _env_file=None,
    )

    assert settings.database_url_value() == "postgresql+asyncpg://db.example.test/postgres"
    assert async_settings.database_url_value() == "postgresql+asyncpg://db.example.test/postgres"


def test_production_requires_session_secret() -> None:
    settings = Settings(environment="production", session_secret=None, _env_file=None)

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        settings.validate_runtime()


@pytest.mark.anyio
async def test_health_and_readiness(client: AsyncClient) -> None:
    health = await client.get("/health")
    ready = await client.get("/readiness")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "flashpost"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "database": "ok"}


@pytest.mark.anyio
async def test_login_normalizes_email_and_auth_me_excludes_password_hash(
    client: AsyncClient, owner
) -> None:
    user, _workspace = owner

    result = await login(client, " OWNER@EXAMPLE.COM ", "correct horse battery staple")
    response = await client.get("/api/auth/me")

    assert result["user"]["id"] == str(user.id)
    assert result["user"]["role"] == "OWNER"
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"
    assert "password_hash" not in response.json()
    assert "password" not in response.json()


@pytest.mark.anyio
async def test_login_rejects_incorrect_password(client: AsyncClient, owner) -> None:
    _user, _workspace = owner
    token = await csrf(client)

    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": "owner@example.com", "password": "wrong password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Email or password is incorrect."}


@pytest.mark.anyio
async def test_login_requires_csrf_token(client: AsyncClient, owner) -> None:
    _user, _workspace = owner

    response = await client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_session_rotates_csrf_and_logout_clears_auth(client: AsyncClient, owner) -> None:
    _user, _workspace = owner
    old_csrf = await csrf(client)
    result = await login(client, "owner@example.com", "correct horse battery staple")

    assert result["csrf_token"] != old_csrf
    me = await client.get("/api/auth/me")
    assert me.status_code == 200

    logout_response = await client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": result["csrf_token"]},
    )
    assert logout_response.status_code == 200
    new_csrf = logout_response.json()["csrf_token"]
    assert new_csrf != result["csrf_token"]
    me_after_logout = await client.get("/api/auth/me")
    assert me_after_logout.status_code == 401
    signed_in_again = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": new_csrf},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert signed_in_again.status_code == 200


@pytest.mark.anyio
async def test_profile_patch_requires_valid_csrf_and_updates_profile(
    client: AsyncClient, owner
) -> None:
    _user, _workspace = owner
    auth = await login(client, "owner@example.com", "correct horse battery staple")

    denied = await client.patch(
        "/api/profile",
        json={"full_name": "Updated Name", "avatar_url": None},
    )
    updated = await client.patch(
        "/api/profile",
        headers={"X-CSRF-Token": auth["csrf_token"]},
        json={"full_name": "Updated Name", "avatar_url": "https://example.com/avatar.png"},
    )

    assert denied.status_code == 403
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Updated Name"
    assert updated.json()["avatar_url"] == "https://example.com/avatar.png"


@pytest.mark.anyio
async def test_workspace_endpoint_only_returns_current_member_workspace(
    client: AsyncClient, owner, db_session: AsyncSession
) -> None:
    user, _workspace = owner
    auth = await login(client, "owner@example.com", "correct horse battery staple")
    own_workspace = await client.get("/api/workspace")

    other_owner = User(
        email="other-owner@example.com",
        full_name="Other Owner",
        password_hash=hash_password("another long password"),
    )
    db_session.add(other_owner)
    await db_session.flush()
    other_workspace = Workspace(
        name="Other Workspace",
        slug="other-workspace",
        owner_id=other_owner.id,
    )
    db_session.add(other_workspace)
    await db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=other_workspace.id,
            user_id=other_owner.id,
            role="OWNER",
            status="ACTIVE",
        )
    )
    await db_session.commit()

    denied = await client.get(
        "/api/workspace",
        headers={"X-Workspace-ID": str(other_workspace.id)},
    )

    assert own_workspace.status_code == 200
    assert own_workspace.json()["role"] == "OWNER"
    assert own_workspace.json()["id"] != str(other_workspace.id)
    assert denied.status_code == 403
    assert str(user.id) != str(other_owner.id)
    assert auth["user"]["id"] == str(user.id)


@pytest.mark.anyio
async def test_workspace_membership_is_unique(
    db_session: AsyncSession, owner
) -> None:
    user, workspace = owner
    db_session.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="OWNER",
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.anyio
async def test_admin_endpoints_deny_owner_and_collaborator(
    client: AsyncClient, owner, collaborator
) -> None:
    await login(client, "owner@example.com", "correct horse battery staple")
    owner_response = await client.get("/api/admin/summary")

    assert owner_response.status_code == 403

    await client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": (await csrf(client))},
    )
    await login(client, "collaborator@example.com", "collaborator password")
    collaborator_response = await client.get("/api/admin/users")

    assert collaborator_response.status_code == 403
    assert collaborator.email == "collaborator@example.com"


@pytest.mark.anyio
async def test_super_admin_can_view_real_admin_metrics_and_paginated_lists(
    client: AsyncClient, super_admin, owner, collaborator
) -> None:
    await login(client, "superadmin@example.com", "super admin password")
    summary_response = await client.get("/api/admin/summary")
    users_response = await client.get("/api/admin/users?page=1&page_size=2&q=example.com")
    workspaces_response = await client.get("/api/admin/workspaces")

    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "users_total": 3,
        "workspaces_total": 1,
        "owners": 1,
        "collaborators": 1,
        "active_users": 3,
    }
    assert users_response.status_code == 200
    assert users_response.json()["total"] == 3
    assert len(users_response.json()["items"]) == 2
    assert workspaces_response.status_code == 200
    assert workspaces_response.json()["items"][0]["members_count"] == 2
    assert super_admin.platform_role == "SUPER_ADMIN"
    assert collaborator.id != owner[0].id


@pytest.mark.anyio
async def test_login_rate_limiter_limits_repeated_failures(client: AsyncClient) -> None:
    token = await csrf(client)
    response = None
    email = f"{uuid.uuid4()}@example.com"
    for _ in range(5):
        response = await client.post(
            "/api/auth/login",
            headers={"X-CSRF-Token": token},
            json={"email": email, "password": "incorrect"},
        )
    assert response is not None
    assert response.status_code == 401
    limited = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": email, "password": "incorrect"},
    )
    assert limited.status_code == 429


@pytest.mark.anyio
async def test_admin_summary_counts_real_rows(client: AsyncClient, super_admin) -> None:
    await login(client, "superadmin@example.com", "super admin password")
    response = await client.get("/api/admin/summary")

    assert response.status_code == 200
    assert response.json()["users_total"] == 1
    assert response.json()["workspaces_total"] == 0
    assert response.json()["owners"] == 0
