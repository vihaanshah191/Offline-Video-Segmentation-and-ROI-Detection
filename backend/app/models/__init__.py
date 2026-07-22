"""ORM models package."""
from app.models.auth import ROLE_PERMISSIONS, AuditLog, User, UserRole
from app.models.runtime_config import RuntimeConfig
from app.models.video import (
    ROI,
    Detection,
    Event,
    Video,
    VideoStatus,
)

__all__ = [
    "ROI",
    "ROLE_PERMISSIONS",
    "AuditLog",
    "Detection",
    "Event",
    "RuntimeConfig",
    "User",
    "UserRole",
    "Video",
    "VideoStatus",
]
