from types import SimpleNamespace

import httpx
import pytest

from app.instagram import publishing


class _Response:
    def __init__(self, payload: dict[str, str], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, str]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://graph.instagram.com/test")
            response = httpx.Response(self.status_code, request=request, json=self._payload)
            raise httpx.HTTPStatusError(
                "request failed",
                request=request,
                response=response,
            )


class _Storage:
    async def create_signed_url(self, storage_path: str) -> str:
        assert storage_path == "workspace/media.mp4"
        return "https://storage.example/signed-media-url"


class _GraphClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.statuses = iter(("IN_PROGRESS", "FINISHED"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, url: str, data: dict[str, str]) -> _Response:
        self.calls.append(("POST", url))
        if url.endswith("/media"):
            assert data["video_url"] == "https://storage.example/signed-media-url"
            assert data["media_type"] == "REELS"
            return _Response({"id": "container-123"})
        if url.endswith("/media_publish"):
            assert data["creation_id"] == "container-123"
            return _Response({"id": "published-456"})
        raise AssertionError(f"Unexpected POST endpoint: {url}")

    async def get(self, url: str, params: dict[str, str]) -> _Response:
        self.calls.append(("GET", url))
        assert params["fields"] == "status_code"
        return _Response({"status_code": next(self.statuses)})


@pytest.mark.anyio
async def test_video_container_finishes_processing_before_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _GraphClient()
    monkeypatch.setattr(
        publishing.httpx,
        "AsyncClient",
        lambda **_kwargs: client,
    )

    async def no_wait(_seconds: int) -> None:
        return None

    monkeypatch.setattr(publishing.asyncio, "sleep", no_wait)
    account = SimpleNamespace(
        username="loop_account",
        instagram_user_id="instagram-user-123",
    )
    media = SimpleNamespace(
        id="media-123",
        media_type="video",
        storage_path="workspace/media.mp4",
        caption="Test reel",
    )

    published_id = await publishing.publish_media(
        account,
        media,
        "account-specific-access-token",
        _Storage(),
    )

    assert published_id == "published-456"
    assert [method for method, _url in client.calls] == [
        "POST",
        "GET",
        "GET",
        "POST",
    ]
    assert client.calls[0][1].endswith("/instagram-user-123/media")
    assert client.calls[1][1].endswith("/container-123")
    assert client.calls[2][1].endswith("/container-123")
    assert client.calls[3][1].endswith("/instagram-user-123/media_publish")
