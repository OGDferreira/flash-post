import pytest
from httpx import ASGITransport, AsyncClient

from app.main import check_database_readiness, create_app


@pytest.mark.anyio
async def test_spa_routes_and_assets_are_served_from_built_frontend(tmp_path) -> None:
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>FlashPost test</title>",
        encoding="utf-8",
    )
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('flashpost');", encoding="utf-8")
    app = create_app(static_assets_dir=tmp_path)
    app.dependency_overrides[check_database_readiness] = lambda: True

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        health_probe = await client.head("/")
        page = await client.get("/login")
        asset = await client.get("/assets/app.js")
        missing_api = await client.get("/api/not-found")

    assert health_probe.status_code == 200
    assert health_probe.content == b""
    assert page.status_code == 200
    assert "FlashPost test" in page.text
    assert asset.status_code == 200
    assert "console.log" in asset.text
    assert missing_api.status_code == 404
    assert missing_api.json() == {"detail": "Not found."}


@pytest.mark.anyio
async def test_readiness_returns_503_when_database_is_unavailable() -> None:
    app = create_app()
    app.dependency_overrides[check_database_readiness] = lambda: False

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        readiness = await client.get("/readiness")
        health = await client.get("/health")

    assert readiness.status_code == 503
    assert readiness.json() == {
        "status": "not_ready",
        "database": "unavailable",
    }
    assert health.status_code == 200
