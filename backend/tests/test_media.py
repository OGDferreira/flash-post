from datetime import datetime, timezone
import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.instagram import publishing
from app.instagram.storage import SupabaseStorage
from app.models import InstagramAccount, InstagramMedia


async def _csrf(client: AsyncClient) -> str:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def _login(client: AsyncClient) -> None:
    csrf = await _csrf(client)
    response = await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": csrf},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_owner_uploads_private_media_and_saves_workspace_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
    owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, workspace = owner

    class FakeStorage:
        def __init__(self) -> None:
            self.uploaded: tuple[str, bytes, str] | None = None

        async def upload(self, path: str, content: bytes, content_type: str) -> None:
            self.uploaded = (path, content, content_type)

    storage = FakeStorage()
    monkeypatch.setattr(
        SupabaseStorage,
        "from_settings",
        classmethod(lambda _cls: storage),
    )
    await _login(client)
    csrf = await _csrf(client)
    jpeg_data = b"\xff\xd8\xff" + b"image-data"

    response = await client.post(
        "/api/media?filename=photo.jpg&caption=Hello%20Instagram",
        content=jpeg_data,
        headers={"X-CSRF-Token": csrf, "Content-Type": "image/jpeg"},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["filename"] == "photo.jpg"
    assert payload["media_type"] == "image"
    assert payload["caption"] == "Hello Instagram"
    assert storage.uploaded is not None
    path, stored_bytes, content_type = storage.uploaded
    assert path.startswith(f"{workspace.id}/")
    assert stored_bytes == jpeg_data
    assert content_type == "image/jpeg"
    persisted = await db_session.scalar(
        select(InstagramMedia).where(InstagramMedia.id == uuid.UUID(payload["id"]))
    )
    assert persisted is not None
    assert persisted.workspace_id == workspace.id
    assert persisted.storage_path == path


@pytest.mark.anyio
async def test_media_upload_rejects_mismatched_file_content(
    client: AsyncClient,
    owner,
) -> None:
    await _login(client)
    csrf = await _csrf(client)

    response = await client.post(
        "/api/media?filename=fake.jpg",
        content=b"not a JPEG",
        headers={"X-CSRF-Token": csrf, "Content-Type": "image/jpeg"},
    )

    assert response.status_code == 415
    assert "contents do not match" in response.json()["detail"]


@pytest.mark.anyio
async def test_image_publication_creates_and_publishes_instagram_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def __init__(self, payload: object):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self.payload

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str, *, params: dict[str, str]):
            assert url.endswith("/me")
            assert params["fields"] == "user_id,username"
            return FakeResponse({"user_id": "instagram-user-1", "username": "test_account"})

        async def post(self, url: str, *, data: dict[str, str]):
            calls.append((url, data))
            return FakeResponse(
                {"id": "container-1" if url.endswith("/media") else "published-1"}
            )

    class FakeStorage:
        async def create_signed_url(self, path: str) -> str:
            assert path == "workspace/media/photo.jpg"
            return "https://private-storage.example/signed-photo"

    monkeypatch.setattr(publishing.httpx, "AsyncClient", FakeClient)
    account = InstagramAccount(
        workspace_id=uuid.uuid4(),
        instagram_user_id="instagram-user-1",
        username="test_account",
        encrypted_access_token="encrypted",
        token_expires_at=datetime.now(timezone.utc),
    )
    media = InstagramMedia(
        workspace_id=account.workspace_id,
        storage_path="workspace/media/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        media_type="image",
        size_bytes=100,
        caption="Test caption",
    )

    published_id = await publishing.publish_media(
        account,
        media,
        "private-access-token",
        FakeStorage(),
    )

    assert published_id == "published-1"
    assert calls[0][0].endswith("/instagram-user-1/media")
    assert calls[0][1]["image_url"] == "https://private-storage.example/signed-photo"
    assert calls[0][1]["caption"] == "Test caption"
    assert calls[1][0].endswith("/instagram-user-1/media_publish")
    assert calls[1][1]["creation_id"] == "container-1"


@pytest.mark.anyio
async def test_video_publication_waits_for_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = iter(("IN_PROGRESS", "FINISHED"))

    class FakeResponse:
        def __init__(self, payload: object):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self.payload

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, *, data: dict[str, str]):
            return FakeResponse(
                {"id": "container-2" if url.endswith("/media") else "published-2"}
            )

        async def get(self, url: str, *, params: dict[str, str]):
            if url.endswith("/me"):
                assert params["fields"] == "user_id,username"
                return FakeResponse({"user_id": "instagram-user-2", "username": "test_account"})
            assert params["fields"] == "status_code,status"
            return FakeResponse({"status_code": next(statuses)})

    class FakeStorage:
        async def create_signed_url(self, _path: str) -> str:
            return "https://private-storage.example/signed-video"

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr(publishing.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(publishing.asyncio, "sleep", no_wait)
    account = InstagramAccount(
        workspace_id=uuid.uuid4(),
        instagram_user_id="instagram-user-2",
        username="test_account",
        encrypted_access_token="encrypted",
        token_expires_at=datetime.now(timezone.utc),
    )
    media = InstagramMedia(
        workspace_id=account.workspace_id,
        storage_path="workspace/media/reel.mp4",
        filename="reel.mp4",
        mime_type="video/mp4",
        media_type="video",
        size_bytes=100,
    )

    published_id = await publishing.publish_media(
        account,
        media,
        "private-access-token",
        FakeStorage(),
    )

    assert published_id == "published-2"


@pytest.mark.anyio
async def test_publication_error_preserves_meta_reason_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed_url = "https://private-storage.example/signed-photo?token=signed-secret"

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str, *, params: dict[str, str]):
            assert url.endswith("/me")
            assert params["fields"] == "user_id,username"
            return httpx.Response(200, json={"user_id": "instagram-user-error", "username": "test_account"}, request=httpx.Request("GET", url))

        async def post(self, url: str, *, data: dict[str, str]):
            request = httpx.Request("POST", url)
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": f"Invalid image URL {signed_url}; token private-access-token",
                        "type": "OAuthException",
                        "code": 9004,
                        "error_subcode": 2207052,
                    },
                    "fbtrace_id": "trace-abc123",
                },
                request=request,
            )

    class FakeStorage:
        async def create_signed_url(self, _path: str) -> str:
            return signed_url

    monkeypatch.setattr(publishing.httpx, "AsyncClient", FakeClient)
    account = InstagramAccount(
        workspace_id=uuid.uuid4(),
        instagram_user_id="instagram-user-error",
        username="test_account",
        encrypted_access_token="encrypted",
        token_expires_at=datetime.now(timezone.utc),
    )
    media = InstagramMedia(
        workspace_id=account.workspace_id,
        storage_path="workspace/media/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        media_type="image",
        size_bytes=100,
    )

    with pytest.raises(publishing.InstagramPublishingError) as error:
        await publishing.publish_media(
            account,
            media,
            "private-access-token",
            FakeStorage(),
        )

    message = str(error.value)
    assert "media container creation" in message
    assert "HTTP 400" in message
    assert "code 9004" in message
    assert "subcode 2207052" in message
    assert "trace trace-abc123" in message
    assert "Invalid image URL" in message
    assert "private-access-token" not in message
    assert "signed-secret" not in message
