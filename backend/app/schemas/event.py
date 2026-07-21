"""Event, ROI and Detection Pydantic schemas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
    rois: list[ROIRead] = []
    detections: list[DetectionRead] = []

    @property
    def object_list(self) -> list[str]:
        return [o for o in self.objects.split(",") if o]
