"""Per-client request limits for the endpoints that cost money or invite guessing.

The counter lives in this process. That is the right trade for a single free Render instance:
no Redis to run, no network hop on the hot path. Running more than one instance would need a
shared store, because each process would otherwise allow the full quota on its own.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

# Stops the table growing without bound when a lot of one-off addresses pass through.
MAX_TRACKED_CLIENTS = 20_000


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, bucket: str, client: str, limit: int, window: int) -> float | None:
        """Record a request. Returns None if allowed, else the seconds until one frees up."""
        now = time.monotonic()
        hits = self._hits[(bucket, client)]

        cutoff = now - window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            return window - (now - hits[0])

        hits.append(now)
        if len(self._hits) > MAX_TRACKED_CLIENTS:
            self._prune()
        return None

    def _prune(self) -> None:
        for key in [key for key, hits in self._hits.items() if not hits]:
            del self._hits[key]

    def clear(self) -> None:
        self._hits.clear()


_window = SlidingWindow()


def reset_rate_limits() -> None:
    """Used by the tests so one test's requests cannot exhaust another's allowance."""
    _window.clear()


def client_key(request: Request) -> str:
    # Render terminates TLS at its proxy, so the socket address is the proxy's. The first
    # entry of X-Forwarded-For is the caller. It is spoofable, which only matters here in
    # that a determined abuser can rotate the header; the limit still stops casual scripts.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, limit: int, window_seconds: int):
    """Build a dependency that allows `limit` requests per `window_seconds` per caller."""

    def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return

        retry_after = _window.check(bucket, client_key(request), limit, window_seconds)
        if retry_after is None:
            return

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="That is a lot of requests in a short time. Please wait a moment.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    return dependency
