"""Runtime-editable analysis defaults (the Settings page's backing store).

Most configuration in this project is env-var based (``app/core/config.py``)
and intentionally requires a restart to change — that's appropriate for
deployment-level concerns (database URL, storage paths, CORS). This table
holds the smaller subset of *analysis-tuning* defaults a user reasonably
wants to change at runtime from a Settings page without redeploying:
motion algorithm, sensitivity, YOLO confidence, noise filtering, and
object-detection on/off.

Deliberately a **single row** (id is always 1) rather than a key-value table:
every field is typed and CHECK-constrained the same way the rest of the
schema is, which a generic KV table would lose. New analysis runs read this
row (falling back to the env-var defaults in ``Settings`` for any field that
has never been set — see ``RuntimeConfigService``); it never affects a run
already in progress.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RuntimeConfig(Base):
    """Singleton row of user-editable analysis defaults."""

    __tablename__ = "runtime_config"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_runtime_config_singleton"),
        CheckConstraint(
            "motion_threshold >= 0 AND motion_threshold <= 1", name="ck_runtime_motion_threshold_range"
        ),
        CheckConstraint("yolo_confidence >= 0 AND yolo_confidence <= 1", name="ck_runtime_yolo_conf_range"),
        CheckConstraint("min_motion_area >= 1", name="ck_runtime_min_area_positive"),
        CheckConstraint("frame_sample_step >= 1", name="ck_runtime_sample_step_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_motion_algorithm: Mapped[str] = mapped_column(String(20), default="auto")
    motion_threshold: Mapped[float] = mapped_column(Float, default=0.012)
    min_motion_area: Mapped[int] = mapped_column(Integer, default=800)
    frame_sample_step: Mapped[int] = mapped_column(Integer, default=2)
    yolo_confidence: Mapped[float] = mapped_column(Float, default=0.35)
    enable_object_detection: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
