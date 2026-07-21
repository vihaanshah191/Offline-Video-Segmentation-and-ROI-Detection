"""Video-related Pydantic schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.video import VideoStatus


class VideoRead(BaseModel):
    """Summary view of a video (list endpoints)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    original_name: str
    fps: float
    duration: float
    width: int
    height: int
    frame_count: int
    size_bytes: int
    status: VideoStatus
    progress: float
    status_message: str
    motion_algorithm: str | None
    created_at: datetime
    updated_at: datetime
    analyzed_at: datetime | None

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"


class VideoDetail(VideoRead):
    """Detailed view including analysis artefacts and derived counts."""

    heatmap_path: str | None = None
    thumbnail_path: str | None = None
    error: str | None = None
    event_count: int = 0


class AnalyzeRequest(BaseModel):
    """Options for launching an analysis run."""

    motion_algorithm: str = Field(
        default="mog2",
        description="Motion algorithm: 'mog2', 'frame_diff' or 'optical_flow'.",
    )
    enable_object_detection: bool = Field(
        default=True, description="Run YOLO object detection on motion frames."
    )
    frame_sample_step: int | None = Field(
        default=None, ge=1, le=30, description="Process every Nth frame."
    )
    min_motion_area: int | None = Field(
        default=None, ge=1, description="Minimum contour area (px) counted as motion."
    )


class MessageResponse(BaseModel):
    """Generic message envelope."""

    message: str
    detail: str | None = None
