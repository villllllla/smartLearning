"""Per-IP rate limiting for public deployments.

Deliberately in-process (a dict of sliding windows) rather than Redis-backed:
this app runs as a single uvicorn container against a single SQLite file, so
there is no second process to share state with. If it ever scales out, this
must move to a shared store — the limits become per-replica otherwise.

Two buckets, because the two threats have very different shapes:

``auth``   credential stuffing against ``/api/auth/login``. Low limit — a human
           logs in a handful of times a day; a script tries thousands.
``write``  any mutating ``/api/`` call. The scarce resource here isn't CPU or
           bandwidth, it's the user's *LLM spend*: one POST to a generation or
           chat endpoint costs real money. Generous enough that normal use never
           notices, low enough that a scripted loop can't drain the account.

Read-only requests are not limited: they're cheap and limiting them would break
normal browsing well before it inconveniences an attacker.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Verified by its own token + a fail-closed open_id allowlist (see
# integrations/feishu/router.py), and bursty by nature — Feishu retries
# deliveries. Limiting it here would only drop legitimate events.
_EXEMPT_PREFIXES = ("/api/integrations/feishu", "/api/health")

_AUTH_PREFIXES = ("/api/auth/login", "/api/auth/register")


def client_ip(request: Request, *, trust_proxy: bool) -> str:
    """Best-effort client address.

    With ``trust_proxy`` off we use the socket peer — correct when the app is
    exposed directly, and unspoofable. With it on we read forwarding headers,
    which is only safe because a trusted proxy is known to rewrite them:

    - ``CF-Connecting-IP`` wins when present (Cloudflare Tunnel / proxy sets it
      and strips client-supplied copies).
    - Otherwise the *last* ``X-Forwarded-For`` entry, which is the peer our own
      nginx observed (``$proxy_add_x_forwarded_for`` appends it). Earlier
      entries are attacker-controlled and must never be trusted.
    """
    if trust_proxy:
        cf = (request.headers.get("cf-connecting-ip") or "").strip()
        if cf:
            return cf
        xff = request.headers.get("x-forwarded-for") or ""
        if xff:
            last = xff.split(",")[-1].strip()
            if last:
                return last
    client = request.client
    return client.host if client else "unknown"


class _SlidingWindow:
    """Fixed-capacity sliding window counter per key."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._last_sweep = time.monotonic()

    def check(self, key: str, now: float) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until retry."""
        with self._lock:
            self._sweep(now)
            q = self._hits.get(key)
            if q is None:
                q = self._hits[key] = deque()
            cutoff = now - self.window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                # Oldest hit leaving the window is when a slot frees up.
                return max(1.0, q[0] + self.window - now)
            q.append(now)
            return None

    def _sweep(self, now: float) -> None:
        """Drop fully-expired keys so idle clients don't leak memory."""
        if now - self._last_sweep < self.window:
            return
        self._last_sweep = now
        cutoff = now - self.window
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]:
            del self._hits[key]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,  # noqa: ANN001
        *,
        auth_limit: int,
        auth_window_seconds: int,
        write_limit: int,
        write_window_seconds: int,
        trust_proxy: bool,
    ) -> None:
        super().__init__(app)
        self._auth = _SlidingWindow(auth_limit, auth_window_seconds)
        self._write = _SlidingWindow(write_limit, write_window_seconds)
        self._trust_proxy = trust_proxy

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        path = request.url.path
        if not path.startswith("/api/") or path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        is_auth = path.startswith(_AUTH_PREFIXES)
        if not is_auth and request.method in _SAFE_METHODS:
            return await call_next(request)

        window = self._auth if is_auth else self._write
        ip = client_ip(request, trust_proxy=self._trust_proxy)
        retry_after = window.check(f"{ip}", time.monotonic())
        if retry_after is None:
            return await call_next(request)

        log.warning(
            "rate limit hit bucket=%s ip=%s path=%s",
            "auth" if is_auth else "write",
            ip,
            path,
        )
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"},
            headers={"Retry-After": str(int(retry_after))},
        )
