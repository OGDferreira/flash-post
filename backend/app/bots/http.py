"""Shared HTTP client for Telegram/SmokePay; tests swap the transport to fake both.

One pooled ``httpx.AsyncClient`` per event loop keeps TCP/TLS connections alive,
so a bot reply no longer pays a fresh handshake on every API call.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx

_transport: httpx.AsyncBaseTransport | None = None
_shared: httpx.AsyncClient | None = None
_loop: asyncio.AbstractEventLoop | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _transport, _shared
    _transport = transport
    _shared = None  # the next call builds a client on the new transport


def shared() -> httpx.AsyncClient:
    global _shared, _loop
    loop = asyncio.get_running_loop()
    if _shared is None or _shared.is_closed or _loop is not loop:
        _shared = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            transport=_transport,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=40, keepalive_expiry=60.0),
        )
        _loop = loop
    return _shared


class _Session:
    """Per-call view of the shared client with its own timeout."""

    def __init__(self, timeout: float) -> None:
        self._client = shared()
        self._timeout = httpx.Timeout(timeout)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        kwargs.setdefault("timeout", self._timeout)
        return await self._client.request(method, url, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)


@asynccontextmanager
async def client(timeout: float = 20.0) -> AsyncIterator[_Session]:
    yield _Session(timeout)
