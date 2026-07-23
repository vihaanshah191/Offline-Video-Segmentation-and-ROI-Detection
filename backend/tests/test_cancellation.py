"""Tests for cooperative analysis cancellation (Video.cancel_requested)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from app.models.video import Video, VideoStatus
from app.services.pipeline import PipelineCancelled
from app.services.video_service import VideoService
from fastapi.testclient import TestClient

API = "/api"


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
    db_session.refresh(video)
    return video


def test_request_cancel_flips_flag_when_processing(db_session) -> None:
    video = _make_video(db_session, status=VideoStatus.PROCESSING)
    service = VideoService(db_session)

    assert service.request_cancel(video) is True
    assert video.cancel_requested is True


def test_request_cancel_flips_flag_when_queued(db_session) -> None:
    video = _make_video(db_session, status=VideoStatus.QUEUED)
    service = VideoService(db_session)

    assert service.request_cancel(video) is True
    assert video.cancel_requested is True


@pytest.mark.parametrize(
    "status",
    [VideoStatus.UPLOADED, VideoStatus.COMPLETED, VideoStatus.FAILED, VideoStatus.CANCELLED],
)
def test_request_cancel_no_op_when_not_running(db_session, status) -> None:
    video = _make_video(db_session, status=status)
    service = VideoService(db_session)

    assert service.request_cancel(video) is False
    assert video.cancel_requested is False


def test_try_mark_queued_resets_stale_cancel_flag(db_session) -> None:
    """Regression test: a video whose previous run failed for an unrelated
    reason while a cancel request happened to be in flight could be left
    with cancel_requested=True in the DB (the generic failure handler used
    to only set status/error, not clear the flag). Without this reset, the
    very next re-analysis's first cancellation checkpoint would immediately
    abort it as "cancelled" even though the user never cancelled that run."""
    video = _make_video(db_session, status=VideoStatus.FAILED, cancel_requested=True)
    service = VideoService(db_session)

    assert service.try_mark_queued(video) is True
    assert video.cancel_requested is False


def test_pipeline_check_cancelled_raises_when_flagged(db_session) -> None:
    from app.services.pipeline import AnalysisPipeline

    video = _make_video(db_session, status=VideoStatus.PROCESSING, cancel_requested=True)

    with pytest.raises(PipelineCancelled):
        AnalysisPipeline._check_cancelled(db_session, video.id)


def test_pipeline_check_cancelled_noop_when_not_flagged(db_session) -> None:
    from app.services.pipeline import AnalysisPipeline

    video = _make_video(db_session, status=VideoStatus.PROCESSING, cancel_requested=False)

    AnalysisPipeline._check_cancelled(db_session, video.id)  # must not raise


def test_cancel_endpoint_404_for_missing_video(client: TestClient) -> None:
    resp = client.post(f"{API}/video/999999/cancel")
    assert resp.status_code == 404


def test_cancel_endpoint_409_when_not_running(client: TestClient, sample_video_path: Path) -> None:
    with sample_video_path.open("rb") as fh:
        upload = client.post(f"{API}/upload", files={"file": ("sample.mp4", fh, "video/mp4")})
    video_id = upload.json()["id"]

    resp = client.post(f"{API}/video/{video_id}/cancel")
    assert resp.status_code == 409


def test_cancel_endpoint_end_to_end(client: TestClient, sample_video_path: Path) -> None:
    """Requesting cancellation immediately after enqueueing analysis must
    eventually leave the video in either 'cancelled' (cancellation won the
    race with the fast synthetic-video pipeline) or 'completed' (the tiny
    sample video finished before the next cancellation checkpoint) — never
    'failed' or stuck 'processing'."""
    with sample_video_path.open("rb") as fh:
        upload = client.post(f"{API}/upload", files={"file": ("sample.mp4", fh, "video/mp4")})
    video_id = upload.json()["id"]

    analyze_resp = client.post(
        f"{API}/analyze/{video_id}",
        json={"motion_algorithm": "mog2", "enable_object_detection": False},
    )
    assert analyze_resp.status_code == 202

    cancel_resp = client.post(f"{API}/video/{video_id}/cancel")
    assert cancel_resp.status_code in (200, 409)  # 409 if it already finished

    status = ""
    for _ in range(120):
        detail = client.get(f"{API}/video/{video_id}").json()
        status = detail["status"]
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.5)

    assert status in ("completed", "cancelled"), f"unexpected terminal status: {status}"
    if status == "cancelled":
        assert detail["progress"] < 100.0
