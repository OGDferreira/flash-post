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

    # nothing is recorded about the visit (the platform owner's decision)
    assert (await db_session.scalars(select(AdminAuditLog))).all() == []


@pytest.mark.anyio
async def test_super_admin_visit_leaves_no_trace_for_the_owner(client: AsyncClient, db_session: AsyncSession, owner, super_admin) -> None:
    from app.models import AppNotification

    owner_user, _workspace = owner
    db_session.add(AppNotification(user_id=owner_user.id, kind="sale", title="Nova venda", body="R$ 10"))
    await db_session.commit()
    await login(client, "superadmin@example.com", "super admin password")
    headers = {"X-CSRF-Token": await csrf(client)}
    assert (await client.post(f"/api/admin/users/{owner_user.id}/impersonate", headers=headers)).status_code == 200
    # reading the owner's notices doesn't mark them as read
    assert (await client.post("/api/partners/notifications/read", headers=headers)).status_code == 204
    assert (await client.get("/api/partners/notifications")).json()["unread"] == 1
    # the admin's device never subscribes to the owner's pushes, and the owner's choice doesn't change
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "B" + "A" * 86, "auth": "A" * 22}}
    assert (await client.post("/api/notifications/push/subscriptions", headers=headers, json=sub)).status_code == 409
    pref = await client.put("/api/notifications/push/preference", headers=headers, json={"enabled": True})
    assert pref.json()["enabled"] is False and pref.json()["impersonating"] is True


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


@pytest.mark.anyio
async def test_push_choice_is_saved_on_the_account_and_the_prompt_answered_once(client: AsyncClient, owner) -> None:
    await login(client, "owner@example.com", "correct horse battery staple")
    headers = {"X-CSRF-Token": await csrf(client)}
    config = (await client.get("/api/notifications/push/config")).json()
    assert config["prompt_done"] is False and config["enabled"] is False
    dismissed = await client.put("/api/notifications/push/preference", headers=headers, json={"prompt_done": True})
    assert dismissed.json()["prompt_done"] is True and dismissed.json()["enabled"] is False
    on = await client.put("/api/notifications/push/preference", headers=headers, json={"enabled": True})
    assert on.json()["enabled"] is True
    assert (await client.get("/api/notifications/push/config")).json()["enabled"] is True
