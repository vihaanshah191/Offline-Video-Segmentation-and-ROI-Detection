"""Tests for JWT authentication, RBAC and the audit log.

Auth is disabled by default (``AUTH_ENABLED=false``) for the whole test
suite, so most other tests exercise the "auth off" no-op path implicitly.
This file explicitly toggles ``settings.auth_enabled`` (a plain mutable
attribute on the shared ``Settings`` singleton) to also exercise the "auth
on" path, then restores it so later tests aren't affected.
"""
from __future__ import annotations

import pytest
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.auth import User, UserRole
from app.services.auth_service import AuthService
from fastapi.testclient import TestClient
from sqlalchemy import func, select

API = "/api"


@pytest.fixture
def auth_enabled(db_session):
    """Enable auth for the duration of a test, seed an admin, then restore.

    Uses ``create_user`` directly rather than ``ensure_seed_admin``:
    ``ensure_seed_admin`` only acts on a *completely empty* users table (by
    design — see its docstring), which makes it order-dependent across test
    files that share one real, non-rolled-back database. Creating (or
    reusing) a specifically-named admin here keeps this fixture correct
    regardless of what other tests ran first.
    """
    original_enabled = settings.auth_enabled
    original_secret = settings.jwt_secret_key
    settings.auth_enabled = True
    settings.jwt_secret_key = "test-secret-key-not-for-production-use-only"
    auth_service = AuthService(db_session)
    if auth_service.get_by_username("admin") is None:
        auth_service.create_user("admin", "s3cur3-test-password", UserRole.ADMIN)
    try:
        yield
    finally:
        settings.auth_enabled = original_enabled
        settings.jwt_secret_key = original_secret


# --------------------------------------------------------------------------- unit
def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_password_hash_never_raises_on_garbage_input() -> None:
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


def test_jwt_roundtrip() -> None:
    token, expires_at = create_access_token("alice", "investigator")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "alice"
    assert payload["role"] == "investigator"
    assert expires_at is not None


def test_jwt_rejects_tampered_signature() -> None:
    token, _ = create_access_token("alice", "investigator")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}xx"
    assert decode_access_token(tampered) is None


def test_jwt_rejects_malformed_token() -> None:
    assert decode_access_token("not-a-jwt") is None
    assert decode_access_token("") is None


# ------------------------------------------------------------------- auth disabled
def test_login_rejected_when_auth_disabled(client: TestClient) -> None:
    resp = client.post(f"{API}/auth/login", json={"username": "admin", "password": "x"})
    assert resp.status_code == 400


def test_me_reports_anonymous_admin_when_auth_disabled(client: TestClient) -> None:
    resp = client.get(f"{API}/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_enabled"] is False
    assert body["username"] is None
    assert body["role"] == "admin"


def test_audit_log_readable_without_token_when_auth_disabled(client: TestClient) -> None:
    resp = client.get(f"{API}/auth/audit-log")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# -------------------------------------------------------------------- auth enabled
def test_login_success_issues_token(client: TestClient, auth_enabled) -> None:
    resp = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "s3cur3-test-password"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["username"] == "admin"
    assert body["role"] == "admin"
    assert body["access_token"]


def test_login_wrong_password_rejected(client: TestClient, auth_enabled) -> None:
    resp = client.post(f"{API}/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user_rejected(client: TestClient, auth_enabled) -> None:
    resp = client.post(f"{API}/auth/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 401


def test_protected_route_requires_token_when_auth_enabled(client: TestClient, auth_enabled) -> None:
    resp = client.get(f"{API}/auth/audit-log")
    assert resp.status_code == 401


def test_protected_route_accepts_valid_token(client: TestClient, auth_enabled) -> None:
    login = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "s3cur3-test-password"}
    )
    token = login.json()["access_token"]
    resp = client.get(f"{API}/auth/audit-log", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_upload_requires_permission_when_auth_enabled(client: TestClient, auth_enabled) -> None:
    resp = client.post(f"{API}/upload", files={"file": ("x.mp4", b"junk", "video/mp4")})
    assert resp.status_code == 401


def test_viewer_role_cannot_upload(client: TestClient, auth_enabled, db_session) -> None:
    AuthService(db_session).create_user("viewer1", "viewer-password-123", UserRole.VIEWER)
    login = client.post(f"{API}/auth/login", json={"username": "viewer1", "password": "viewer-password-123"})
    token = login.json()["access_token"]

    resp = client.post(
        f"{API}/upload",
        files={"file": ("x.mp4", b"junk", "video/mp4")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_investigator_role_can_upload_but_not_manage_settings(
    client: TestClient, auth_enabled, db_session, sample_video_path
) -> None:
    AuthService(db_session).create_user("inv1", "investigator-password-123", UserRole.INVESTIGATOR)
    login = client.post(
        f"{API}/auth/login", json={"username": "inv1", "password": "investigator-password-123"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with sample_video_path.open("rb") as fh:
        upload = client.post(
            f"{API}/upload", files={"file": ("sample.mp4", fh, "video/mp4")}, headers=headers
        )
    assert upload.status_code == 201

    settings_resp = client.put(f"{API}/settings", json={"motion_threshold": 5.0}, headers=headers)
    assert settings_resp.status_code == 403


def test_deactivated_user_token_rejected(client: TestClient, auth_enabled, db_session) -> None:
    user = AuthService(db_session).create_user("temp1", "temp-password-123", UserRole.VIEWER)
    login = client.post(f"{API}/auth/login", json={"username": "temp1", "password": "temp-password-123"})
    token = login.json()["access_token"]

    user.is_active = False
    db_session.commit()

    resp = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_seed_admin_only_seeds_a_completely_empty_table(db_session) -> None:
    """``ensure_seed_admin`` must never touch the table once *any* user
    exists, so an operator's changed admin password is never reset on
    restart. Written order-independently (other tests in this module/session
    share the same real DB and may have already created users) by branching
    on the table's actual state rather than assuming it's empty."""
    service = AuthService(db_session)
    count_before = db_session.execute(select(func.count(User.id))).scalar_one()

    service.ensure_seed_admin("order-independent-seed-admin", "irrelevant-password-123")

    count_after = db_session.execute(select(func.count(User.id))).scalar_one()
    if count_before > 0:
        assert count_after == count_before
        assert service.get_by_username("order-independent-seed-admin") is None
    else:
        assert count_after == count_before + 1
        assert service.get_by_username("order-independent-seed-admin") is not None
