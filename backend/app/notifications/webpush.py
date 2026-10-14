"""Minimal Web Push sender (RFC 8030 + RFC 8291 aes128gcm + RFC 8292 VAPID).

Implemented on top of ``cryptography`` (already a dependency) and ``httpx`` so
no new package is needed. Only the server side is implemented: payload
encryption for a browser subscription and the VAPID ``Authorization`` header.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt_value, encrypt_value
from app.models import SystemSetting

logger = logging.getLogger(__name__)

_VAPID_SETTING_KEY = "web_push_vapid_keys"
_RECORD_SIZE = 4096
_MAX_PAYLOAD_BYTES = 3_000

# Push services operated by browser vendors. Subscriptions pointing anywhere
# else are rejected: the server would otherwise POST to attacker-chosen URLs.
_ALLOWED_PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)


class WebPushError(Exception):
    pass


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def is_allowed_push_endpoint(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return False
    if parts.port not in (None, 443):
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_PUSH_HOST_SUFFIXES)


@dataclass(frozen=True)
class VapidKeys:
    private_key: ec.EllipticCurvePrivateKey
    public_key_b64: str


def _public_key_b64(private_key: ec.EllipticCurvePrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64url_encode(raw)


def _private_key_from_raw(raw_b64: str) -> ec.EllipticCurvePrivateKey:
    value = raw_b64.strip()
    if value.startswith("-----BEGIN"):
        key = serialization.load_pem_private_key(value.encode("utf-8"), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise WebPushError("VAPID private key must be an EC P-256 key.")
        return key
    secret = int.from_bytes(b64url_decode(value), "big")
    return ec.derive_private_key(secret, ec.SECP256R1())


def _private_key_to_raw(private_key: ec.EllipticCurvePrivateKey) -> str:
    return b64url_encode(private_key.private_numbers().private_value.to_bytes(32, "big"))


async def get_vapid_keys(db: AsyncSession) -> VapidKeys:
    """VAPID keys from env (VAPID_PRIVATE_KEY) or generated once and stored encrypted."""
    settings = get_settings()
    if settings.vapid_private_key is not None:
        private_key = _private_key_from_raw(settings.vapid_private_key.get_secret_value())
        return VapidKeys(private_key, _public_key_b64(private_key))

    stored = await db.get(SystemSetting, _VAPID_SETTING_KEY)
    if stored is None:
        private_key = ec.generate_private_key(ec.SECP256R1())
        candidate = SystemSetting(
            key=_VAPID_SETTING_KEY,
            value={
                "public_key": _public_key_b64(private_key),
                "encrypted_private_key": encrypt_value(_private_key_to_raw(private_key)),
            },
            is_public=False,
        )
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
        except IntegrityError:
            # Another instance generated the keys first; use theirs.
            stored = await db.get(SystemSetting, _VAPID_SETTING_KEY, populate_existing=True)
            if stored is None:
                raise WebPushError("VAPID keys could not be stored.") from None
        else:
            await db.commit()
            return VapidKeys(private_key, _public_key_b64(private_key))
    value = stored.value if isinstance(stored.value, dict) else {}
    encrypted = value.get("encrypted_private_key")
    if not isinstance(encrypted, str):
        raise WebPushError("Stored VAPID keys are invalid.")
    private_key = _private_key_from_raw(decrypt_value(encrypted))
    return VapidKeys(private_key, _public_key_b64(private_key))


def vapid_authorization(endpoint: str, keys: VapidKeys, subject: str) -> str:
    parts = urlsplit(endpoint)
    audience = f"{parts.scheme}://{parts.netloc}"
    header = b64url_encode(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64url_encode(
        json.dumps(
            {"aud": audience, "exp": int(time.time()) + 12 * 3600, "sub": subject},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{claims}".encode("ascii")
    der_signature = keys.private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    signature = b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={header}.{claims}.{signature}, k={keys.public_key_b64}"


def encrypt_payload(payload: bytes, p256dh_b64: str, auth_b64: str) -> bytes:
    """aes128gcm content encoding for a single record (RFC 8291 §4)."""
    if len(payload) > _MAX_PAYLOAD_BYTES:
        raise WebPushError("Push payload is too large.")
    try:
        user_agent_public = b64url_decode(p256dh_b64)
        auth_secret = b64url_decode(auth_b64)
        ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), user_agent_public)
    except (ValueError, InvalidKey) as exc:
        raise WebPushError("Invalid subscription keys.") from exc
    if len(auth_secret) != 16:
        raise WebPushError("Invalid subscription auth secret.")

    server_private = ec.generate_private_key(ec.SECP256R1())
    server_public = server_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    shared_secret = server_private.exchange(ec.ECDH(), ua_key)
    ikm = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=auth_secret,
        info=b"WebPush: info\x00" + user_agent_public + server_public,
    ).derive(shared_secret)
    salt = os.urandom(16)
    content_key = HKDF(
        algorithm=hashes.SHA256(), length=16, salt=salt, info=b"Content-Encoding: aes128gcm\x00"
    ).derive(ikm)
    nonce = HKDF(
        algorithm=hashes.SHA256(), length=12, salt=salt, info=b"Content-Encoding: nonce\x00"
    ).derive(ikm)
    ciphertext = AESGCM(content_key).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!IB", _RECORD_SIZE, len(server_public)) + server_public
    return header + ciphertext


@dataclass(frozen=True)
class PushResult:
    ok: bool
    gone: bool  # subscription expired/unsubscribed: delete it
    status_code: int | None


async def send_web_push(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: dict,
    keys: VapidKeys,
    ttl_seconds: int = 12 * 3600,
    topic: str | None = None,
) -> PushResult:
    if not is_allowed_push_endpoint(endpoint):
        return PushResult(ok=False, gone=True, status_code=None)
    body = encrypt_payload(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        p256dh,
        auth,
    )
    headers = {
        "Authorization": vapid_authorization(endpoint, keys, get_settings().vapid_subject_value),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(ttl_seconds),
        "Urgency": "normal",
    }
    if topic:
        # Topic lets the push service replace an undelivered older message.
        headers["Topic"] = topic[:32]
    try:
        response = await client.post(endpoint, content=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("Web Push delivery failed (%s).", type(exc).__name__)
        return PushResult(ok=False, gone=False, status_code=None)
    if response.status_code in (200, 201, 202):
        return PushResult(ok=True, gone=False, status_code=response.status_code)
    gone = response.status_code in (404, 410)
    logger.info("Web Push service answered HTTP %s.", response.status_code)
    return PushResult(ok=False, gone=gone, status_code=response.status_code)


async def get_public_vapid_key(db: AsyncSession) -> str:
    return (await get_vapid_keys(db)).public_key_b64


__all__ = [
    "PushResult",
    "VapidKeys",
    "WebPushError",
    "b64url_decode",
    "b64url_encode",
    "encrypt_payload",
    "get_public_vapid_key",
    "get_vapid_keys",
    "is_allowed_push_endpoint",
    "send_web_push",
    "vapid_authorization",
]
