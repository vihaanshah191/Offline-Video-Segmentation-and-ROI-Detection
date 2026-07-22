"""Password hashing and JWT (HS256) issuance/verification.

Password hashing uses ``bcrypt`` directly (not ``passlib``, which is
unmaintained and incompatible with modern bcrypt releases).

JWT is a small, self-contained HS256 (HMAC-SHA256) implementation using only
the standard library, rather than a third-party JWT package. This is a
deliberate choice, not a shortcut: this project only ever needs symmetric
signing with one shared secret (no key rotation, no JWKS, no asymmetric
algorithms), which is exactly what HS256 is, and HS256 is simple enough to
implement correctly in ~40 lines — RFC 7519 (JWT) + RFC 7515 (JWS) reduced to
the one concrete case this app uses. This also sidesteps a real-world
packaging hazard: several JWT libraries (including PyJWT) probe for the
`cryptography` package at import time to enable RSA/EC algorithms this app
never uses, and a broken/mismatched system install of `cryptography` (a
compiled Rust extension) can crash that probe with an unrecoverable panic
before this code ever runs — unrelated to anything this module does, but a
real failure mode of depending on that import path. Constant-time comparison
(`hmac.compare_digest`) is used for signature verification, matching the
security property any correct JWT library must provide.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import bcrypt

from app.core.config import settings

# bcrypt has a hard 72-byte input limit; truncate defensively rather than
# raising on an unusually long passphrase.
_MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    """Hash a password for storage."""
    truncated = plain_password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a password against its stored hash. Never raises on bad input."""
    try:
        truncated = plain_password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
        return bcrypt.checkpw(truncated, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class InvalidTokenError(Exception):
    """Raised internally for any malformed/invalid/expired token; always
    caught within this module — callers only ever see None from decode."""


def _sign(signing_input: bytes) -> bytes:
    return hmac.new(settings.jwt_secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()


def create_access_token(username: str, role: str) -> tuple[str, datetime]:
    """Issue a signed HS256 JWT for ``username``. Returns (token, expiry).

    The expiry (``jwt_expiry_minutes``) is the system's "session timeout" —
    a client must re-authenticate once the token expires; there is no
    server-side session store to invalidate, keeping the API stateless.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": username, "role": role, "exp": int(expires_at.timestamp())}

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature_b64 = _b64url_encode(_sign(signing_input))

    return f"{header_b64}.{payload_b64}.{signature_b64}", expires_at


def decode_access_token(token: str) -> dict | None:
    """Decode and validate an HS256 JWT. Returns the payload, or None if
    malformed, tampered with, or expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidTokenError("malformed token")
        header_b64, payload_b64, signature_b64 = parts

        expected_signature = _sign(f"{header_b64}.{payload_b64}".encode("ascii"))
        actual_signature = _b64url_decode(signature_b64)
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise InvalidTokenError("signature mismatch")

        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            raise InvalidTokenError("unsupported algorithm")

        payload = json.loads(_b64url_decode(payload_b64))
        exp = payload.get("exp")
        if exp is None or datetime.now(timezone.utc).timestamp() > exp:
            raise InvalidTokenError("expired")

        return payload
    except (InvalidTokenError, ValueError, KeyError, TypeError, UnicodeDecodeError):
        return None
