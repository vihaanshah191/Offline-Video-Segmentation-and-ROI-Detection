"""Runtime-settings Pydantic schemas (the Settings page)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RuntimeConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_motion_algorithm: str
    motion_threshold: float
    min_motion_area: int
    frame_sample_step: int
    yolo_confidence: float
    enable_object_detection: bool
    updated_at: datetime
    updated_by: str | None


class RuntimeConfigUpdate(BaseModel):
    """All fields optional: only provided fields are changed."""

    default_motion_algorithm: str | None = Field(
        default=None, description="mog2 | frame_diff | optical_flow | auto"
    )
    motion_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    min_motion_area: int | None = Field(default=None, ge=1)
    frame_sample_step: int | None = Field(default=None, ge=1, le=60)
    yolo_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    enable_object_detection: bool | None = None


class SystemCapabilities(BaseModel):
    """Static-ish capability info shown on the Settings page (read-only there)."""

    yolo_model: str
    yolo_device: str
    task_backend: str
    max_upload_mb: int
    allowed_extensions: list[str]
    auth_enabled: bool
    demo_mode_enabled: bool
