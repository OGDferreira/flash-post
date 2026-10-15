import pytest
from httpx import AsyncClient

from tests.test_auth import csrf, login


@pytest.mark.anyio
async def test_super_admin_edits_resets_and_tests_milestone_texts(client: AsyncClient, super_admin, owner) -> None:
    await login(client, "owner@example.com", "correct horse battery staple")
    assert (await client.get("/api/admin/notifications/messages")).status_code == 403

    await login(client, "superadmin@example.com", "super admin password")
    data = (await client.get("/api/admin/notifications/messages")).json()
    assert {k["kind"] for k in data["kinds"]} == {"views", "posts", "sales", "followers"}
    assert data["customized"] is False

    headers = {"X-CSRF-Token": await csrf(client)}
    saved = await client.put(
        "/api/admin/notifications/messages",
        json={"messages": {"views": {"10000": [{"title": "Teste {valor}", "body": "Oi {nome}"}]}}},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["messages"]["views"]["10000"] == [{"title": "Teste {valor}", "body": "Oi {nome}"}]
    bad = await client.put(
        "/api/admin/notifications/messages",
        json={"messages": {"views": {"123": [{"title": "x", "body": "y"}]}}},
        headers=headers,
    )
    assert bad.status_code == 422

    test = await client.post(
        "/api/admin/notifications/test", json={"kind": "views", "threshold": 10000, "variant": 0}, headers=headers
    )
    assert test.status_code == 200
    body = test.json()
    assert body["title"] == "Teste 10.000" and body["devices"] == 0

    reset = await client.delete("/api/admin/notifications/messages", headers=headers)
    assert reset.json()["customized"] is False
