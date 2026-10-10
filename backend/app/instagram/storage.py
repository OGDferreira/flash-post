import asyncio
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import get_settings

MEDIA_BUCKET = "instagram-media"
SIGNED_URL_TTL_SECONDS = 4 * 60 * 60
SIGN_MAX_ATTEMPTS = 4
SIGN_BACKOFF_SECONDS = 2
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_INVISIBLE_CHARS = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00a0"}


class SupabaseStorageError(RuntimeError):
    pass


class SupabaseStorage:
    def __init__(self, base_url: str, service_role_key: str) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("SUPABASE_URL must be a valid project URL.")
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        }

    @classmethod
    def from_settings(cls) -> "SupabaseStorage":
        settings = get_settings()
        if settings.supabase_url is None or settings.supabase_service_role_key is None:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured."
            )
        return cls(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
        )

    @staticmethod
    def _quoted_path(path: str) -> str:
        return "/".join(quote(part, safe="") for part in path.split("/"))

    @staticmethod
    def normalize_path(path: str) -> str:
        """Remove espaços invisíveis, barras duplas e barras nas pontas."""
        cleaned = "".join(
            ch for ch in path if ch.isprintable() and ch not in _INVISIBLE_CHARS
        )
        parts = [part.strip() for part in cleaned.replace("\\", "/").split("/")]
        parts = [part for part in parts if part]
        if not parts or any(part in {".", ".."} for part in parts):
            raise SupabaseStorageError("The media storage path is invalid.")
        return "/".join(parts)

    async def upload(self, path: str, content: bytes, content_type: str) -> None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                f"{self.base_url}/storage/v1/object/{MEDIA_BUCKET}/{self._quoted_path(path)}",
                headers={
                    **self.headers,
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
                content=content,
            )
        if response.is_error:
            raise SupabaseStorageError(
                f"Supabase Storage rejected the upload (HTTP {response.status_code})."
            )

    async def create_signed_url(self, path: str) -> str:
        path = self.normalize_path(path)
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(SIGN_MAX_ATTEMPTS):
            if attempt:
                await asyncio.sleep(SIGN_BACKOFF_SECONDS * 2 ** (attempt - 1))
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                    response = await client.post(
                        f"{self.base_url}/storage/v1/object/sign/{MEDIA_BUCKET}/{self._quoted_path(path)}",
                        headers={**self.headers, "Content-Type": "application/json"},
                        json={"expiresIn": SIGNED_URL_TTL_SECONDS},
                    )
            except httpx.TransportError as exc:
                last_error = exc
                response = None
                continue
            if response.status_code in _RETRYABLE_STATUS:
                continue
            break
        if response is None:
            raise SupabaseStorageError(
                f"Supabase Storage could not be reached to sign the media URL ({type(last_error).__name__})."
            )
        if response.is_error:
            raise SupabaseStorageError(
                f"Supabase Storage could not sign the media URL (HTTP {response.status_code})."
            )
        payload = response.json()
        signed_url = payload.get("signedURL") if isinstance(payload, dict) else None
        if not isinstance(signed_url, str) or not signed_url:
            raise SupabaseStorageError("Supabase Storage returned an invalid signed URL.")
        if signed_url.startswith("/storage/v1/"):
            return f"{self.base_url}{signed_url}"
        if signed_url.startswith("/"):
            return f"{self.base_url}/storage/v1{signed_url}"
        parsed = urlsplit(signed_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise SupabaseStorageError("Supabase Storage returned an unsafe signed URL.")
        return signed_url

    async def delete(self, path: str) -> None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.delete(
                f"{self.base_url}/storage/v1/object/{MEDIA_BUCKET}",
                headers={**self.headers, "Content-Type": "application/json"},
                json={"prefixes": [path]},
            )
        if response.is_error:
            raise SupabaseStorageError(
                f"Supabase Storage could not delete the media (HTTP {response.status_code})."
            )
