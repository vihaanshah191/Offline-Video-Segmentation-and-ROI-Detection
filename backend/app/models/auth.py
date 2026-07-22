"""Authentication, authorization and audit-log ORM models.

Kept in a separate module from ``video.py`` (domain data) since these are a
cross-cutting concern layered on top of the core pipeline, not part of the
video-analysis domain model itself. Gated behind ``settings.auth_enabled``
(default ``False``) so the existing unauthenticated API contract — and the
existing test suite / demo flow — is completely unaffected unless an
operator explicitly opts in. See ``SYSTEM_DESIGN.md`` for the rationale.
"""
from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserRole(str, enum.Enum):
    """The three roles requested for this system.

    * ``ADMIN`` — full access: manage users, view audit log, everything below.
    * ``INVESTIGATOR`` — upload, analyze, delete, export; the primary
      day-to-day role for someone reviewing footage.
    * ``VIEWER`` — read-only: view videos, events, analytics, download
      reports/clips, but cannot upload, analyze or delete.
    """

    ADMIN = "admin"
    INVESTIGATOR = "investigator"
    VIEWER = "viewer"


# Permission matrix: which roles may perform which mutating action. Kept as a
# plain module-level constant (not a DB table) since it encodes fixed
# application policy, not configurable data.
_WRITE_ACTIONS = {"upload", "analyze", "delete", "cancel"}
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.ADMIN: _WRITE_ACTIONS | {"manage_users", "view_audit_log"},
    UserRole.INVESTIGATOR: set(_WRITE_ACTIONS),
    UserRole.VIEWER: set(),
}


class User(Base):
    """An application user (only meaningful when ``AUTH_ENABLED=true``)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20), nullable=False, default=UserRole.VIEWER
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def has_permission(self, action: str) -> bool:
        return action in ROLE_PERMISSIONS.get(self.role, set())


class AuditLog(Base):
    """An immutable record of a security-relevant action.

    Written for authentication events and every mutating video action
    (upload/analyze/delete) when auth is enabled; also written (with
    ``username=None``) for the same actions when auth is disabled, so the
    log is still useful in the default single-operator deployment.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(
            "action IN ('login', 'login_failed', 'logout', 'upload', 'analyze', 'delete', "
            "'settings_update', 'cancel')",
            name="ck_audit_log_action_enum",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(default=True)
