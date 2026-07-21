"""Tests for the SQL-aggregation-based analytics and timeline services."""
from __future__ import annotations

from app.models.video import Detection, Event, Video, VideoStatus
from app.services.analytics import compute_analytics, compute_timeline


def _make_video(db_session, **overrides) -> Video:
    defaults = {
        "filename": "v.mp4", "original_name": "v.mp4", "path": "/tmp/v.mp4",
        "fps": 25.0, "duration": 20.0, "width": 640, "height": 480, "frame_count": 500,
        "size_bytes": 1000, "status": VideoStatus.COMPLETED,
    }
    defaults.update(overrides)
    video = Video(**defaults)
    db_session.add(video)
    db_session.commit()
    return video


def _make_event(db_session, video, **overrides) -> Event:
    defaults = {
        "video_id": video.id, "start_time": 1.0, "end_time": 3.0, "duration": 2.0,
        "motion_score": 0.5, "peak_motion_score": 0.8, "confidence": 0.6, "objects": "",
    }
    defaults.update(overrides)
    event = Event(**defaults)
    db_session.add(event)
    db_session.commit()
    return event


def test_compute_analytics_empty_video(db_session) -> None:
    video = _make_video(db_session)
    analytics = compute_analytics(db_session, video)
    assert analytics.total_events == 0
    assert analytics.total_motion_duration == 0.0
    assert analytics.motion_coverage == 0.0
    assert analytics.longest_event_id is None
    assert analytics.object_counts == []


def test_compute_analytics_aggregates_correctly(db_session) -> None:
    video = _make_video(db_session, duration=10.0)
    _make_event(
        db_session, video, start_time=0, end_time=2, duration=2.0,
        motion_score=0.2, peak_motion_score=0.3,
    )
    e2 = _make_event(
        db_session, video, start_time=4, end_time=8, duration=4.0,
        motion_score=0.9, peak_motion_score=0.95,
    )

    analytics = compute_analytics(db_session, video)
    assert analytics.total_events == 2
    assert analytics.total_motion_duration == 6.0
    assert analytics.motion_coverage == 0.6  # 6s of 10s duration
    assert analytics.average_motion_score == (0.2 + 0.9) / 2
    assert analytics.longest_event_id == e2.id
    assert analytics.longest_event_duration == 4.0
    assert analytics.peak_motion_score == 0.95


def test_compute_analytics_coverage_clamped_to_one(db_session) -> None:
    """Overlapping/rounding artefacts must never push coverage above 100%."""
    video = _make_video(db_session, duration=1.0)
    _make_event(db_session, video, start_time=0, end_time=5, duration=5.0)
    analytics = compute_analytics(db_session, video)
    assert analytics.motion_coverage == 1.0


def test_object_counts_prohibited_flag_reflects_stored_data_not_static_set(db_session) -> None:
    """Regression test: object_counts' 'prohibited' flag must be derived from
    what was actually stored on Detection rows (which can vary per detector
    configuration — default vs. a custom fine-tuned model), not from a
    hardcoded module-level label set that might not match what actually ran."""
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    # "widget" is not in any built-in prohibited set, but THIS detection was
    # stored with prohibited=True (e.g. a custom model's own configuration).
    db_session.add(
        Detection(event_id=event.id, label="widget", confidence=0.9, prohibited=True, x=0, y=0, w=1, h=1)
    )
    db_session.add(
        Detection(event_id=event.id, label="widget", confidence=0.8, prohibited=True, x=0, y=0, w=1, h=1)
    )
    db_session.commit()

    analytics = compute_analytics(db_session, video)
    widget_count = next(oc for oc in analytics.object_counts if oc.label == "widget")
    assert widget_count.count == 2
    assert widget_count.prohibited is True


def test_prohibited_detections_count(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    db_session.add(
        Detection(event_id=event.id, label="phone", confidence=0.9, prohibited=True, x=0, y=0, w=1, h=1)
    )
    db_session.add(
        Detection(event_id=event.id, label="person", confidence=0.9, prohibited=False, x=0, y=0, w=1, h=1)
    )
    db_session.commit()

    analytics = compute_analytics(db_session, video)
    assert analytics.total_detections == 2
    assert analytics.prohibited_detections == 1


def test_compute_timeline_basic_shape(db_session) -> None:
    video = _make_video(db_session, duration=10.0)
    _make_event(db_session, video, start_time=2, end_time=4, duration=2.0, motion_score=0.7, objects="phone")

    timeline = compute_timeline(db_session, video, max_points=20)
    assert timeline.duration == 10.0
    assert len(timeline.points) > 0
    assert len(timeline.event_markers) == 1
    assert timeline.event_markers[0]["objects"] == ["phone"]

    active_points = [p for p in timeline.points if p.active]
    assert all(2.0 <= p.time <= 4.0 for p in active_points)
    assert all(p.motion_score == 0.7 for p in active_points)


def test_compute_timeline_no_events(db_session) -> None:
    video = _make_video(db_session, duration=5.0)
    timeline = compute_timeline(db_session, video)
    assert all(not p.active for p in timeline.points)
    assert timeline.event_markers == []


def test_compute_timeline_multiple_disjoint_events(db_session) -> None:
    """Regression-style check for the two-pointer sweep replacing the old
    O(events x points) nested loop: multiple, well-separated events must each
    be correctly reflected at their own time range."""
    video = _make_video(db_session, duration=20.0)
    _make_event(db_session, video, start_time=1, end_time=2, duration=1.0, motion_score=0.3, objects="a")
    _make_event(db_session, video, start_time=10, end_time=11, duration=1.0, motion_score=0.9, objects="b")

    timeline = compute_timeline(db_session, video, max_points=100)
    near_first = [p for p in timeline.points if 1.0 <= p.time <= 2.0]
    near_second = [p for p in timeline.points if 10.0 <= p.time <= 11.0]
    assert all(p.active and p.motion_score == 0.3 for p in near_first)
    assert all(p.active and p.motion_score == 0.9 for p in near_second)

    far_from_both = [p for p in timeline.points if 4.0 <= p.time <= 8.0]
    assert far_from_both  # sanity: interval is fine enough to have points here
    assert all(not p.active for p in far_from_both)
