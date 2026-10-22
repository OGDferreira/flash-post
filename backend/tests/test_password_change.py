import pytest
from httpx import AsyncClient

from tests.test_auth import login

OLD = "correct horse battery staple"
NEW = "another long secret phrase"


async def _change(client: AsyncClient, csrf_token: str, current: str, new: str, confirm: str | None = None):
    return await client.post(
        "/api/profile/password",
        headers={"X-CSRF-Token": csrf_token},
        json={"current_password": current, "new_password": new, "confirm_password": confirm or new},
    )


@pytest.mark.anyio
async def test_password_change_requires_current_password_and_then_signs_in_with_new(client: AsyncClient, owner) -> None:
    token = (await login(client, "owner@example.com", OLD))["csrf_token"]

    wrong = await _change(client, token, "not my password", NEW)
    assert wrong.status_code == 400
    mismatch = await _change(client, token, OLD, NEW, "something different!")
    assert mismatch.status_code == 422
    same = await _change(client, token, OLD, OLD)
    assert same.status_code == 422

    ok = await _change(client, token, OLD, NEW)
    assert ok.status_code == 200, ok.text
    assert ok.json()["csrf_token"]
    # The session stays signed in.
    assert (await client.get("/api/auth/me")).status_code == 200

    await client.post("/api/auth/logout", headers={"X-CSRF-Token": ok.json()["csrf_token"]})
    token = (await client.get("/api/auth/csrf")).json()["csrf_token"]
    old_login = await client.post("/api/auth/login", headers={"X-CSRF-Token": token}, json={"email": "owner@example.com", "password": OLD})
    assert old_login.status_code == 401
    await login(client, "owner@example.com", NEW)


@pytest.mark.anyio
async def test_password_change_needs_a_session_and_csrf(client: AsyncClient, owner) -> None:
    token = (await client.get("/api/auth/csrf")).json()["csrf_token"]
    assert (await _change(client, token, OLD, NEW)).status_code == 401
    await login(client, "owner@example.com", OLD)
    assert (await _change(client, "bad-token", OLD, NEW)).status_code == 403
