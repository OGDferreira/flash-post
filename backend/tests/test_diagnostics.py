import pytest
from httpx import AsyncClient


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def _login(client: AsyncClient) -> None:
    token = await _csrf(client)
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_workspace_member_can_report_and_read_browser_errors(
    client: AsyncClient,
    owner,
) -> None:
    await _login(client)
    token = await _csrf(client)

    created = await client.post(
        "/api/diagnostics/events",
        headers={"X-CSRF-Token": token},
        json={
            "source": "browser",
            "level": "error",
            "message": "TypeError: example failure",
            "stack": "at render (bundle.js:10)",
            "path": "/dashboard",
        },
    )

    assert created.status_code == 200, created.text
    assert created.json()["source"] == "browser"
    assert created.json()["message"] == "TypeError: example failure"

    listed = await client.get("/api/diagnostics/events")

    assert listed.status_code == 200, listed.text
    assert listed.json()["events"][0]["stack"] == "at render (bundle.js:10)"
