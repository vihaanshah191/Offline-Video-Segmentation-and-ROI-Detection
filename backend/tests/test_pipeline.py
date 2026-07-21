"""Integration test for the full analysis pipeline."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import settings
from app.models.video import Video, VideoStatus
from app.services.pipeline import AnalysisPipeline, PipelineConfig
from app.utils.video_io import probe_metadata


def _register_video(db_session, sample_video_path: Path) -> Video:
    dest = settings.videos_dir / "pipeline_sample.mp4"
    shutil.copy(sample_video_path, dest)
    meta = probe_metadata(dest)
    video = Video(
        filename="pipeline_sample.mp4",
        original_name="pipeline_sample.mp4",
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
    return video


def test_pipeline_creates_events_and_heatmap(db_session, sample_video_path: Path) -> None:
    video = _register_video(db_session, sample_video_path)
    config = PipelineConfig.from_settings(
        settings, motion_algorithm="mog2", enable_object_detection=False
    )
    pipeline = AnalysisPipeline(config, settings)
    summary = pipeline.run(video, db_session, progress_cb=lambda pct, msg: None)

    assert summary["events"] >= 1
    assert video.status == VideoStatus.COMPLETED
    assert video.progress == 100.0

    # At least one event with a merged ROI and a generated clip file.
    assert len(video.events) >= 1
    first = video.events[0]
    assert first.duration > 0
    assert len(first.rois) >= 1
    assert first.clip_path is not None and Path(first.clip_path).exists()

    # Heatmap PNG must be generated.
    assert video.heatmap_path is not None and Path(video.heatmap_path).exists()


def test_pipeline_frame_diff_algorithm(db_session, sample_video_path: Path) -> None:
    video = _register_video(db_session, sample_video_path)
    config = PipelineConfig.from_settings(
        settings, motion_algorithm="frame_diff", enable_object_detection=False
    )
    pipeline = AnalysisPipeline(config, settings)
    summary = pipeline.run(video, db_session, progress_cb=lambda pct, msg: None)
    assert summary["events"] >= 1
    assert video.motion_algorithm == "frame_diff"
