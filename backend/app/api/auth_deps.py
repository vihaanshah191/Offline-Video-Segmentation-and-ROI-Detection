"""Authentication/authorization FastAPI dependencies.

When ``settings.auth_enabled`` is ``False`` (the default), every dependency
here is a no-op that returns a synthetic full-access principal — this keeps
the entire pre-existing unauthenticated API contract, test suite and demo
flow completely unaffected. When enabled, a valid Bearer JWT is required on
protected routes and role permissions
(see :data:`app.models.auth.ROLE_PERMISSIONS`) are enforced.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.auth import ROLE_PERMISSIONS, UserRole
from app.services.auth_service import AuthService

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class Principal:
    """The authenticated (or anonymous, when auth is disabled) request actor."""

    username: str | None
    role: UserRole

    def has_permission(self, action: str) -> bool:
        return action in ROLE_PERMISSIONS.get(self.role, set())


# Full-access principal used for every request when auth is disabled, so
# permission checks are always a no-op in that (default) mode.
_ANONYMOUS = Principal(username=None, role=UserRole.ADMIN)


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Principal:
    """Resolve the current request's principal.

    Returns the anonymous full-access principal when auth is disabled;
    otherwise validates the Bearer token and the referenced account.
    """
    if not settings.auth_enabled:
        return _ANONYMOUS

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token."
        )

    username = payload.get("sub")
    try:
        UserRole(payload.get("role"))  # validate the claim; the DB role below is authoritative
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload."
        ) from None

    # A JWT alone can't reflect an account being deactivated after issuance
    # (there's no server-side session store to invalidate) — re-check.
    user = AuthService(db).get_by_username(username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account no longer active."
        )

    return Principal(username=user.username, role=user.role)


def require_permission(action: str):
    """Dependency factory: 403s unless the current principal may perform ``action``.

    A no-op check (always passes) when auth is disabled, since
    ``get_current_principal`` returns the full-access anonymous principal.
    """

    def _check(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.has_permission(action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{principal.role.value}' is not permitted to perform '{action}'.",
            )
        return principal

    return _check
