"""Analytics and timeline aggregation services (read models)."""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.video import Detection, Event, Video
from app.schemas.analytics import (
    ObjectCount,
    TimelinePoint,
    TimelineResponse,
    VideoAnalytics,
)
from app.services.object_detection import PROHIBITED_LABELS


def _events_for(db: Session, video_id: int) -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.video_id == video_id)
        .options(selectinload(Event.detections), selectinload(Event.rois))
        .order_by(Event.start_time)
    )
    return list(db.execute(stmt).scalars().all())


def compute_analytics(db: Session, video: Video) -> VideoAnalytics:
    """Aggregate dashboard analytics for a video."""
    events = _events_for(db, video.id)

    total_events = len(events)
    total_motion = sum(e.duration for e in events)
    duration = video.duration or 0.0
    coverage = (total_motion / duration) if duration > 0 else 0.0

    avg_score = (
        sum(e.motion_score for e in events) / total_events if total_events else 0.0
    )

    peak_event = max(events, key=lambda e: e.peak_motion_score, default=None)
    longest = max(events, key=lambda e: e.duration, default=None)

    detections: list[Detection] = [d for e in events for d in e.detections]
    label_counter: Counter[str] = Counter(d.label for d in detections)
    object_counts = [
        ObjectCount(label=label, count=count, prohibited=label in PROHIBITED_LABELS)
        for label, count in sorted(label_counter.items(), key=lambda kv: kv[1], reverse=True)
    ]
    prohibited = sum(1 for d in detections if d.prohibited)

    return VideoAnalytics(
        video_id=video.id,
        total_events=total_events,
        total_motion_duration=round(total_motion, 2),
        motion_coverage=round(min(1.0, coverage), 4),
        average_motion_score=round(avg_score, 5),
        peak_motion_score=round(peak_event.peak_motion_score, 5) if peak_event else 0.0,
        peak_activity_time=round(peak_event.start_time, 2) if peak_event else 0.0,
        longest_event_duration=round(longest.duration, 2) if longest else 0.0,
        longest_event_id=longest.id if longest else None,
        total_detections=len(detections),
        prohibited_detections=prohibited,
        object_counts=object_counts,
    )


def compute_timeline(db: Session, video: Video, *, max_points: int = 600) -> TimelineResponse:
    """Build a down-sampled motion timeline plus event markers.

    The timeline is reconstructed from events: within each event the motion is
    represented by its average score, and gaps between events are zero. This
    yields a compact, dashboard-ready series without persisting per-frame data.
    """
    events = _events_for(db, video.id)
    duration = video.duration or (events[-1].end_time if events else 0.0)

    # Choose a sampling interval that keeps the series under ``max_points``.
    interval = max(0.5, round(duration / max_points, 3)) if duration else 1.0

    points: list[TimelinePoint] = []
    t = 0.0
    while t <= duration + 1e-6:
        score = 0.0
        active = False
        objs: list[str] = []
        for event in events:
            if event.start_time <= t <= event.end_time:
                score = event.motion_score
                active = True
                objs = [o for o in event.objects.split(",") if o]
                break
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
