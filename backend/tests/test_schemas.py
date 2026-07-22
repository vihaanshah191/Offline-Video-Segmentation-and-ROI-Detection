"""Tests for derived (computed) Pydantic schema fields: severity and the
filesystem-path -> served-URL conversions on EventRead/VideoDetail."""
from __future__ import annotations

from app.core.config import settings
from app.models.video import Detection, Event, Video, VideoStatus
from app.schemas.event import EventRead
from app.schemas.video import VideoDetail


def _make_video(db_session, **overrides) -> Video:
    defaults = {
        "filename": "v.mp4", "original_name": "v.mp4", "path": "/tmp/v.mp4",
        "fps": 25.0, "duration": 10.0, "width": 640, "height": 480, "frame_count": 250,
        "size_bytes": 1000, "status": VideoStatus.COMPLETED,
    }
    defaults.update(overrides)
    video = Video(**defaults)
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


def _make_event(db_session, video, **overrides) -> Event:
    defaults = {
        "video_id": video.id, "start_time": 1.0, "end_time": 3.0, "duration": 2.0,
        "motion_score": 0.5, "peak_motion_score": 0.3, "confidence": 0.6, "objects": "",
    }
    defaults.update(overrides)
    event = Event(**defaults)
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_event_severity_normal_by_default(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video, peak_motion_score=0.1)
    read = EventRead.model_validate(event)
    assert read.severity == "normal"


def test_event_severity_warning_on_high_motion(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video, peak_motion_score=0.9)
    read = EventRead.model_validate(event)
    assert read.severity == "warning"


def test_event_severity_warning_on_heuristic_prohibited(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video, peak_motion_score=0.1)
    db_session.add(
        Detection(
            event_id=event.id, label="book", confidence=0.7, prohibited=True, heuristic=True,
            x=0, y=0, w=1, h=1,
        )
    )
    db_session.commit()
    db_session.refresh(event)
    read = EventRead.model_validate(event)
    assert read.severity == "warning"


def test_event_severity_critical_on_confirmed_prohibited(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video, peak_motion_score=0.1)
    db_session.add(
        Detection(
            event_id=event.id, label="phone", confidence=0.9, prohibited=True, heuristic=False,
            x=0, y=0, w=1, h=1,
        )
    )
    db_session.commit()
    db_session.refresh(event)
    read = EventRead.model_validate(event)
    assert read.severity == "critical"


def test_event_clip_and_thumbnail_urls_derived_from_paths(db_session) -> None:
    # A path actually under storage_dir (as production's nested storage/clips
    # etc. layout has) converts to a full relative URL; the test environment
    # deliberately uses flat sibling dirs (see conftest.py), so exercise that
    # nested case directly against storage_dir rather than assuming
    # settings.clips_dir is nested under it in every deployment.
    video = _make_video(db_session)
    clip_path = str(settings.storage_dir / "clips" / "clip1.mp4")
    thumb_path = str(settings.storage_dir / "thumbnails" / "thumb1.jpg")
    event = _make_event(db_session, video, clip_path=clip_path, thumbnail_path=thumb_path)
    read = EventRead.model_validate(event)
    assert read.clip_url == "/storage/clips/clip1.mp4"
    assert read.thumbnail_url == "/storage/thumbnails/thumb1.jpg"


def test_event_urls_none_when_paths_absent(db_session) -> None:
    video = _make_video(db_session)
    event = _make_event(db_session, video)
    read = EventRead.model_validate(event)
    assert read.clip_url is None
    assert read.thumbnail_url is None


def test_video_detail_heatmap_and_thumbnail_urls(db_session) -> None:
    heatmap_path = str(settings.storage_dir / "heatmaps" / "heat1.png")
    thumb_path = str(settings.storage_dir / "thumbnails" / "vid1.jpg")
    video = _make_video(db_session, heatmap_path=heatmap_path, thumbnail_path=thumb_path)
    detail = VideoDetail.model_validate(video)
    assert detail.heatmap_url == "/storage/heatmaps/heat1.png"
    assert detail.thumbnail_url == "/storage/thumbnails/vid1.jpg"
