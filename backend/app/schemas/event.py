"""Event, ROI and Detection Pydantic schemas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings
from app.utils.files import to_relative_url
from app.utils.severity import compute_severity


class ROIRead(BaseModel):
    """A merged motion region bounding box."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    x: int
    y: int
    w: int
    h: int
    confidence: float


class DetectionRead(BaseModel):
    """A YOLO object detection."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    confidence: float
    timestamp: float
    prohibited: bool
    heuristic: bool = Field(
        default=False,
        description=(
            "True when this label is a heuristic proxy for a prohibited concept "
            "the detection model has no direct class for (e.g. 'book' standing in "
            "for 'possible notes'), not a direct, reliable detection."
        ),
    )
    x: int
    y: int
    w: int
    h: int


class EventRead(BaseModel):
    """A motion-activity segment with its ROIs and detections."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    start_time: float
    end_time: float
    duration: float
    motion_score: float
    peak_motion_score: float
    confidence: float
    objects: str
    clip_path: str | None
    thumbnail_path: str | None
    clip_url: str | None = None
    thumbnail_url: str | None = None
    rois: list[ROIRead] = []
    detections: list[DetectionRead] = []
    severity: str = Field(
        default="normal",
        description="'critical' | 'warning' | 'normal', derived from detections + peak motion.",
    )

    @property
    def object_list(self) -> list[str]:
        return [o for o in self.objects.split(",") if o]

    @model_validator(mode="after")
    def _compute_derived_fields(self) -> "EventRead":
        self.severity = compute_severity(self.peak_motion_score, self.detections)
        self.clip_url = to_relative_url(self.clip_path, settings.storage_dir)
        self.thumbnail_url = to_relative_url(self.thumbnail_path, settings.storage_dir)
        return self
