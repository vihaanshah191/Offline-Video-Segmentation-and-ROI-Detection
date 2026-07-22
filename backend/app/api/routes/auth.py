"""Authentication endpoints: login, current-user, audit log.

All routes here work regardless of ``AUTH_ENABLED``: with auth disabled,
``/auth/me`` reports the anonymous full-access principal and ``/auth/login``
is rejected (there is nothing to authenticate against); the audit log is
still readable (and still being written to — see ``AuthService.record_audit``
call sites) even when auth itself is off, since it's a useful record in the
default single-operator deployment too.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.auth_deps import Principal, get_current_principal, require_permission
from app.core.config import settings
from app.core.security import create_access_token
from app.database.session import get_db
from app.schemas.auth import AuditLogEntry, CurrentUserResponse, LoginRequest, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Authenticate and obtain a bearer token")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled on this deployment (AUTH_ENABLED=false).",
        )

    auth_service = AuthService(db)
    user = auth_service.authenticate(payload.username, payload.password)
    client_ip = request.client.host if request.client else None

    if user is None:
        auth_service.record_audit(
            action="login_failed", username=payload.username, ip_address=client_ip, success=False
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")

    token, expires_at = create_access_token(user.username, user.role.value)
    auth_service.record_audit(action="login", username=user.username, ip_address=client_ip)
    return TokenResponse(
        access_token=token, expires_at=expires_at, username=user.username, role=user.role
    )


@router.get("/me", response_model=CurrentUserResponse, summary="Report the current principal")
def me(principal: Principal = Depends(get_current_principal)) -> CurrentUserResponse:
    return CurrentUserResponse(
        username=principal.username, role=principal.role, auth_enabled=settings.auth_enabled
    )


@router.get(
    "/audit-log",
    response_model=list[AuditLogEntry],
    summary="List recent audit-log entries (admin only when auth is enabled)",
)
def list_audit_log(
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_permission("view_audit_log")),
    limit: int = 200,
    offset: int = 0,
) -> list[AuditLogEntry]:
    # require_permission() is already a no-op (always passes) when auth is
    # disabled, since get_current_principal() returns a full-access anonymous
    # principal in that mode — no separate conditional needed here.
    entries = AuthService(db).list_audit_log(limit=min(limit, 1000), offset=max(offset, 0))
    return [AuditLogEntry.model_validate(e) for e in entries]
