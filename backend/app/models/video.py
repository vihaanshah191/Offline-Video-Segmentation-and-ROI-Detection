"""SQLAlchemy ORM models: Video, Event, ROI and Detection.

The schema mirrors the AI pipeline output:

* A :class:`Video` is uploaded and analysed.
* Analysis produces :class:`Event` rows (motion-activity segments / clips).
* Each event owns one or more :class:`ROI` boxes (merged motion regions) and
  zero or more :class:`Detection` rows (YOLO object detections).

Indexing strategy: every column that appears in a ``WHERE``, ``ORDER BY`` or
sort-by clause anywhere in the API (see ``app/api/routes/*.py``) is indexed.
CHECK constraints encode the numeric invariants the application already
enforces in Python (progress 0..100, non-negative durations, confidence
0..1, ...) at the database level too, so a bug in a future code path (or a
raw SQL script) can't silently write nonsensical rows.
"""
from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class VideoStatus(str, enum.Enum):
    """Lifecycle status of an uploaded video."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Video(Base):
    """An uploaded recording and its extracted metadata / analysis state."""

    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_videos_progress_range"),
        CheckConstraint("duration >= 0", name="ck_videos_duration_nonneg"),
        CheckConstraint("fps >= 0", name="ck_videos_fps_nonneg"),
        CheckConstraint("width >= 0", name="ck_videos_width_nonneg"),
        CheckConstraint("height >= 0", name="ck_videos_height_nonneg"),
        CheckConstraint("frame_count >= 0", name="ck_videos_frame_count_nonneg"),
        CheckConstraint("size_bytes >= 0", name="ck_videos_size_bytes_nonneg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)

    fps: Mapped[float] = mapped_column(Float, default=0.0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)  # seconds
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False, length=20),
        default=VideoStatus.UPLOADED,
        nullable=False,
        index=True,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100
    status_message: Mapped[str] = mapped_column(String(512), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    motion_algorithm: Mapped[str | None] = mapped_column(String(32), nullable=True)
    heatmap_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # JSON-encoded performance/processing statistics from the most recent
    # analysis run (frame throughput, cache hit rate, resolved algorithm,
    # per-stage timings, ...). Stored as text (not a dedicated JSON column
    # type) for SQLite/Postgres portability; parsed on the way out by the API
    # layer.
    processing_stats: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    events: Mapped[list[Event]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="Event.start_time",
    )

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"


class Event(Base):
    """A motion-activity segment (clip) discovered during analysis."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("end_time >= start_time", name="ck_events_time_order"),
        CheckConstraint("duration >= 0", name="ck_events_duration_nonneg"),
        CheckConstraint(
            "motion_score >= 0 AND motion_score <= 1", name="ck_events_motion_score_range"
        ),
        CheckConstraint(
            "peak_motion_score >= 0 AND peak_motion_score <= 1",
            name="ck_events_peak_motion_score_range",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_events_confidence_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    start_time: Mapped[float] = mapped_column(Float, nullable=False, index=True)  # seconds
    end_time: Mapped[float] = mapped_column(Float, nullable=False)  # seconds
    duration: Mapped[float] = mapped_column(Float, nullable=False, index=True)  # seconds

    motion_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)  # avg 0..1
    peak_motion_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, index=True)  # 0..1

    # Comma-separated summary of detected object labels for quick search.
    objects: Mapped[str] = mapped_column(String(512), default="")

    clip_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    video: Mapped[Video] = relationship(back_populates="events")
    rois: Mapped[list[ROI]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    detections: Mapped[list[Detection]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class ROI(Base):
    """A merged region-of-interest bounding box belonging to an event."""

    __tablename__ = "rois"
    __table_args__ = (
        CheckConstraint("w > 0", name="ck_rois_width_positive"),
        CheckConstraint("h > 0", name="ck_rois_height_positive"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_rois_confidence_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Absolute pixel coordinates in the source video frame.
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    w: Mapped[int] = mapped_column(Integer, nullable=False)
    h: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    event: Mapped[Event] = relationship(back_populates="rois")


class Detection(Base):
    """A single YOLO object detection tied to an event."""

    __tablename__ = "detections"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_detections_confidence_range"),
        CheckConstraint("w >= 0", name="ck_detections_width_nonneg"),
        CheckConstraint("h >= 0", name="ck_detections_height_nonneg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )

    label: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[float] = mapped_column(Float, default=0.0)  # seconds
    prohibited: Mapped[bool] = mapped_column(default=False)
    # True when ``label`` is only a heuristic proxy for a prohibited concept
    # COCO has no direct class for (e.g. "book" standing in for "possible
    # notes"), rather than a direct, reliable detection. See
    # app/services/object_detection.py module docstring for the full
    # rationale — surfaced so the UI can word findings appropriately instead
    # of overclaiming certainty.
    heuristic: Mapped[bool] = mapped_column(default=False)

    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    w: Mapped[int] = mapped_column(Integer, default=0)
    h: Mapped[int] = mapped_column(Integer, default=0)

    event: Mapped[Event] = relationship(back_populates="detections")
