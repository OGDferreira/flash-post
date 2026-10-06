import uuid

import pytest
from httpx import AsyncClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value
from app.core.config import Settings
from app.core.nickname import nickname_key, normalize_nickname
from app.core.security import hash_password, verify_password
from app.models import User, Workspace, WorkspaceMember
from app.schemas.auth import RegisterRequest


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Gui Ferreira", "Gui Ferreira"),
        ("00 do Site", "00 do Site"),
        ("João Ads", "João Ads"),
        ("Guilherme 🚀", "Guilherme 🚀"),
        ("   Gui   Ferreira   ", "Gui Ferreira"),
    ],
)
def test_public_nickname_normalization(value: str, expected: str) -> None:
    assert normalize_nickname(value) == expected


@pytest.mark.parametrize("value", ["", " ", "A", "x" * 41])
def test_public_nickname_rejects_values_outside_length_bounds(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_nickname(value)


@pytest.mark.parametrize(
    ("nickname", "expected"),
    [
        ("Gui Ferreira", "Gui Ferreira"),
        ("00 do Site", "00 do Site"),
        ("João Ads", "João Ads"),
        ("Guilherme 🚀", "Guilherme 🚀"),
        ("   Gui   Ferreira   ", "Gui Ferreira"),
    ],
)
def test_registration_schema_accepts_public_display_names(
    nickname: str, expected: str
) -> None:
    payload = RegisterRequest.model_validate(
        {
            "full_name": "Display Name User",
            "email": "display@example.com",
            "nickname": nickname,
            "password": "a secure password",
            "confirm_password": "a secure password",
        }
    )

    assert payload.nickname == expected


@pytest.mark.parametrize("nickname", ["A", "x" * 41])
def test_registration_schema_rejects_public_names_outside_length_bounds(
    nickname: str,
) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "full_name": "Display Name User",
                "email": "display@example.com",
                "nickname": nickname,
                "password": "a secure password",
                "confirm_password": "a secure password",
            }
        )


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
    assert result["user"]["workspace_role"] == "OWNER"
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"
    assert response.json()["workspace_role"] == "OWNER"
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
    client: AsyncClient, owner, collaborator
) -> None:
    _user, _workspace = owner
    _collaborator = collaborator
    auth = await login(client, "owner@example.com", "correct horse battery staple")

    denied = await client.patch(
        "/api/profile",
        json={"full_name": "Updated Name", "nickname": "owner-updated", "avatar_url": None},
    )
    updated = await client.patch(
        "/api/profile",
        headers={"X-CSRF-Token": auth["csrf_token"]},
        json={
            "full_name": "Updated Name",
            "nickname": "  João   Ferreira  ",
            "avatar_url": "https://example.com/avatar.png",
        },
    )

    assert denied.status_code == 403
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Updated Name"
    assert updated.json()["nickname"] == "João Ferreira"
    assert updated.json()["avatar_url"] == "https://example.com/avatar.png"

    duplicate = await client.patch(
        "/api/profile",
        headers={"X-CSRF-Token": auth["csrf_token"]},
        json={"full_name": "Updated Name", "nickname": "colaborador", "avatar_url": None},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "This nickname is already in use."


@pytest.mark.anyio
async def test_profile_patch_keeps_existing_avatar_when_omitted(
    client: AsyncClient,
    owner,
) -> None:
    user, _workspace = owner
    user.avatar_url = "https://example.com/previous-avatar.png"
    auth = await login(client, "owner@example.com", "correct horse battery staple")

    response = await client.patch(
        "/api/profile",
        headers={"X-CSRF-Token": auth["csrf_token"]},
        json={"full_name": "Updated Name", "nickname": "Gui Ferreira"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["avatar_url"] == "https://example.com/previous-avatar.png"


@pytest.mark.anyio
async def test_profile_avatar_upload_uses_private_storage_and_signed_redirect(
    client: AsyncClient,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStorage:
        uploaded: tuple[str, bytes, str] | None = None

        async def upload(self, path: str, content: bytes, content_type: str) -> None:
            self.uploaded = (path, content, content_type)

        async def delete(self, _path: str) -> None:
            return None

        async def create_signed_url(self, _path: str) -> str:
            return "https://storage.example/signed-avatar"

    storage = FakeStorage()
    monkeypatch.setattr(
        "app.auth.router.SupabaseStorage.from_settings",
        classmethod(lambda _cls: storage),
    )
    await login(client, "owner@example.com", "correct horse battery staple")
    token = await csrf(client)

    uploaded = await client.post(
        "/api/profile/avatar",
        content=b"\xff\xd8\xffprofile-avatar",
        headers={"Content-Type": "image/jpeg", "X-CSRF-Token": token},
    )

    assert uploaded.status_code == 200, uploaded.text
    avatar_path = uploaded.json()["avatar_url"]
    stored_path = owner[0].avatar_url
    assert stored_path is not None
    assert stored_path.startswith(f"avatars/{owner[0].id}/")
    assert avatar_path.startswith("/api/profile/avatar?")
    assert storage.uploaded == (
        stored_path,
        b"\xff\xd8\xffprofile-avatar",
        "image/jpeg",
    )
    redirected = await client.get("/api/profile/avatar")
    assert redirected.status_code == 307
    assert redirected.headers["location"] == "https://storage.example/signed-avatar"


@pytest.mark.anyio
async def test_registration_creates_pending_owner_without_signing_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await csrf(client)
    response = await client.post(
        "/api/auth/register",
        headers={"X-CSRF-Token": token},
        json={
            "full_name": "Gui Operations",
            "email": " GuiOps@Example.com ",
            "nickname": "Gui Ferreira",
            "password": "a secure password",
            "confirm_password": "a secure password",
        },
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["user"]["email"] == "guiops@example.com"
    assert result["user"]["nickname"] == "Gui Ferreira"
    assert result["user"]["role"] == "OWNER"
    assert result["user"]["is_verified"] is False
    assert result["user"]["is_approved"] is False
    assert "password_hash" not in result["user"]
    assert "password" not in result["user"]
    assert result["csrf_token"] == token

    current_user = await client.get("/api/auth/me")
    workspace = await client.get("/api/workspace")
    assert current_user.status_code == 401
    assert workspace.status_code == 401
    login_response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": await csrf(client)},
        json={"email": "guiops@example.com", "password": "a secure password"},
    )
    assert login_response.status_code == 403
    assert login_response.json()["detail"] == "Sua conta aguarda aprovação do administrador."
    user = await db_session.scalar(select(User).where(User.email == "guiops@example.com"))
    assert user is not None
    assert user.platform_role == "USER"
    assert user.is_approved is False
    assert user.password_hash != "a secure password"
    assert verify_password("a secure password", user.password_hash)


@pytest.mark.anyio
async def test_super_admin_can_approve_new_owner_without_changing_existing_user_data(
    client: AsyncClient,
    owner,
    db_session: AsyncSession,
) -> None:
    owner_user, _workspace = owner
    owner_user.platform_role = "SUPER_ADMIN"
    original_hash = owner_user.password_hash
    original_nickname = owner_user.nickname
    await db_session.commit()

    register_token = await csrf(client)
    created = await client.post(
        "/api/auth/register",
        headers={"X-CSRF-Token": register_token},
        json={
            "full_name": "Waiting Owner",
            "email": "waiting@example.com",
            "nickname": "Waiting Owner",
            "password": "a secure password",
            "confirm_password": "a secure password",
        },
    )
    assert created.status_code == 201, created.text
    pending_id = created.json()["user"]["id"]

    admin_auth = await login(
        client,
        "owner@example.com",
        "correct horse battery staple",
    )
    assert admin_auth["user"]["role"] == "SUPER_ADMIN"
    assert admin_auth["user"]["workspace_role"] == "OWNER"
    approval = await client.post(
        f"/api/admin/users/{pending_id}/approve",
        headers={"X-CSRF-Token": admin_auth["csrf_token"]},
    )

    assert approval.status_code == 200, approval.text
    assert approval.json()["is_approved"] is True
    assert owner_user.platform_role == "SUPER_ADMIN"
    assert owner_user.password_hash == original_hash
    assert owner_user.nickname == original_nickname
    approved_login = await login(client, "waiting@example.com", "a secure password")
    assert approved_login["user"]["is_approved"] is True


@pytest.mark.anyio
async def test_registration_accepts_unicode_public_nickname(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await csrf(client)
    response = await client.post(
        "/api/auth/register",
        headers={"X-CSRF-Token": token},
        json={
            "full_name": "João Ads",
            "email": "joao@example.com",
            "nickname": "   João    Ads ",
            "password": "a secure password",
            "confirm_password": "a secure password",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["user"]["nickname"] == "João Ads"
    assert response.json()["user"]["nickname"] != response.json()["user"]["nickname"].lower()
    workspace = await db_session.scalar(
        select(Workspace).where(Workspace.name == "Operação de João Ads")
    )
    assert workspace is not None
    assert workspace.slug == "joao-ads"


@pytest.mark.anyio
async def test_registration_adds_suffix_when_workspace_slug_is_taken(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    async def create(nickname: str, email: str) -> dict:
        response = await client.post(
            "/api/auth/register",
            headers={"X-CSRF-Token": await csrf(client)},
            json={
                "full_name": "New Owner",
                "email": email,
                "nickname": nickname,
                "password": "a secure password",
                "confirm_password": "a secure password",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    await create("00 do Site", "first@example.com")
    await create("00-do-site", "second@example.com")
    workspaces = (
        await db_session.scalars(select(Workspace).order_by(Workspace.slug))
    ).all()

    assert [(workspace.name, workspace.slug) for workspace in workspaces] == [
        ("Operação de 00 do Site", "00-do-site"),
        ("Operação de 00-do-site", "00-do-site-2"),
    ]


@pytest.mark.anyio
async def test_registration_rejects_duplicate_email_and_nickname_case_insensitively(
    client: AsyncClient, owner
) -> None:
    _user, _workspace = owner
    token = await csrf(client)
    payload = {
        "full_name": "Another User",
        "email": "new@example.com",
        "nickname": "New User",
        "password": "a secure password",
        "confirm_password": "a secure password",
    }

    availability = await client.get(
        "/api/auth/nickname-availability",
        params={"nickname": "GUI   FERREIRA"},
    )
    duplicate_nickname = await client.post(
        "/api/auth/register",
        headers={"X-CSRF-Token": token},
        json={**payload, "nickname": "gui   ferreira"},
    )
    duplicate_email = await client.post(
        "/api/auth/register",
        headers={"X-CSRF-Token": token},
        json={**payload, "email": "OWNER@example.com"},
    )

    assert availability.status_code == 200
    assert availability.json() == {"available": False}
    assert duplicate_nickname.status_code == 409
    assert duplicate_nickname.json()["detail"] == "This nickname is already in use."
    assert duplicate_email.status_code == 409
    assert duplicate_email.json()["detail"] == "An account with this email already exists."


@pytest.mark.anyio
async def test_registration_rate_limit_blocks_repeated_attempts(
    client: AsyncClient, owner
) -> None:
    _user, _workspace = owner
    token = await csrf(client)
    payload = {
        "full_name": "New User",
        "email": "OWNER@example.com",
        "nickname": "New Owner",
        "password": "a secure password",
        "confirm_password": "a secure password",
    }

    responses = [
        await client.post(
            "/api/auth/register",
            headers={"X-CSRF-Token": token},
            json=payload,
        )
        for _ in range(6)
    ]

    assert [response.status_code for response in responses] == [
        409,
        409,
        409,
        409,
        409,
        429,
    ]


@pytest.mark.anyio
async def test_registration_validates_nickname_and_password(client: AsyncClient) -> None:
    token = await csrf(client)
    base_payload = {
        "full_name": "New User",
        "email": "new@example.com",
        "nickname": " ",
        "password": "short",
        "confirm_password": "short",
    }

    bad_nickname = await client.post(
        "/api/auth/register",
        headers={"X-CSRF-Token": token},
        json=base_payload,
    )
    bad_password = await client.post(
        "/api/auth/register",
        headers={"X-CSRF-Token": token},
        json={**base_payload, "nickname": "New User", "password": "short7!", "confirm_password": "short7!"},
    )
    mismatched_password = await client.post(
        "/api/auth/register",
        headers={"X-CSRF-Token": token},
        json={
            **base_payload,
            "nickname": "New User",
            "password": "valid password",
            "confirm_password": "different password",
        },
    )

    assert bad_nickname.status_code == 422
    assert bad_password.status_code == 422
    assert mismatched_password.status_code == 422


@pytest.mark.anyio
async def test_nickname_index_is_unique_and_case_insensitive(db_session: AsyncSession, owner) -> None:
    indexes = await db_session.execute(
        text(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'uq_users_nickname_normalized'"
        )
    )
    index_sql = indexes.scalar_one()
    assert "CREATE UNIQUE INDEX" in index_sql.upper()
    assert "NICKNAME_NORMALIZED" in index_sql.upper()
    duplicate = User(
        email="duplicate-owner@example.com",
        nickname="gui ferreira",
        nickname_normalized=nickname_key("gui ferreira"),
        full_name="Duplicate Owner",
        password_hash=hash_password("another long password"),
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.anyio
async def test_workspace_endpoint_only_returns_current_member_workspace(
    client: AsyncClient, owner, db_session: AsyncSession
) -> None:
    user, _workspace = owner
    auth = await login(client, "owner@example.com", "correct horse battery staple")
    own_workspace = await client.get("/api/workspace")

    other_owner = User(
        email="other-owner@example.com",
        nickname="other-owner",
        nickname_normalized=nickname_key("other-owner"),
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
async def test_super_admin_deletes_users_but_cannot_delete_self_or_workspace_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    super_admin,
    owner,
    collaborator,
) -> None:
    await login(client, "superadmin@example.com", "super admin password")

    self_delete = await client.delete(
        f"/api/admin/users/{super_admin.id}",
        headers={"X-CSRF-Token": await csrf(client)},
    )
    assert self_delete.status_code == 409

    owner_delete = await client.delete(
        f"/api/admin/users/{owner[0].id}",
        headers={"X-CSRF-Token": await csrf(client)},
    )
    assert owner_delete.status_code == 409
    assert await db_session.get(User, owner[0].id) is not None

    deleted = await client.delete(
        f"/api/admin/users/{collaborator.id}",
        headers={"X-CSRF-Token": await csrf(client)},
    )
    assert deleted.status_code == 204, deleted.text
    assert await db_session.get(User, collaborator.id) is None
    assert await db_session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == collaborator.id)
    ) is None


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
