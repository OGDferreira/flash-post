"""Shared HTTP client factory; tests swap the transport to fake Telegram/SmokePay."""

import httpx

_transport: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = transport


def client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout), transport=_transport)
