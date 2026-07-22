"""User authentication and audit-log service."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.security import hash_password, verify_password
from app.models.auth import AuditLog, User, UserRole

logger = get_logger(__name__)


class AuthService:
    """User lookup/authentication and audit-log writes."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_username(self, username: str) -> User | None:
        return self.db.execute(select(User).where(User.username == username)).scalar_one_or_none()

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the user if credentials are valid and the account is active."""
        user = self.get_by_username(username)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        user.last_login_at = datetime.now(UTC)
        self.db.commit()
        return user

    def create_user(self, username: str, password: str, role: UserRole) -> User:
        user = User(username=username, password_hash=hash_password(password), role=role)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def ensure_seed_admin(self, admin_username: str, admin_password: str) -> None:
        """Create the seed admin account if no users exist yet.

        Idempotent and safe to call on every startup: only acts when the
        `users` table is completely empty, so it never resets an operator's
        subsequently-changed admin password.
        """
        has_any_user = self.db.execute(select(User.id).limit(1)).first() is not None
        if has_any_user:
            return
        self.create_user(admin_username, admin_password, UserRole.ADMIN)
        logger.info("Seeded initial admin account '%s'", admin_username)

    def record_audit(
        self,
        *,
        action: str,
        username: str | None,
        resource: str | None = None,
        ip_address: str | None = None,
        detail: str | None = None,
        success: bool = True,
    ) -> None:
        """Write an audit-log entry. Never raises — audit logging must not
        be able to break the action it's recording."""
        try:
            self.db.add(
                AuditLog(
                    username=username,
                    action=action,
                    resource=resource,
                    ip_address=ip_address,
                    detail=detail,
                    success=success,
                )
            )
            self.db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write audit log entry for action=%s", action)
            self.db.rollback()

    def list_audit_log(self, *, limit: int = 200, offset: int = 0) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())
