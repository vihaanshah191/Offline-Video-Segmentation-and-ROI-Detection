"""Analytics, timeline and heatmap Pydantic schemas."""
from __future__ import annotations

from pydantic import BaseModel


class TimelinePoint(BaseModel):
    """One sampled point along the video timeline."""

    time: float  # seconds
    motion_score: float  # 0..1
    active: bool  # whether motion exceeded threshold
    objects: list[str] = []  # object labels detected near this point


class TimelineResponse(BaseModel):
    """Full timeline payload for the dashboard."""

    video_id: int
    duration: float
    fps: float
    sample_interval: float  # seconds between points
    points: list[TimelinePoint]
    event_markers: list[dict] = []  # {start, end, id, objects}


class HeatmapResponse(BaseModel):
    """Metadata about a generated heatmap image."""

    video_id: int
    heatmap_url: str | None
    width: int
    height: int
    generated: bool


class ObjectCount(BaseModel):
    """Aggregate count for a single object label."""

    label: str
    count: int
    prohibited: bool


class VideoAnalytics(BaseModel):
    """Aggregate analytics for a single video's dashboard."""

    video_id: int
    total_events: int
    total_motion_duration: float  # seconds
    motion_coverage: float  # fraction of the video with motion (0..1)
    average_motion_score: float
    peak_motion_score: float
    peak_activity_time: float  # timestamp (s) of maximum motion
    longest_event_duration: float
    longest_event_id: int | None
    average_event_duration: float  # seconds
    total_roi_area_pixels: int  # sum of every ROI's (w * h) across the video
    top_object: str | None  # most frequently detected label, if any
    total_detections: int
    prohibited_detections: int
    object_counts: list[ObjectCount]
    storage_bytes: int  # on-disk size of the source video file
    compression_ratio: float | None  # estimated raw (uncompressed) / encoded size
