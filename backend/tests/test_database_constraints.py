"""Tests for database-level CHECK constraints, indexes and cascade deletion.

These encode, at the database layer, the same numeric invariants the
application already enforces in Python — so a future bug (or a raw SQL
script bypassing the ORM) can't silently write nonsensical rows.
"""
from __future__ import annotations

import pytest
from app.models.video import ROI, Detection, Event, Video, VideoStatus
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def _make_video(db_session, **overrides) -> Video:
    defaults = {
        "filename": "v.mp4",
        "original_name": "v.mp4",
        "path": "/tmp/v.mp4",
        "fps": 25.0,
        "duration": 10.0,
        "width": 640,
        "height": 480,
        "frame_count": 250,
        "size_bytes": 1000,
        "status": VideoStatus.UPLOADED,
    }
    defaults.update(overrides)
    video = Video(**defaults)
    db_session.add(video)
    db_session.commit()
    return video


def _make_event(db_session, video: Video, **overrides) -> Event:
    defaults = {
        "video_id": video.id,
        "start_time": 1.0,
        "end_time": 3.0,
        "duration": 2.0,
        "motion_score": 0.5,
        "peak_motion_score": 0.8,
        "confidence": 0.6,
    }
    defaults.update(overrides)
    event = Event(**defaults)
    db_session.add(event)
    db_session.commit()
    return event


# ----------------------------------------------------------------- Video CHECKs
def test_video_progress_out_of_range_rejected(db_session) -> None:
    with pytest.raises(IntegrityError):
        _make_video(db_session, progress=150.0)
    db_session.rollback()


def test_video_negative_duration_rejected(db_session) -> None:
    with pytest.raises(IntegrityError):
        _make_video(db_session, duration=-1.0)
    db_session.rollback()


def test_video_valid_progress_boundary_accepted(db_session) -> None:
    video = _make_video(db_session, progress=100.0)
    assert video.id is not None


# ----------------------------------------------------------------- Event CHECKs
def test_event_end_before_start_rejected(db_session) -> None:
    video = _make_video(db_session)
    with pytest.raises(IntegrityError):
        _make_event(db_session, video, start_time=5.0, end_time=2.0)
    db_session.rollback()


def test_event_motion_score_out_of_range_rejected(db_session) -> None:
    video = _make_video(db_session)
    with pytest.raises(IntegrityError):
        _make_event(db_session, video, motion_score=1.5)
    db_session.rollback()


def test_event_negative_duration_rejected(db_session) -> None:
    video = _make_video(db_session)
    with pytest.raises(IntegrityError):
        _make_event(db_session, video, duration=-1.0)
    db_session.rollback()


def test_event_valid_row_accepted(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    assert event.id is not None


# ------------------------------------------------------------------- ROI CHECKs
def test_roi_zero_width_rejected(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    db_session.add(ROI(event_id=event.id, x=0, y=0, w=0, h=10, confidence=0.5))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_roi_confidence_out_of_range_rejected(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    db_session.add(ROI(event_id=event.id, x=0, y=0, w=10, h=10, confidence=1.2))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_roi_valid_row_accepted(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    roi = ROI(event_id=event.id, x=0, y=0, w=10, h=10, confidence=0.5)
    db_session.add(roi)
    db_session.commit()
    assert roi.id is not None


# ------------------------------------------------------------- Detection CHECKs
def test_detection_confidence_out_of_range_rejected(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    db_session.add(
        Detection(event_id=event.id, label="phone", confidence=-0.1, x=0, y=0, w=5, h=5)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_detection_valid_row_accepted(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    det = Detection(
        event_id=event.id, label="phone", confidence=0.9, prohibited=True, heuristic=False,
        x=0, y=0, w=5, h=5,
    )
    db_session.add(det)
    db_session.commit()
    assert det.id is not None
    assert det.heuristic is False


# -------------------------------------------------------------- cascade delete
def test_deleting_video_cascades_to_events_rois_detections(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    db_session.add(ROI(event_id=event.id, x=0, y=0, w=10, h=10, confidence=0.5))
    db_session.add(Detection(event_id=event.id, label="phone", confidence=0.9, x=0, y=0, w=5, h=5))
    db_session.commit()

    event_id = event.id
    db_session.delete(video)
    db_session.commit()

    assert db_session.get(Event, event_id) is None
    remaining_rois = db_session.query(ROI).filter_by(event_id=event_id).all()
    remaining_detections = db_session.query(Detection).filter_by(event_id=event_id).all()
    assert remaining_rois == []
    assert remaining_detections == []


def test_sqlite_foreign_keys_pragma_enabled(db_session) -> None:
    """Defense-in-depth check: FK enforcement must be ON for the test DB
    connection too (not just documented), since it protects against a raw
    delete that bypasses the ORM's explicit cascade logic."""
    result = db_session.execute(text("PRAGMA foreign_keys")).scalar()
    assert result == 1
