"""Analytics and timeline aggregation services (read models).

Aggregate numeric statistics (counts, sums, averages, group-by label) are
computed with SQL aggregate functions rather than loading full ORM object
graphs into Python and reducing them there — this matters on a multi-hour
recording with hundreds of events and thousands of detections, where the
difference is one small SQL query versus materialising (and selectinload-ing
the ROIs and detections of) every single event row.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.video import Detection, Event, Video
from app.schemas.analytics import (
    ObjectCount,
    TimelinePoint,
    TimelineResponse,
    VideoAnalytics,
)


def _events_for(db: Session, video_id: int) -> list[Event]:
    """Load every event (with ROIs/detections) for a video, ordered by start time.

    Used by the timeline (which needs per-event detail for markers) and by
    CSV/PDF report generation. ``compute_analytics`` deliberately does NOT use
    this — it aggregates in SQL instead, since it only needs scalar summaries.
    """
    stmt = (
        select(Event)
        .where(Event.video_id == video_id)
        .options(selectinload(Event.detections), selectinload(Event.rois))
        .order_by(Event.start_time)
    )
    return list(db.execute(stmt).scalars().all())


def compute_analytics(db: Session, video: Video) -> VideoAnalytics:
    """Aggregate dashboard analytics for a video using SQL-side aggregation."""
    video_id = video.id

    summary = db.execute(
        select(
            func.count(Event.id),
            func.coalesce(func.sum(Event.duration), 0.0),
            func.coalesce(func.avg(Event.motion_score), 0.0),
        ).where(Event.video_id == video_id)
    ).one()
    total_events, total_motion, avg_score = summary

    duration = video.duration or 0.0
    coverage = (total_motion / duration) if duration > 0 else 0.0

    peak_row = db.execute(
        select(Event.id, Event.start_time, Event.peak_motion_score)
        .where(Event.video_id == video_id)
        .order_by(Event.peak_motion_score.desc())
        .limit(1)
    ).first()

    longest_row = db.execute(
        select(Event.id, Event.duration)
        .where(Event.video_id == video_id)
        .order_by(Event.duration.desc())
        .limit(1)
    ).first()

    # Group detections by label directly in SQL. The "prohibited" flag for
    # each label is derived from whatever was actually stored on those rows
    # (MAX() over a 0/1 boolean == "was any detection of this label flagged
    # prohibited") rather than from a hardcoded label set — a custom/
    # fine-tuned model (see app/services/object_detection.py) may use an
    # entirely different prohibited-label configuration than the default
    # detector, and the analytics must reflect what actually ran, not a
    # static assumption.
    detection_rows = db.execute(
        select(Detection.label, func.count(Detection.id), func.max(Detection.prohibited))
        .join(Event, Event.id == Detection.event_id)
        .where(Event.video_id == video_id)
        .group_by(Detection.label)
        .order_by(func.count(Detection.id).desc())
    ).all()

    object_counts = [
        ObjectCount(label=label, count=count, prohibited=bool(prohibited_flag))
        for label, count, prohibited_flag in detection_rows
    ]
    total_detections = sum(count for _, count, _ in detection_rows)

    prohibited_count = db.execute(
        select(func.count(Detection.id))
        .join(Event, Event.id == Detection.event_id)
        .where(Event.video_id == video_id, Detection.prohibited.is_(True))
    ).scalar_one()

    return VideoAnalytics(
        video_id=video_id,
        total_events=int(total_events),
        total_motion_duration=round(float(total_motion), 2),
        motion_coverage=round(min(1.0, coverage), 4),
        average_motion_score=round(float(avg_score), 5),
        peak_motion_score=round(peak_row.peak_motion_score, 5) if peak_row else 0.0,
        peak_activity_time=round(peak_row.start_time, 2) if peak_row else 0.0,
        longest_event_duration=round(longest_row.duration, 2) if longest_row else 0.0,
        longest_event_id=longest_row.id if longest_row else None,
        total_detections=int(total_detections),
        prohibited_detections=int(prohibited_count),
        object_counts=object_counts,
    )


def compute_timeline(db: Session, video: Video, *, max_points: int = 600) -> TimelineResponse:
    """Build a down-sampled motion timeline plus event markers.

    The timeline is reconstructed from events: within each event the motion is
    represented by its average (normalized) score, and gaps between events are
    zero. This yields a compact, dashboard-ready series without persisting
    per-frame data.

    Uses a single forward-advancing pointer over the (already time-sorted,
    non-overlapping) events rather than re-scanning every event for every
    sampled point — O(events + points) instead of O(events x points), which
    matters on a long recording with hundreds of events sampled at hundreds
    of timeline points.
    """
    events = _events_for(db, video.id)
    duration = video.duration or (events[-1].end_time if events else 0.0)

    # Choose a sampling interval that keeps the series under ``max_points``.
    interval = max(0.5, round(duration / max_points, 3)) if duration else 1.0

    points: list[TimelinePoint] = []
    event_idx = 0
    n_events = len(events)
    t = 0.0
    while t <= duration + 1e-6:
        while event_idx < n_events and events[event_idx].end_time < t:
            event_idx += 1

        score = 0.0
        active = False
        objs: list[str] = []
        if event_idx < n_events and events[event_idx].start_time <= t <= events[event_idx].end_time:
            current = events[event_idx]
            score = current.motion_score
            active = True
            objs = [o for o in current.objects.split(",") if o]

        points.append(
            TimelinePoint(time=round(t, 3), motion_score=round(score, 5), active=active, objects=objs)
        )
        t += interval

    markers = [
        {
            "id": e.id,
            "start": round(e.start_time, 3),
            "end": round(e.end_time, 3),
            "motion_score": round(e.motion_score, 5),
            "objects": [o for o in e.objects.split(",") if o],
        }
        for e in events
    ]

    return TimelineResponse(
        video_id=video.id,
        duration=round(duration, 3),
        fps=video.fps,
        sample_interval=interval,
        points=points,
        event_markers=markers,
    )
