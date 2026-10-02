import asyncio
import hashlib
import time
from collections import deque


class LoginRateLimiter:
    """Process-local login limiter; replace with a shared store when scaling out."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def key(client_host: str, email: str) -> str:
        normalized = f"{client_host.casefold()}:{email.casefold()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def is_limited(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            failures = self._failures.get(key)
            if failures is None:
                return False
            while failures and now - failures[0] >= self.window_seconds:
                failures.popleft()
            if not failures:
                self._failures.pop(key, None)
                return False
            return len(failures) >= self.max_attempts

    async def record_failure(self, key: str) -> None:
        now = time.monotonic()
        async with self._lock:
            failures = self._failures.get(key)
            if failures is None:
                if len(self._failures) >= 10_000:
                    expired_keys = [
                        current_key
                        for current_key, attempts in self._failures.items()
                        if not attempts or now - attempts[-1] >= self.window_seconds
                    ]
                    for expired_key in expired_keys:
                        self._failures.pop(expired_key, None)
                if len(self._failures) >= 10_000:
                    self._failures.pop(next(iter(self._failures)))
                failures = deque()
                self._failures[key] = failures
            while failures and now - failures[0] >= self.window_seconds:
                failures.popleft()
            failures.append(now)

    async def clear(self, key: str) -> None:
        async with self._lock:
            self._failures.pop(key, None)
