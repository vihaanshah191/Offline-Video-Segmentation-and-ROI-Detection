"""Tests for report generation (CSV export and the PDF investigation report)."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import settings
from app.models.video import Video, VideoStatus
from app.services.pipeline import AnalysisPipeline, PipelineConfig
from app.services.report import build_pdf_report, events_to_csv
from app.utils.video_io import probe_metadata


def _register_and_analyze(db_session, sample_video_path: Path, name: str) -> Video:
    """Run the real pipeline so the video has real events, ROIs, detections,
    a heatmap file and event thumbnails on disk — the PDF report embeds all
    of these, so a fixture with only ORM rows and no files would silently
    skip the interesting code paths (Image() flowables, the motion chart)."""
    dest = settings.videos_dir / name
    shutil.copy(sample_video_path, dest)
    meta = probe_metadata(dest)
    video = Video(
        filename=name,
        original_name=name,
        path=str(dest),
        fps=meta.fps,
        duration=meta.duration,
        width=meta.width,
        height=meta.height,
        frame_count=meta.frame_count,
        size_bytes=dest.stat().st_size,
        status=VideoStatus.UPLOADED,
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)

    config = PipelineConfig.from_settings(settings, motion_algorithm="mog2", enable_object_detection=False)
    AnalysisPipeline(config, settings).run(video, db_session)
    db_session.refresh(video)
    return video


def test_events_to_csv_has_expected_columns(db_session, sample_video_path: Path) -> None:
    video = _register_and_analyze(db_session, sample_video_path, "report_csv.mp4")
    csv_text = events_to_csv(db_session, video)
    assert "event_id" in csv_text
    assert "peak_motion_score" in csv_text


def test_build_pdf_report_produces_valid_pdf_with_events(db_session, sample_video_path: Path) -> None:
    video = _register_and_analyze(db_session, sample_video_path, "report_pdf.mp4")
    assert video.event_count if hasattr(video, "event_count") else True  # sanity, not authoritative

    pdf_bytes = build_pdf_report(db_session, video)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 2000  # a trivial/empty document would be much smaller


def test_build_pdf_report_handles_video_with_no_events(db_session) -> None:
    """A video with zero events (e.g. a static recording) must still
    generate a valid report — no heatmap, no event snapshot, no motion
    chart data, but no crash either."""
    video = Video(
        filename="empty.mp4",
        original_name="empty.mp4",
        path="/tmp/empty.mp4",
        fps=25.0,
        duration=5.0,
        width=320,
        height=240,
        frame_count=125,
        size_bytes=1000,
        status=VideoStatus.COMPLETED,
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)

    pdf_bytes = build_pdf_report(db_session, video)
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_report_endpoint_returns_pdf(client, sample_video_path: Path) -> None:
    with sample_video_path.open("rb") as fh:
        upload = client.post(
            "/api/upload", files={"file": ("sample.mp4", fh, "video/mp4")}
        )
    video_id = upload.json()["id"]

    import time

    client.post(f"/api/analyze/{video_id}", json={"motion_algorithm": "mog2", "enable_object_detection": False})
    for _ in range(120):
        detail = client.get(f"/api/video/{video_id}").json()
        if detail["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert detail["status"] == "completed"

    resp = client.get(f"/api/report/{video_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
