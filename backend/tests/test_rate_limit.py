"""Tests for the in-process sliding-window rate limiter.

Builds a minimal Starlette app with the middleware constructed with injected
(small, deterministic) limits, independent of the shared test-session app and
its ``RATE_LIMIT_ENABLED=false`` setting (see conftest.py) — this is exactly
why ``RateLimitMiddleware`` accepts ``route_limits`` at construction time
rather than only reading a module-level constant computed at import time.
"""
from __future__ import annotations

from app.core.rate_limit import RateLimitMiddleware
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _build_app(route_limits: tuple[tuple[str, int], ...]) -> Starlette:
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/api/upload", endpoint, methods=["POST"]),
            Route("/api/other", endpoint, methods=["POST"]),
        ]
    )
    app.add_middleware(RateLimitMiddleware, route_limits=route_limits)
    return app


def test_requests_within_limit_succeed() -> None:
    app = _build_app((("/api/upload", 3),))
    client = TestClient(app)
    for _ in range(3):
        resp = client.post("/api/upload")
        assert resp.status_code == 200


def test_requests_exceeding_limit_are_rejected() -> None:
    app = _build_app((("/api/upload", 3),))
    client = TestClient(app)
    for _ in range(3):
        assert client.post("/api/upload").status_code == 200
    resp = client.post("/api/upload")
    assert resp.status_code == 429
    assert resp.json()["error_type"] == "rate_limited"
    assert "Retry-After" in resp.headers


def test_limit_is_per_route_group() -> None:
    """Hitting the limit on one route group must not affect a different one."""
    app = _build_app((("/api/upload", 1),))
    client = TestClient(app)
    assert client.post("/api/upload").status_code == 200
    assert client.post("/api/upload").status_code == 429
    # /api/other falls back to the default limit, unaffected by /api/upload.
    assert client.post("/api/other").status_code == 200


def test_unmatched_route_uses_default_limit() -> None:
    app = _build_app((("/api/upload", 1),))
    # default_rate_limit_per_minute defaults to 120 in Settings; well above 5.
    client = TestClient(app)
    for _ in range(5):
        assert client.post("/api/other").status_code == 200


def test_different_clients_have_independent_limits() -> None:
    app = _build_app((("/api/upload", 1),))
    client = TestClient(app)
    assert client.post("/api/upload", headers={"x-forwarded-for": "1.1.1.1"}).status_code == 200
    assert client.post("/api/upload", headers={"x-forwarded-for": "1.1.1.1"}).status_code == 429
    # A different client IP has its own independent budget.
    assert client.post("/api/upload", headers={"x-forwarded-for": "2.2.2.2"}).status_code == 200
