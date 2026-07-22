"""Authentication Pydantic schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.auth import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    username: str
    role: UserRole


class CurrentUserResponse(BaseModel):
    username: str | None
    role: UserRole
    auth_enabled: bool


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    username: str | None
    action: str
    resource: str | None
    ip_address: str | None
    detail: str | None
    success: bool
