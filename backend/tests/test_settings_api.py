"""Tests for the runtime-settings API (the Settings page backend)."""
from __future__ import annotations

from app.core.config import settings as env_settings
from app.models.auth import UserRole
from app.services.auth_service import AuthService
from fastapi.testclient import TestClient

API = "/api"


def test_get_settings_returns_defaults(client: TestClient) -> None:
    resp = client.get(f"{API}/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert "default_motion_algorithm" in body
    assert "motion_threshold" in body
    assert 0.0 <= body["motion_threshold"] <= 1.0


def test_update_settings_partial(client: TestClient) -> None:
    resp = client.put(f"{API}/settings", json={"motion_threshold": 0.25})
    assert resp.status_code == 200
    assert resp.json()["motion_threshold"] == 0.25

    # Untouched fields keep their prior values (partial-update semantics).
    again = client.get(f"{API}/settings").json()
    assert again["motion_threshold"] == 0.25


def test_update_settings_rejects_out_of_range(client: TestClient) -> None:
    resp = client.put(f"{API}/settings", json={"motion_threshold": 5.0})
    assert resp.status_code == 422


def test_reset_settings_restores_env_defaults(client: TestClient) -> None:
    client.put(f"{API}/settings", json={"motion_threshold": 0.9})
    resp = client.post(f"{API}/settings/reset")
    assert resp.status_code == 200
    assert resp.json()["motion_threshold"] == env_settings.motion_threshold


def test_capabilities_endpoint(client: TestClient) -> None:
    resp = client.get(f"{API}/settings/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_backend"] in ("thread", "celery")
    assert isinstance(body["allowed_extensions"], list)
    assert body["auth_enabled"] is False


def test_update_settings_requires_manage_permission_when_auth_enabled(
    client: TestClient, db_session
) -> None:
    original_enabled = env_settings.auth_enabled
    original_secret = env_settings.jwt_secret_key
    env_settings.auth_enabled = True
    env_settings.jwt_secret_key = "test-secret-key-not-for-production-use-only"
    try:
        AuthService(db_session).create_user("settings-admin", "settings-admin-pass-123", UserRole.ADMIN)
        login = client.post(
            f"{API}/auth/login",
            json={"username": "settings-admin", "password": "settings-admin-pass-123"},
        )
        token = login.json()["access_token"]

        ok = client.put(
            f"{API}/settings",
            json={"motion_threshold": 0.3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok.status_code == 200

        anon = client.put(f"{API}/settings", json={"motion_threshold": 0.3})
        assert anon.status_code == 401
    finally:
        env_settings.auth_enabled = original_enabled
        env_settings.jwt_secret_key = original_secret
