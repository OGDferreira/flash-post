import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog
from tests.test_auth import csrf, login


@pytest.mark.anyio
async def test_super_admin_enters_user_account_and_returns(
    client: AsyncClient, db_session: AsyncSession, owner, super_admin
) -> None:
    owner_user, workspace = owner
    await login(client, "superadmin@example.com", "super admin password")
    token = await csrf(client)

    response = await client.post(f"/api/admin/users/{owner_user.id}/impersonate", headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.text

    me = (await client.get("/api/auth/me")).json()
    assert me["id"] == str(owner_user.id)
    assert me["impersonator_name"] == "FlashPost Super Admin"
    assert (await client.get("/api/workspace")).json()["id"] == str(workspace.id)
    # Admin-only endpoints are closed while acting as the user.
    assert (await client.get("/api/admin/users")).status_code == 403

    response = await client.post("/api/auth/impersonation/stop", headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.text
    me = (await client.get("/api/auth/me")).json()
    assert me["id"] == str(super_admin.id)
    assert me["impersonator_name"] is None
    assert (await client.get("/api/admin/users")).status_code == 200

    actions = (
        await db_session.scalars(
            select(AdminAuditLog.action)
            .where(AdminAuditLog.actor_user_id == super_admin.id, AdminAuditLog.target_user_id == owner_user.id)
            .order_by(AdminAuditLog.created_at)
        )
    ).all()
    assert sorted(actions) == ["IMPERSONATE_START", "IMPERSONATE_STOP"]


@pytest.mark.anyio
async def test_regular_user_cannot_impersonate(client: AsyncClient, owner, collaborator) -> None:
    await login(client, "owner@example.com", "correct horse battery staple")
    token = await csrf(client)
    response = await client.post(f"/api/admin/users/{collaborator.id}/impersonate", headers={"X-CSRF-Token": token})
    assert response.status_code == 403
    response = await client.post("/api/auth/impersonation/stop", headers={"X-CSRF-Token": token})
    assert response.status_code == 400
    assert (await client.get("/api/auth/me")).json()["email"] == "owner@example.com"


@pytest.mark.anyio
async def test_cannot_enter_super_admin_account(client: AsyncClient, super_admin) -> None:
    await login(client, "superadmin@example.com", "super admin password")
    token = await csrf(client)
    response = await client.post(f"/api/admin/users/{super_admin.id}/impersonate", headers={"X-CSRF-Token": token})
    assert response.status_code == 400
