import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, WorkspaceMember


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def _login(client: AsyncClient, email: str, password: str):
    token = await _csrf(client)
    return await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": email, "password": password},
    )


def _signup(nickname: str, email: str) -> dict:
    return {
        "full_name": "Novo Colaborador",
        "email": email,
        "nickname": nickname,
        "password": "safe-collaborator-password",
        "confirm_password": "safe-collaborator-password",
    }


@pytest.mark.anyio
async def test_invite_signup_requires_owner_approval_and_keeps_owner_settings(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    _owner_user, workspace = owner
    assert (await _login(client, "owner@example.com", "correct horse battery staple")).status_code == 200
    token = await _csrf(client)

    defaults = (await client.get("/api/collaborators/invites/defaults")).json()
    assert defaults["from_last_invite"] is False

    created = await client.post(
        "/api/collaborators/invites",
        headers={"X-CSRF-Token": token},
        json={
            "rate_per_connection": "7.50",
            "daily_connection_goal": 3,
            "monthly_connection_goal": 60,
            "monthly_bonus": "20.00",
        },
    )
    assert created.status_code == 201, created.text
    invite = created.json()
    assert invite["status"] == "active"
    # "Last used settings" now come from this invite.
    defaults = (await client.get("/api/collaborators/invites/defaults")).json()
    assert defaults == {
        "rate_per_connection": "7.50",
        "daily_connection_goal": 3,
        "monthly_connection_goal": 60,
        "monthly_bonus": "20.00",
        "from_last_invite": True,
    }
    listed = (await client.get("/api/collaborators/invites")).json()["invites"]
    assert "token" not in listed[0]

    # Collaborator opens the link anonymously and registers.
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": token})
    info = await client.get(f"/api/auth/collaborator-invites/{invite['token']}")
    assert info.status_code == 200
    csrf = await _csrf(client)
    signup = await client.post(
        f"/api/auth/collaborator-invites/{invite['token']}/register",
        headers={"X-CSRF-Token": csrf},
        json=_signup("novo.colab", "novo.colab@example.com"),
    )
    assert signup.status_code == 201, signup.text

    # Single-use link: it is spent now.
    again = await client.post(
        f"/api/auth/collaborator-invites/{invite['token']}/register",
        headers={"X-CSRF-Token": csrf},
        json=_signup("outro.colab", "outro.colab@example.com"),
    )
    assert again.status_code == 404

    # Blocked until the Super Admin approves the account...
    blocked = await _login(client, "novo.colab@example.com", "safe-collaborator-password")
    assert blocked.status_code == 403
    assert "administrador" in blocked.json()["detail"]
    new_user = await db_session.scalar(select(User).where(User.email == "novo.colab@example.com"))
    assert new_user.is_approved is False
    new_user.is_approved = True
    await db_session.commit()

    # ...and until the owner approves the access.
    blocked = await _login(client, "novo.colab@example.com", "safe-collaborator-password")
    assert blocked.status_code == 403
    assert "chefe" in blocked.json()["detail"]

    assert (await _login(client, "owner@example.com", "correct horse battery staple")).status_code == 200
    token = await _csrf(client)
    team = (await client.get("/api/collaborators")).json()
    assert team["collaborators"] == []
    assert len(team["pending"]) == 1
    pending = team["pending"][0]
    assert pending["rate_per_connection"] == "7.50"
    assert pending["daily_connection_goal"] == 3

    approved = await client.post(
        f"/api/collaborators/{pending['member_id']}/approve", headers={"X-CSRF-Token": token}
    )
    assert approved.status_code == 204
    team = (await client.get("/api/collaborators")).json()
    assert team["pending"] == []
    assert team["collaborators"][0]["rate_per_connection"] == "7.50"

    await client.post("/api/auth/logout", headers={"X-CSRF-Token": token})
    ok = await _login(client, "novo.colab@example.com", "safe-collaborator-password")
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["role"] == "COLLABORATOR"


@pytest.mark.anyio
async def test_invite_revoked_expired_and_reject_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    body = {
        "rate_per_connection": "1.00",
        "daily_connection_goal": 1,
        "monthly_connection_goal": 1,
        "monthly_bonus": "0.00",
        "max_uses": 5,
    }
    revoked = (await client.post("/api/collaborators/invites", headers={"X-CSRF-Token": token}, json=body)).json()
    assert (
        await client.delete(f"/api/collaborators/invites/{revoked['id']}", headers={"X-CSRF-Token": token})
    ).status_code == 204
    assert (await client.get(f"/api/auth/collaborator-invites/{revoked['token']}")).status_code == 404
    assert (await client.get("/api/collaborators/invites")).json()["invites"][0]["status"] == "revoked"

    good = (await client.post("/api/collaborators/invites", headers={"X-CSRF-Token": token}, json=body)).json()
    signup = await client.post(
        f"/api/auth/collaborator-invites/{good['token']}/register",
        headers={"X-CSRF-Token": token},
        json=_signup("rejected.colab", "rejected@example.com"),
    )
    assert signup.status_code == 201, signup.text
    pending = (await client.get("/api/collaborators")).json()["pending"]
    assert (
        await client.post(
            f"/api/collaborators/{pending[0]['member_id']}/reject", headers={"X-CSRF-Token": token}
        )
    ).status_code == 204
    assert (await client.get("/api/collaborators")).json()["pending"] == []
    assert await db_session.scalar(select(User.id).where(User.email == "rejected@example.com")) is None

    bogus = await client.get(f"/api/auth/collaborator-invites/{uuid.uuid4().hex}")
    assert bogus.status_code == 404
