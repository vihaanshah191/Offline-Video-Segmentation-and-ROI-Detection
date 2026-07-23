"""Integration test for the full analysis pipeline."""
from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

from app.core.config import settings
from app.models.video import Video, VideoStatus
from app.services.pipeline import AnalysisPipeline, PipelineConfig, _FrameReaderThread
from app.utils.video_io import probe_metadata


def test_pipeline_config_survives_celery_style_serialization() -> None:
    """Regression test: PipelineConfig is a ``slots=True`` dataclass, which
    has no ``__dict__`` — a plain ``config.__dict__`` (as the Celery task
    dispatch previously did) raises AttributeError, silently caught by
    enqueue_analysis's broad except-and-fall-back-to-threads, so the celery
    backend never actually ran a single job even when configured. The fix is
    ``dataclasses.asdict()``, which must round-trip through
    ``PipelineConfig(**...)`` exactly as celery_app.analyze_video_task does."""
    original = PipelineConfig.from_settings(
        settings,
        motion_algorithm="mog2",
        object_detection_confidence=0.42,
        object_detection_classes=["phone", "bag"],
    )
    as_dict = dataclasses.asdict(original)
    assert isinstance(as_dict, dict)
    reconstructed = PipelineConfig(**as_dict)
    assert reconstructed == original


def test_frame_reader_thread_stop_unblocks_a_full_queue(sample_video_path: Path) -> None:
    """Regression test: a reader thread abandoned mid-stream (cancellation or
    a fatal corrupt-frame abort) used to stay blocked forever on a full
    queue's ``put()`` — leaking the thread and its open VideoCapture for the
    rest of the process's life, since nothing ever calls ``.get()`` again.

    A queue_size of 1 with no consumer reproduces that "queue stays full,
    producer stays blocked" state almost immediately. Without ``stop()``
    unblocking the producer's ``put()``, ``join()`` would time out and the
    thread would still be alive.
    """
    reader = _FrameReaderThread(str(sample_video_path), step=1, queue_size=1).start()
    reader.stop()
    reader.join(timeout=2.0)
    assert not reader._thread.is_alive()


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

    # Per-event heatmaps must also be generated (each event has ROIs, so
    # each should produce a heatmap file too).
    assert first.heatmap_path is not None and Path(first.heatmap_path).exists()


def test_pipeline_frame_diff_algorithm(db_session, sample_video_path: Path) -> None:
    video = _register_video(db_session, sample_video_path)
    config = PipelineConfig.from_settings(
        settings, motion_algorithm="frame_diff", enable_object_detection=False
    )
    pipeline = AnalysisPipeline(config, settings)
    summary = pipeline.run(video, db_session, progress_cb=lambda pct, msg: None)
    assert summary["events"] >= 1
    assert video.motion_algorithm == "frame_diff"
