import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value
from app.models import EmailAccount


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def _login(client: AsyncClient, email: str, password: str) -> None:
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_owner_creates_edits_and_deletes_email_account(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _user, _workspace = owner
    await _login(client, "owner@example.com", "correct horse battery staple")
    payload = {
        "supplier": "Moraes",
        "email": "Inbox.User@example.com",
        "password": "private-email-password",
        "two_factor_code": "private-2fa-seed",
    }
    created = await client.post(
        "/api/emails",
        headers={"X-CSRF-Token": await _csrf(client)},
        json=payload,
    )
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["email"] == "inbox.user@example.com"
    assert item["status"] == "available"
    account = await db_session.get(EmailAccount, uuid.UUID(item["id"]))
    assert account is not None
    assert account.encrypted_password != payload["password"]
    assert account.encrypted_two_factor_code != payload["two_factor_code"]
    assert decrypt_value(account.encrypted_password) == payload["password"]
    assert decrypt_value(account.encrypted_two_factor_code) == payload["two_factor_code"]

    listing = await client.get("/api/emails")
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store"
    assert listing.json()["can_manage"] is True
    assert listing.json()["counts"] == {
        "total": 1,
        "available": 1,
        "in_use": 0,
        "completed": 0,
        "error": 0,
        "returned": 0,
    }

    edited = await client.put(
        f"/api/emails/{item['id']}",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={
            **payload,
            "supplier": "Updated supplier",
            "password": "changed-password",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["supplier"] == "Updated supplier"
    assert edited.json()["password"] == "changed-password"

    deleted = await client.delete(
        f"/api/emails/{item['id']}",
        headers={"X-CSRF-Token": await _csrf(client)},
    )
    assert deleted.status_code == 204
    assert await db_session.get(EmailAccount, uuid.UUID(item["id"])) is None


@pytest.mark.anyio
async def test_collaborator_can_cycle_status_and_update_observation_only(
    client: AsyncClient,
    db_session: AsyncSession,
    collaborator,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.emails import router as email_router

    _owner_user, workspace = owner
    user = collaborator
    account = EmailAccount(
        workspace_id=workspace.id,
        supplier="Moraes",
        email="worker@example.com",
        encrypted_password=encrypt_value("worker-password"),
        encrypted_two_factor_code=encrypt_value("worker-2fa"),
        status="available",
    )
    db_session.add(account)
    await db_session.commit()
    await _login(client, "collaborator@example.com", "collaborator password")

    listing = await client.get("/api/emails")
    assert listing.status_code == 200
    assert listing.json()["can_manage"] is False
    assert listing.json()["accounts"][0]["password"] == "worker-password"
    assert listing.json()["accounts"][0]["two_factor_code"] == "worker-2fa"

    for next_status in ("in_use", "completed", "error", "returned", "available"):
        changed = await client.patch(
            f"/api/emails/{account.id}/status",
            headers={"X-CSRF-Token": await _csrf(client)},
            json={"status": next_status},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["responsible"] == user.nickname
        assert changed.json()["status"] == next_status

    wrong_step = await client.patch(
        f"/api/emails/{account.id}/status",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"status": "completed"},
    )
    assert wrong_step.status_code == 409

    observation = await client.patch(
        f"/api/emails/{account.id}/observation",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"observation": "  Login returned an error  "},
    )
    assert observation.status_code == 200
    assert observation.json()["observation"] == "Login returned an error"

    class FakeStorage:
        @classmethod
        def from_settings(cls):
            return cls()

        async def upload(self, _path: str, _content: bytes, _content_type: str) -> None:
            return None

        async def create_signed_url(self, path: str) -> str:
            return f"https://storage.example/{path}"

        async def delete(self, _path: str) -> None:
            return None

    monkeypatch.setattr(
        email_router.SupabaseStorage, "from_settings", FakeStorage.from_settings
    )
    uploaded = await client.post(
        f"/api/emails/{account.id}/attachment?filename=error.png",
        headers={
            "X-CSRF-Token": await _csrf(client),
            "Content-Type": "image/png",
        },
        content=b"\x89PNG\r\n\x1a\nvalid-test-image",
    )
    assert uploaded.status_code == 200, uploaded.text

    forbidden_create = await client.post(
        "/api/emails",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={
            "supplier": "Moraes",
            "email": "forbidden@example.com",
            "password": "secret-password",
            "two_factor_code": "secret-2fa",
        },
    )
    assert forbidden_create.status_code == 403
    forbidden_edit = await client.put(
        f"/api/emails/{account.id}",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={
            "supplier": "Hacked supplier",
            "email": "changed@example.com",
            "password": "changed",
            "two_factor_code": "changed",
        },
    )
    assert forbidden_edit.status_code == 403
    forbidden_delete = await client.delete(
        f"/api/emails/{account.id}",
        headers={"X-CSRF-Token": await _csrf(client)},
    )
    assert forbidden_delete.status_code == 403


@pytest.mark.anyio
async def test_email_error_image_upload_requires_an_image_and_stores_privately(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.emails import router as email_router

    _user, workspace = owner
    account = EmailAccount(
        workspace_id=workspace.id,
        supplier="Moraes",
        email="error@example.com",
        encrypted_password=encrypt_value("password"),
        encrypted_two_factor_code=encrypt_value("two-factor"),
    )
    db_session.add(account)
    await db_session.commit()

    class FakeStorage:
        uploads: list[tuple[str, bytes, str]] = []

        @classmethod
        def from_settings(cls):
            return cls()

        async def upload(self, path: str, content: bytes, content_type: str) -> None:
            self.uploads.append((path, content, content_type))

        async def create_signed_url(self, path: str) -> str:
            return f"https://storage.example/{path}"

        async def delete(self, _path: str) -> None:
            return None

    monkeypatch.setattr(email_router.SupabaseStorage, "from_settings", FakeStorage.from_settings)
    await _login(client, "owner@example.com", "correct horse battery staple")
    invalid = await client.post(
        f"/api/emails/{account.id}/attachment?filename=not-image.png",
        headers={
            "X-CSRF-Token": await _csrf(client),
            "Content-Type": "image/png",
        },
        content=b"not an image",
    )
    assert invalid.status_code == 415

    content = b"\x89PNG\r\n\x1a\n" + b"valid-test-image"
    uploaded = await client.post(
        f"/api/emails/{account.id}/attachment?filename=error.png",
        headers={
            "X-CSRF-Token": await _csrf(client),
            "Content-Type": "image/png",
        },
        content=content,
    )
    assert uploaded.status_code == 200, uploaded.text
    assert FakeStorage.uploads[0][1:] == (content, "image/png")
    await db_session.refresh(account)
    assert account.error_attachment_path is not None
    assert account.error_attachment_path.startswith(
        f"{workspace.id}/email-errors/{account.id}/"
    )
    attachment = await client.get(f"/api/emails/{account.id}/attachment")
    assert attachment.status_code == 307
    assert attachment.headers["location"].startswith("https://storage.example/")
