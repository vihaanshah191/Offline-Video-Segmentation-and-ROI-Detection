"""Best-effort, in-process rate limiting middleware.

Implements a per-client-IP sliding-window limiter with no external
dependencies (no Redis required), which keeps the single-node / thread-worker
deployment story (the project's default) dependency-free.

Limitation (documented, not hidden): because state is held in process memory,
this limiter is **not** shared across multiple Uvicorn/Gunicorn workers or
multiple replicas. For a horizontally-scaled, multi-worker production
deployment, replace this with a distributed limiter backed by Redis (the
project already depends on Redis when ``TASK_BACKEND=celery``, so that
infrastructure is available to extend). See ``docs/SYSTEM_DESIGN.md``.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings as global_settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_WINDOW_SECONDS = 60.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by client IP + route group.

    Route limits are read from ``settings`` at construction time (not at
    module-import time) and can also be overridden explicitly — this keeps
    the middleware unit-testable with custom limits without needing to
    manipulate environment variables and re-import the module.
    """

    def __init__(self, app, *, route_limits: tuple[tuple[str, int], ...] | None = None) -> None:
        super().__init__(app)
        s = global_settings
        self._route_limits: tuple[tuple[str, int], ...] = route_limits or (
            (f"{s.api_prefix}/upload", s.upload_rate_limit_per_minute),
            (f"{s.api_prefix}/analyze", s.analyze_rate_limit_per_minute),
        )
        self._default_limit = s.default_rate_limit_per_minute
        # key -> deque of monotonic timestamps within the current window.
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _limit_for(self, path: str) -> tuple[str, int]:
        for prefix, limit in self._route_limits:
            if path.startswith(prefix):
                return prefix, limit
        return "default", self._default_limit

    def _client_key(self, request: Request) -> str:
        # Respect a trusted proxy header if present (e.g. behind nginx), else
        # fall back to the direct peer address.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = request.client
        return client.host if client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        group, limit = self._limit_for(request.url.path)
        client_ip = self._client_key(request)
        key = f"{client_ip}:{group}"

        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > _WINDOW_SECONDS:
            window.popleft()

        if len(window) >= limit:
            retry_after = max(1, int(_WINDOW_SECONDS - (now - window[0])))
            logger.warning(
                "Rate limit exceeded for %s on %s (%d/%d per minute)",
                client_ip,
                group,
                len(window),
                limit,
                extra={"client_ip": client_ip, "route_group": group, "limit": limit},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded ({limit} requests/minute for this endpoint). "
                    f"Retry after {retry_after}s.",
                    "error_type": "rate_limited",
                },
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
        return await call_next(request)
