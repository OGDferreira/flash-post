import io
import os
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Extension, SupportTicket, User, Workspace
from tests.test_loops import _csrf, _login

OWNER_PW = "correct horse battery staple"
COLLAB_PW = "collaborator password"


def _zip(entries: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in (entries or {"manifest.json": b"{}", "src/a.js": b"1"}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


async def _create(client: AsyncClient, **extra) -> dict:
    response = await client.post(
        "/api/extensions",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"name": "Auto Login", "description": "Faz login", "instructions": "1. Descompacte", **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _upload(client: AsyncClient, ext_id: str, body: bytes, content_type="application/zip", name="my ext.zip"):
    return await client.put(
        f"/api/extensions/{ext_id}/file",
        headers={"X-CSRF-Token": await _csrf(client), "Content-Type": content_type, "X-File-Name": name},
        content=body,
    )


@pytest.mark.anyio
async def test_owner_uploads_and_authorized_collaborator_downloads(
    client: AsyncClient, owner, collaborator
) -> None:
    await _login(client, "owner@example.com", OWNER_PW)
    ext = await _create(client)
    assert ext["has_file"] is False
    ok = await _upload(client, ext["id"], _zip())
    assert ok.status_code == 200, ok.text
    assert ok.json()["file_name"] == "my_ext.zip" and ok.json()["has_file"] is True
    hidden = await _create(client, visible_to_collaborators=False, name="Interna")
    await _upload(client, hidden["id"], _zip())
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})

    await _login(client, "collaborator@example.com", COLLAB_PW)
    listed = (await client.get("/api/extensions")).json()
    assert [item["name"] for item in listed] == ["Auto Login"]  # hidden one is not listed
    download = await client.get(f"/api/extensions/{ext['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"
    assert zipfile.ZipFile(io.BytesIO(download.content)).namelist() == ["manifest.json", "src/a.js"]
    assert (await client.get(f"/api/extensions/{hidden['id']}/download")).status_code == 404
    token = await _csrf(client)
    assert (await client.post("/api/extensions", headers={"X-CSRF-Token": token}, json={"name": "xx"})).status_code == 403
    assert (await _upload(client, ext["id"], _zip())).status_code == 403
    assert (await client.delete(f"/api/extensions/{ext['id']}", headers={"X-CSRF-Token": token})).status_code == 403


@pytest.mark.anyio
async def test_upload_validation(client: AsyncClient, owner, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.extensions import router as extensions_router

    await _login(client, "owner@example.com", OWNER_PW)
    ext = await _create(client)
    assert (await _upload(client, ext["id"], b"not a zip at all")).status_code == 415
    assert (await _upload(client, ext["id"], _zip(), content_type="text/html")).status_code == 415
    assert (await _upload(client, ext["id"], _zip({"../evil.sh": b"x"}))).status_code == 422
    assert (await _upload(client, ext["id"], _zip({"/abs/path": b"x"}))).status_code == 422
    assert (await _upload(client, ext["id"], b"PK\x03\x04" + b"\x00" * 30)).status_code == 415  # fake header
    monkeypatch.setattr(extensions_router, "MAX_ZIP_BYTES", 1000)
    big = _zip({"big.bin": os.urandom(4000)})
    assert len(big) > 1000
    assert (await _upload(client, ext["id"], big)).status_code == 413
    monkeypatch.setattr(extensions_router, "MAX_UNCOMPRESSED_BYTES", 10)
    monkeypatch.setattr(extensions_router, "MAX_ZIP_BYTES", 10_000_000)
    assert (await _upload(client, ext["id"], _zip({"a": b"x" * 100}))).status_code == 422  # zip-bomb guard
    stored = (await client.get("/api/extensions")).json()[0]
    assert stored["has_file"] is False  # nothing invalid was kept


@pytest.mark.anyio
async def test_extensions_are_isolated_per_workspace(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    from tests.test_affiliates import PASSWORD, _make_owner

    await _login(client, "owner@example.com", OWNER_PW)
    ext = await _create(client)
    await _upload(client, ext["id"], _zip())
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    await _make_owner(db_session, "outsider")
    await _login(client, "outsider@example.com", PASSWORD)
    assert (await client.get("/api/extensions")).json() == []
    assert (await client.get(f"/api/extensions/{ext['id']}/download")).status_code == 404
    token = await _csrf(client)
    assert (await client.delete(f"/api/extensions/{ext['id']}", headers={"X-CSRF-Token": token})).status_code == 404


async def _ticket(client: AsyncClient, title="Erro ao conectar", kind="PROBLEM") -> dict:
    response = await client.post(
        "/api/support/tickets",
        headers={"X-CSRF-Token": await _csrf(client)},
        json={"kind": kind, "title": title, "description": "Aparece uma tela branca ao conectar."},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.anyio
async def test_ticket_lifecycle_and_visibility(
    client: AsyncClient, db_session: AsyncSession, owner, collaborator
) -> None:
    await _login(client, "collaborator@example.com", COLLAB_PW)
    mine = await _ticket(client)
    assert mine["status"] == "OPEN" and mine["can_manage"] is False
    token = await _csrf(client)
    assert (await client.post(
        "/api/support/tickets", headers={"X-CSRF-Token": token}, json={"title": "ab", "description": "curto"}
    )).status_code == 422
    # The author cannot resolve, only close.
    denied = await client.patch(
        f"/api/support/tickets/{mine['id']}", headers={"X-CSRF-Token": token}, json={"status": "RESOLVED"}
    )
    assert denied.status_code == 403
    assert (await client.get("/api/support/tickets", params={"scope": "workspace"})).status_code == 403
    assert (await client.get("/api/support/tickets", params={"scope": "all"})).status_code == 403
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": token})

    await _login(client, "owner@example.com", OWNER_PW)
    own = await _ticket(client, title="Dúvida do chefe", kind="QUESTION")
    team = (await client.get("/api/support/tickets", params={"scope": "workspace"})).json()
    assert [item["id"] for item in team["items"]] == [mine["id"]]  # owner's own ticket is not mixed in
    assert team["items"][0]["can_manage"] is True and team["counts"]["OPEN"] == 1
    token = await _csrf(client)
    answered = await client.patch(
        f"/api/support/tickets/{mine['id']}", headers={"X-CSRF-Token": token},
        json={"status": "IN_PROGRESS", "resolution_note": "Estamos verificando."},
    )
    assert answered.status_code == 200 and answered.json()["status"] == "IN_PROGRESS"
    resolved = await client.patch(
        f"/api/support/tickets/{mine['id']}", headers={"X-CSRF-Token": token},
        json={"status": "RESOLVED", "resolution_note": "Reconecte a conta."},
    )
    assert resolved.json()["resolved_at"] is not None
    # The owner cannot resolve their own ticket (only a platform admin can).
    own_try = await client.patch(
        f"/api/support/tickets/{own['id']}", headers={"X-CSRF-Token": token}, json={"status": "RESOLVED"}
    )
    assert own_try.status_code == 403
    closed = await client.patch(
        f"/api/support/tickets/{own['id']}", headers={"X-CSRF-Token": token}, json={"status": "CLOSED"}
    )
    assert closed.status_code == 200
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": token})

    await _login(client, "collaborator@example.com", COLLAB_PW)
    seen = (await client.get("/api/support/tickets")).json()
    assert seen["items"][0]["status"] == "RESOLVED"
    assert seen["items"][0]["resolution_note"] == "Reconecte a conta."


@pytest.mark.anyio
async def test_super_admin_sees_and_resolves_all_tickets(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    from app.core.nickname import nickname_key
    from app.core.security import hash_password
    from app.models import WorkspaceMember

    await _login(client, "owner@example.com", OWNER_PW)
    ticket = await _ticket(client)
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    admin = User(
        email="admin@example.com", nickname="Admin", nickname_normalized=nickname_key("Admin"),
        full_name="Admin", password_hash=hash_password("admin password 1"), platform_role="SUPER_ADMIN",
        is_active=True, is_verified=True,
    )
    db_session.add(admin)
    await db_session.flush()
    workspace = await db_session.scalar(select(Workspace))
    db_session.add(WorkspaceMember(workspace_id=workspace.id, user_id=admin.id, role="COLLABORATOR", status="ACTIVE"))
    await db_session.commit()
    await _login(client, "admin@example.com", "admin password 1")
    everything = (await client.get("/api/support/tickets", params={"scope": "all"})).json()
    assert everything["total"] == 1
    done = await client.patch(
        f"/api/support/tickets/{ticket['id']}", headers={"X-CSRF-Token": await _csrf(client)},
        json={"status": "RESOLVED", "resolution_note": "Corrigido na 0.4.0"},
    )
    assert done.status_code == 200 and done.json()["can_manage"] is True
