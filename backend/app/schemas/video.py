"""Video-related Pydantic schemas."""
from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    processing_stats: dict | None = Field(
        default=None,
        description=(
            "Performance/processing statistics from the most recent analysis run "
            "(frame throughput, resolved motion algorithm, cache hit rate, ...)."
        ),
    )

    @field_validator("processing_stats", mode="before")
    @classmethod
    def _parse_processing_stats(cls, value: object) -> dict | None:
        """Transparently parse the JSON-text ORM column into a dict.

        ``Video.processing_stats`` is stored as a JSON-encoded string (see
        ``app/models/video.py`` for the SQLite/Postgres-portability rationale),
        so ``model_validate(video)`` would otherwise fail validation trying to
        assign a ``str`` to this ``dict | None`` field.
        """
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            # The column is always written as a JSON *object* (see
            # AnalysisPipeline.run); guard defensively against any other
            # JSON type rather than passing it through untyped.
            return parsed if isinstance(parsed, dict) else None
        if value is None or isinstance(value, dict):
            return value
        return None


class AnalyzeRequest(BaseModel):
    """Options for launching an analysis run."""

    motion_algorithm: str = Field(
        default="mog2",
        description=(
            "Motion algorithm: 'mog2', 'frame_diff', 'optical_flow', or 'auto' to "
            "let the pipeline pre-scan the video and pick the best fit automatically."
        ),
        examples=["mog2", "auto"],
    )
    enable_object_detection: bool = Field(
        default=True, description="Run YOLO object detection on motion-segment frames."
    )
    frame_sample_step: int | None = Field(
        default=None, ge=1, le=60, description="Process every Nth frame (higher = faster, coarser)."
    )
    min_motion_area: int | None = Field(
        default=None, ge=1, description="Minimum contour area (px) counted as motion."
    )
    object_detection_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum YOLO confidence to keep a detection (overrides the server default for this run).",
    )
    object_detection_classes: list[str] | None = Field(
        default=None,
        description=(
            "Restrict detections to only these labels (e.g. ['phone', 'bag']). "
            "A further filter on top of the model's own relevant-label set, not a replacement for it."
        ),
    )


class GlobalStats(BaseModel):
    """Aggregate counts across every uploaded video, for the dashboard overview."""

    total_videos: int
    completed_videos: int
    processing_videos: int
    failed_videos: int
    total_events: int
    total_video_duration_seconds: float
    free_disk_bytes: int


class MessageResponse(BaseModel):
    """Generic message envelope."""

    message: str
    detail: str | None = None
