import httpx
import pytest

from app.instagram import storage as storage_module
from app.instagram.storage import SupabaseStorage, SupabaseStorageError


def test_normalize_path_removes_double_slashes_and_invisible_characters() -> None:
    assert (
        SupabaseStorage.normalize_path("/ws//folder/\u200bvideo\u00a0.mp4 ")
        == "ws/folder/video.mp4"
    )
    with pytest.raises(SupabaseStorageError):
        SupabaseStorage.normalize_path("ws/../secret.mp4")


@pytest.mark.anyio
async def test_signed_url_retries_after_gateway_error(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    responses = [
        httpx.Response(502),
        httpx.Response(200, json={"signedURL": "/object/sign/instagram-media/a.mp4?token=x"}),
    ]
    requested_urls: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url, **kwargs):
            requested_urls.append(url)
            return responses.pop(0)

    monkeypatch.setattr(storage_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(storage_module.httpx, "AsyncClient", FakeClient)

    storage = SupabaseStorage("https://project.supabase.co", "service-key")
    url = await storage.create_signed_url("ws//a.mp4")

    assert url.startswith("https://project.supabase.co/storage/v1/object/sign/")
    assert sleeps == [2]
    assert all(request.endswith("/instagram-media/ws/a.mp4") for request in requested_urls)


@pytest.mark.anyio
async def test_signed_url_gives_up_after_repeated_gateway_errors(monkeypatch) -> None:
    async def fake_sleep(seconds: float) -> None:
        return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url, **kwargs):
            return httpx.Response(502)

    monkeypatch.setattr(storage_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(storage_module.httpx, "AsyncClient", FakeClient)

    storage = SupabaseStorage("https://project.supabase.co", "service-key")
    with pytest.raises(SupabaseStorageError, match="HTTP 502"):
        await storage.create_signed_url("ws/a.mp4")
